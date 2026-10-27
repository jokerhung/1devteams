import json
from collections import deque

import httpx
import pytest
from sqlalchemy import func, select

from app.acp.api_session import ApiAgentSession
from app.db.models import Ticket
from app.services.agent_service import policy
from tests.api.conftest import project
from tests.engine.test_browser_worker import actions, block
from tests.engine.test_browser_worker import browser_site as browser_site


async def test_direct_chat_selected_project_uses_workspace_and_releases_it(engine_client):
    client = engine_client
    entity = await project(client)
    agent = (await client.get("/api/agents")).json()[0]
    response = await client.post(
        "/api/agent-chat",
        json={
            "agent_id": agent["id"],
            "project_id": entity["id"],
            "messages": [{"role": "user", "content": "Kiểm tra project"}],
        },
    )
    assert response.status_code == 200, response.text
    session = client.factory.sessions[-1]
    assert session.workspace == client.workspace.resolve()
    assert session.workspace.exists()
    assert not session.alive
    prompt = client.factory.prompts[agent["handle"]][-1][0]
    assert f"Project: {entity['name']}" in prompt
    assert "không phải source của project" not in prompt
    assert not any(lock.locked() for lock in client.app.state.ticket_runner.workspace_locks.values())


async def test_direct_chat_invalid_project_does_not_start_agent(engine_client):
    client = engine_client
    agent = (await client.get("/api/agents")).json()[0]
    response = await client.post(
        "/api/agent-chat",
        json={
            "agent_id": agent["id"],
            "project_id": "00000000-0000-0000-0000-000000000000",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    assert response.status_code == 404
    assert not client.factory.sessions


async def test_direct_chat_keeps_context_and_closes_isolated_session(engine_client):
    client = engine_client
    agent = (await client.get("/api/agents")).json()[0]
    client.factory.scripts[agent["handle"]].append("Xin chào!")
    messages = [
        {"role": "user", "content": "Tôi tên Nam"},
        {"role": "assistant", "content": "Chào Nam"},
        {"role": "user", "content": "Tên tôi là gì?"},
    ]
    response = await client.post("/api/agent-chat", json={"agent_id": agent["id"], "messages": messages})
    assert response.status_code == 200, response.text
    assert response.json() == {"message": "Xin chào!", "reports": []}
    session = client.factory.sessions[-1]
    prompt = client.factory.prompts[agent["handle"]][-1][0]
    assert json.loads(prompt.split("\n", 1)[1]) == messages
    assert session.cfg.system_prompt == agent["system_prompt"]
    assert agent["handle"] in prompt
    assert agent["display_name"] in prompt
    for key, value in agent["permission_profile"].items():
        assert session.cfg.permission_profile.model_dump()[key] == value
    assert "không thực thi công cụ" not in prompt
    assert not session.alive
    assert not session.workspace.exists()
    assert not client.app.state.acp_pool.sessions
    async with client.app.state.db_session() as db:
        assert await db.scalar(select(func.count()).select_from(Ticket)) == 0


async def test_direct_chat_failure_can_retry_and_releases_capacity(engine_client):
    client = engine_client
    agent = (await client.get("/api/agents")).json()[0]
    client.factory.scripts[agent["handle"]].extend(["ERROR", "Đã kết nối"])
    payload = {"agent_id": agent["id"], "messages": [{"role": "user", "content": "Xin chào"}]}
    response = await client.post("/api/agent-chat", json=payload)
    assert response.status_code == 502
    assert not client.app.state.acp_pool.sessions
    response = await client.post("/api/agent-chat", json=payload)
    assert response.status_code == 200
    assert response.json()["message"] == "Đã kết nối"


async def test_direct_chat_stream_reports_runtime_failure(engine_client):
    client = engine_client
    agent = (await client.get("/api/agents")).json()[0]
    client.factory.scripts[agent["handle"]].append("ERROR")
    response = await client.post(
        "/api/agent-chat",
        headers={"Accept": "text/event-stream"},
        json={
            "agent_id": agent["id"],
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[0]["type"] == "action"
    assert events[-1]["type"] == "error"
    assert not client.app.state.acp_pool.sessions


async def test_direct_chat_streams_browser_progress_before_reply(engine_client, browser_site):
    client = engine_client
    agent = next(a for a in (await client.get("/api/agents")).json() if a["handle"] == "@tester")
    client.factory.scripts["@tester"].extend(
        [
            block(actions(browser_site)),
            block([{"action": "report", "summary": "Verified"}]),
            "Test completed",
        ]
    )
    response = await client.post(
        "/api/agent-chat",
        headers={"Accept": "text/event-stream"},
        json={
            "agent_id": agent["id"],
            "messages": [{"role": "user", "content": "Test login"}],
        },
    )
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
    actions_seen = [event for event in events if event["type"] == "action"]
    assert len(actions_seen) > 5
    navigate = [event for event in actions_seen if event["title"].startswith("Browser: navigate")]
    assert [event["status"] for event in navigate] == ["in_progress", "completed"]
    assert navigate[0]["id"] == navigate[1]["id"]
    assert events[-1]["type"] == "reply"
    assert events[-1]["reports"][0]["status"] == "PASS"
    assert "correct-secret" not in response.text
    assert not client.app.state.acp_pool.sessions


async def test_direct_chat_validates_messages_and_authentication(client):
    agent = (await client.get("/api/agents")).json()[0]
    for messages in (
        [],
        [{"role": "assistant", "content": "Hello"}],
        [{"role": "user", "content": "x" * 12001}],
    ):
        response = await client.post("/api/agent-chat", json={"agent_id": agent["id"], "messages": messages})
        assert response.status_code == 422
    client.headers.pop("Authorization")
    response = await client.post(
        "/api/agent-chat", json={"agent_id": agent["id"], "messages": [{"role": "user", "content": "Hello"}]}
    )
    assert response.status_code == 401


@pytest.mark.parametrize("custom_api", [False, True])
async def test_tester_runs_browser_without_ticket(engine_client, browser_site, custom_api):
    client = engine_client
    tester = next(a for a in (await client.get("/api/agents")).json() if a["handle"] == "@tester")
    replies = deque(
        [
            block(actions(browser_site)),
            block([{"action": "report", "summary": "Authenticated page verified"}]),
            "Login verified using the browser.",
        ]
    )
    if custom_api:
        response = await client.patch(
            f"/api/agents/{tester['id']}",
            json={
                "runtime": "openai-api",
                "base_url": "http://localhost/v1",
                "model": "test-model",
                "api_key": "test-provider-key",
                "permission_profile": {"allow_browser": True},
            },
        )
        assert response.status_code == 200, response.text

        async def answer(request):
            data = {
                "choices": [{"index": 0, "delta": {"content": replies.popleft()}, "finish_reason": "stop"}]
            }
            return httpx.Response(200, text="data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n")

        client.app.state.acp_pool.factory = lambda cfg, workspace: ApiAgentSession(
            cfg, workspace, transport=httpx.MockTransport(answer), policy=policy(client.app.state.settings)
        )
    else:
        client.factory.scripts["@tester"].extend(replies)
    response = await client.post(
        "/api/agent-chat",
        json={
            "agent_id": tester["id"],
            "messages": [{"role": "user", "content": "Test the login page"}],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["message"] == "Login verified using the browser."
    assert "correct-secret" not in response.text
    assert "@@BROWSER" not in response.text
    assert len(body["reports"]) == 1
    report = body["reports"][0]
    assert report["status"] == "PASS"
    assert len(report["checks"]) == 2
    assert report["screenshot"].startswith("data:image/png;base64,")
    assert not client.app.state.acp_pool.sessions
    assert not client.app.state.ticket_runner.browser_manager.workers
    async with client.app.state.db_session() as db:
        assert await db.scalar(select(func.count()).select_from(Ticket)) == 0
