import asyncio
import json
import logging
import socket
from unittest.mock import patch

import httpx
import pytest
from pydantic import ValidationError

from app.acp.api_session import ApiAgentSession
from app.acp.types import AgentRuntimeConfig
from app.acp.url_policy import PinnedTransport, URLPolicy, URLPolicyError, completion_url
from tests.fakes.fake_openai import app, requests


@pytest.fixture
def api_cfg():
    return AgentRuntimeConfig(
        agent_id="api",
        handle="@custom-api",
        runtime="openai-api",
        model="test-model",
        base_url="http://localhost/v1",
        api_key="test-secret",
        system_prompt="System role",
    )


def make_api(cfg, tmp_path, **kwargs):
    return ApiAgentSession(
        cfg,
        tmp_path,
        policy=URLPolicy({"localhost"}, {"localhost"}),
        transport=httpx.ASGITransport(app=app),
        **kwargs,
    )


async def collect(session, text="Go"):
    return [event async for event in session.prompt(text)]


@pytest.mark.parametrize("model", ["test-model", "length"])
async def test_stream(api_cfg, tmp_path, model):
    api_cfg.model = model
    session = make_api(api_cfg, tmp_path)
    try:
        await session.start()
        events = await collect(session)
        assert (
            "".join(event.content for event in events if event.event_type == "message_chunk")
            == "@@ROUTE: ready"
        )
        assert any(event.event_type == "thought_chunk" for event in events)
        assert any("tokens: prompt 7" in event.content for event in events)
        assert any("finish_reason=" in event.content for event in events)
        assert events[-1].metadata["modified_files"] == [] and not session.modified_files
        assert requests[-1]["messages"][0] == {"role": "system", "content": "System role"}
        assert requests[-1]["stream_options"]["include_usage"] and "tools" not in requests[-1]
        await collect(session, "Again")
        assert requests[-1]["messages"][2]["role"] == "assistant"
    finally:
        await session.close()


@pytest.mark.parametrize("status", ["401", "403", "404", "429", "500", "timeout", "redirect"])
async def test_errors(api_cfg, tmp_path, caplog, status):
    api_cfg.model = status
    session = make_api(api_cfg, tmp_path, timeout=0.1)
    try:
        await session.start()
        with caplog.at_level(logging.DEBUG):
            events = await collect(session)
        assert events[-1].event_type == "error"
        if status.isdigit():
            assert events[-1].metadata["status_code"] == int(status)
        assert "test-secret" not in json.dumps([event.model_dump() for event in events]) + caplog.text
        assert not session.history
    finally:
        await session.close()


async def test_cancel_discards_partial_history(api_cfg, tmp_path):
    api_cfg.model = "timeout"
    session = make_api(api_cfg, tmp_path)
    await session.start()
    stream = session.prompt("Go")
    first = await anext(stream)
    assert first.event_type == "log"
    await session.cancel()
    rest = [event async for event in stream]
    assert rest[-1].metadata["stop_reason"] == "cancelled" and not session.history
    await session.close()


async def test_context_budget(api_cfg, tmp_path):
    session = make_api(api_cfg, tmp_path, context_chars=45)
    await session.start()
    await collect(session, "First")
    await collect(session, "New text that excludes history")
    assert len(requests[-1]["messages"]) == 2
    events = await collect(session, "X" * 100)
    assert events[-1].event_type == "error"
    await session.close()


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://169.254.169.254/",
        "https://[fd00:ec2::254]/",
        "https://127.0.0.1/v1",
        "http://localhost:11434/v1",
        "https://user:pass@public.example/v1",
        "https://public.example/v1?api_key=secret",
        "https://public.example/v1?access_token=secret",
    ],
)
async def test_ssrf(api_cfg, tmp_path, url):
    with pytest.raises(URLPolicyError):
        await URLPolicy().validate(url)


async def test_local_requires_both_allowlists():
    with pytest.raises(URLPolicyError):
        await URLPolicy({"localhost"}, set()).validate("http://localhost:11434/v1")
    url, ips = await URLPolicy({"localhost"}, {"localhost"}).validate("http://localhost:11434/v1")
    assert url.port == 11434 and ips


async def test_dns_private_and_mixed_answers():
    loop = asyncio.get_running_loop()
    addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443)) for ip in ("8.8.8.8", "10.0.0.1")]
    with patch.object(loop, "getaddrinfo", return_value=addresses):
        with pytest.raises(URLPolicyError):
            await URLPolicy().validate("https://public.example/v1")


async def test_dns_connection_is_pinned_and_sni_preserved():
    loop = asyncio.get_running_loop()
    addresses = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("8.8.8.8", 443))]
    captured = []

    async def handle(self, request):
        captured.append(request)
        return httpx.Response(200)

    transport = PinnedTransport("https://public.example/v1", URLPolicy())
    try:
        with (
            patch.object(loop, "getaddrinfo", return_value=addresses),
            patch.object(httpx.AsyncHTTPTransport, "handle_async_request", handle),
        ):
            await transport.handle_async_request(
                httpx.Request("POST", "https://public.example/v1/chat/completions")
            )
        assert captured[0].url.host == "8.8.8.8"
        assert captured[0].headers["Host"] == "public.example"
        assert captured[0].extensions["sni_hostname"] == "public.example"
        with pytest.raises(URLPolicyError):
            await transport.handle_async_request(
                httpx.Request("POST", "https://evil.example/v1/chat/completions")
            )
    finally:
        await transport.aclose()


def test_azure_query_preserved_and_api_permissions(api_cfg):
    assert (
        completion_url("https://host/openai/deployments/a/?api-version=2024-10-21")
        == "https://host/openai/deployments/a/chat/completions?api-version=2024-10-21"
    )
    with pytest.raises(ValidationError):
        AgentRuntimeConfig(
            **(api_cfg.model_dump() | {"api_key": "x", "permission_profile": {"allow_write": True}})
        )


async def test_pinned_transport_with_actual_socket(api_cfg, tmp_path):
    received = asyncio.get_running_loop().create_future()

    async def serve(reader, writer):
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            content_length = next(
                int(line.split(b":", 1)[1])
                for line in headers.split(b"\r\n")
                if line.lower().startswith(b"content-length:")
            )
            body = await reader.readexactly(content_length)
            received.set_result((headers, json.loads(body)))
            chunks = [
                {"choices": [{"delta": {"content": "socket verified"}, "finish_reason": None}]},
                {"choices": [{"delta": {}, "finish_reason": "stop"}]},
            ]
            response = "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks).encode()
            writer.write(
                b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nConnection: close\r\n"
                + f"Content-Length: {len(response)}\r\n\r\n".encode()
                + response
            )
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    api_cfg.base_url = f"http://127.0.0.1:{port}/v1"
    session = ApiAgentSession(api_cfg, tmp_path, policy=URLPolicy({"127.0.0.1"}, {"127.0.0.1"}), timeout=5)
    try:
        await session.start()
        events = await collect(session)
        assert events[-1].metadata["full_text"] == "socket verified"
        headers, body = await asyncio.wait_for(received, 2)
        assert f"host: 127.0.0.1:{port}".encode() in headers.lower()
        assert b"Authorization: Bearer test-secret" in headers
        assert body["model"] == "test-model" and body["stream"]
    finally:
        await session.close()
        server.close()
        await server.wait_closed()
