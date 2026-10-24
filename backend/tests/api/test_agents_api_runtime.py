import json

import httpx
import pytest
from sqlalchemy import select

from app.db.models import Agent
from app.services.agent_service import runtime_config
from app.services.connections import test_api as probe_api

PAYLOAD = {
    "handle": "@api_agent",
    "display_name": "API Agent",
    "runtime": "openai-api",
    "base_url": "http://localhost/v1",
    "model": "test-model",
    "api_key": "test-private-key",
    "api_params": {"extra_headers": {"api-key": "extra-secret"}},
}


async def test_api_key_encryption_edit_and_switch(client, caplog):
    response = await client.post("/api/agents", json=PAYLOAD)
    assert response.status_code == 201, response.text
    aid = response.json()["id"]
    assert "test-private-key" not in response.text and "extra-secret" not in response.text
    assert response.json()["has_key"] and response.json()["api_key_last4"] == "-key"
    async with client.app.state.db_session() as db:
        agent = await db.scalar(select(Agent).where(Agent.id == aid))
        assert agent.api_key_enc != PAYLOAD["api_key"]
        assert "extra-secret" not in json.dumps(agent.api_params)
        cfg = runtime_config(agent, client.app.state.settings)
        assert cfg.api_key.get_secret_value() == PAYLOAD["api_key"]
        assert cfg.api_params.extra_headers["api-key"].get_secret_value() == "extra-secret"
    response = await client.patch(f"/api/agents/{aid}", json={"description": "new"})
    assert response.json()["agent"]["has_key"]
    same = await client.patch(f"/api/agents/{aid}", json={"api_key": PAYLOAD["api_key"]})
    assert not same.json()["restart"]
    response = await client.patch(f"/api/agents/{aid}", json={"api_key": "rotated-key-9999"})
    assert response.json()["restart"] and response.json()["agent"]["api_key_last4"] == "9999"
    native = await client.post(
        "/api/agents", json={"handle": "@native", "display_name": "Native", "permission_profile": "developer"}
    )
    response = await client.patch(
        f"/api/agents/{native.json()['id']}",
        json={
            key: value
            for key, value in PAYLOAD.items()
            if key not in {"handle", "display_name", "api_params"}
        },
    )
    assert response.status_code == 200, response.text
    assert not response.json()["agent"]["permission_profile"]["allow_write"]
    assert "test-private-key" not in caplog.text and "extra-secret" not in caplog.text


@pytest.mark.parametrize(
    "key,value",
    [
        ("base_url", None),
        ("model", None),
        ("api_key", None),
        ("permission_profile", "developer"),
        ("permission_profile", "tester"),
        ("permission_profile", {"can_git_release": True}),
        ("base_url", "http://169.254.169.254/v1"),
        ("base_url", "https://10.0.0.1/v1"),
    ],
)
async def test_bad_api_config(client, key, value):
    response = await client.post("/api/agents", json=PAYLOAD | {key: value})
    assert response.status_code == 422, response.text
    assert "test-private-key" not in response.text


async def test_connection_fake_models_and_rate_limit(client, monkeypatch):
    from app.schemas.agent import ConnectionDraft
    from tests.fakes.fake_openai import app

    body = ConnectionDraft(base_url="http://localhost/v1", api_key="test-key", model="test-model")
    result = await probe_api(body, client.app.state.settings, transport=httpx.ASGITransport(app=app))
    assert result["ok"] and result["models"]
    from app.services import connections

    async def fake(*args):
        return result

    monkeypatch.setattr(connections, "test_api", fake)
    for _ in range(10):
        assert (
            await client.post(
                "/api/agents/test-connection-draft",
                json={"base_url": body.base_url, "api_key": "test-key", "model": body.model},
            )
        ).status_code == 200
    assert (
        await client.post(
            "/api/agents/test-connection-draft",
            json={"base_url": body.base_url, "api_key": "test-key", "model": body.model},
        )
    ).status_code == 429


async def test_api_params_keep_encrypted_headers_and_missing_cipher(client):
    created = await client.post("/api/agents", json=PAYLOAD)
    aid = created.json()["id"]
    assert (
        await client.patch(f"/api/agents/{aid}", json={"api_params": {"temperature": 0.5}})
    ).status_code == 200
    async with client.app.state.db_session() as db:
        agent = await db.get(Agent, aid)
        cfg = runtime_config(agent, client.app.state.settings)
        assert cfg.api_params.extra_headers["api-key"].get_secret_value() == "extra-secret"
    client.app.state.settings.app_secret_key = None
    result = await client.post("/api/agents", json=PAYLOAD | {"handle": "@no_cipher"})
    assert result.status_code == 503 and PAYLOAD["api_key"] not in result.text


async def test_api_options_use_saved_key_for_unsaved_model_config(client, monkeypatch):
    from app.services import connections

    aid = (await client.post("/api/agents", json=PAYLOAD)).json()["id"]

    async def fake(body, settings, *, models_only):
        assert models_only
        assert body.api_key.get_secret_value() == PAYLOAD["api_key"]
        assert body.extra_headers["api-key"].get_secret_value() == "extra-secret"
        return {"ok": True, "latency_ms": 1, "models": [{"id": "new-model"}]}

    monkeypatch.setattr(connections, "test_api", fake)
    response = await client.post(
        "/api/agents/api-options", json={"agent_id": aid, "base_url": PAYLOAD["base_url"]}
    )
    assert response.status_code == 200 and response.json()["models"][0]["id"] == "new-model"
    assert PAYLOAD["api_key"] not in response.text
    response = await client.post(
        "/api/agents/api-options", json={"agent_id": aid, "base_url": "http://localhost/other"}
    )
    assert response.status_code == 422


async def test_discovery_metadata_and_no_completion_fallback(client):
    from app.schemas.agent import ConnectionDraft

    seen = []

    def respond(request):
        seen.append(request.method)
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "reasoner",
                        "reasoning": {"supported_efforts": ["high", "low", "none"], "mandatory": True},
                        "provider_secret": "never return this",
                    },
                    {"id": "plain", "supported_parameters": ["temperature"]},
                    {"id": "test-key"},
                ]
            },
        )

    body = ConnectionDraft(base_url="http://localhost/v1", api_key="test-key", model="test-model")
    result = await probe_api(
        body, client.app.state.settings, transport=httpx.MockTransport(respond), models_only=True
    )
    assert seen == ["GET"]
    assert [item["id"] for item in result["models"]] == ["reasoner", "plain"]
    assert [item["id"] for item in result["models"][0]["reasoning_levels"]] == ["high", "low"]
    assert result["models"][1]["supports_reasoning"] is False
    assert "provider_secret" not in str(result)

    def missing(request):
        assert request.method == "GET"
        return httpx.Response(404)

    result = await probe_api(
        body, client.app.state.settings, transport=httpx.MockTransport(missing), models_only=True
    )
    assert not result["ok"]
