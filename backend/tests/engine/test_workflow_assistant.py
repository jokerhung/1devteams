import asyncio
import json

from tests.api.conftest import project


async def test_assistant_proposes_without_saving_and_closes_session(engine_client):
    client = engine_client
    entity = await project(client, seeded=True)
    workflow = entity["workflow"]
    graph = workflow["graph"]
    graph["nodes"][1]["data"]["instructions"] = "New BA instruction"
    client.factory.scripts["@workflow"].append("Updated BA\n@@WORKFLOW\n" + json.dumps(graph) + "\n@@END")
    response = await client.post(
        f"/api/workflows/{workflow['id']}/assistant",
        json={"graph": workflow["graph"], "messages": [{"role": "user", "content": "Update BA"}]},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["message"] == "Updated BA" and result["graph"] == graph
    assert not result["errors"]
    persisted = (await client.get(f"/api/workflows/{workflow['id']}")).json()
    assert persisted["current_version"] == workflow["current_version"]
    assert persisted["graph"]["nodes"][1]["data"].get("instructions") != "New BA instruction"
    session = client.factory.sessions[-1]
    assert session.cfg.handle == "@workflow"
    assert not session.cfg.permission_profile.allow_read
    assert not session.cfg.permission_profile.allow_write
    assert not session.cfg.permission_profile.allow_terminal
    assert session.workspace != client.workspace
    assert not session.alive and not await asyncio.to_thread(session.workspace.exists)
    assert not client.app.state.acp_pool.sessions
    agents = (await client.get("/api/agents")).json()
    assistant = next(agent for agent in agents if agent["handle"] == "@workflow")
    assert assistant["is_builtin"]
    team = (await client.get("/api/teams")).json()[0]
    assert assistant["id"] not in team["agent_ids"]


async def test_assistant_rejects_unsafe_graph_and_supports_clarification(engine_client):
    client = engine_client
    entity = await project(client, seeded=True)
    workflow = entity["workflow"]
    graph = workflow["graph"]
    graph["edges"].append({"id": "bypass", "source": "start", "target": "n_lead"})
    body = {"graph": workflow["graph"], "messages": [{"role": "user", "content": "Remove approval"}]}
    client.factory.scripts["@workflow"].append("@@WORKFLOW\n" + json.dumps(graph) + "\n@@END")
    response = await client.post(f"/api/workflows/{workflow['id']}/assistant", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["graph"] is None and response.json()["errors"]
    client.factory.scripts["@workflow"].append("Which agent should review?")
    response = await client.post("/api/workflow-templates/add_feature/assistant", json=body)
    assert response.status_code == 200 and response.json()["graph"] is None
    assert response.json()["message"] == "Which agent should review?"
    client.factory.scripts["@workflow"].append("@@WORKFLOW\ninvalid\n@@END")
    response = await client.post("/api/workflow-templates/add_feature/assistant", json=body)
    assert response.json()["graph"] is None and response.json()["errors"]


async def test_assistant_permissions_and_runtime_errors(engine_client):
    client = engine_client
    entity = await project(client, seeded=True)
    workflow = entity["workflow"]
    body = {"graph": workflow["graph"], "messages": [{"role": "user", "content": "Help"}]}
    client.factory.scripts["@workflow"].append("ERROR")
    failed = await client.post(f"/api/workflows/{workflow['id']}/assistant", json=body)
    assert failed.status_code == 502
    assert not client.app.state.acp_pool.sessions
    created = await client.post(
        "/api/users",
        json={"email": "viewer@example.com", "display_name": "Viewer", "password": "Password123!"},
    )
    assert created.status_code == 201
    login = await client.post(
        "/api/auth/login", json={"email": "viewer@example.com", "password": "Password123!"}
    )
    headers = {"Authorization": "Bearer " + login.json()["access_token"]}
    assert (
        await client.post(f"/api/workflows/{workflow['id']}/assistant", json=body, headers=headers)
    ).status_code == 403
    assert (
        await client.post("/api/workflow-templates/add_feature/assistant", json=body, headers=headers)
    ).status_code == 403


async def test_assistant_does_not_hold_sqlite_lock_while_waiting(engine_client):
    client = engine_client
    entity = await project(client, seeded=True)
    workflow = entity["workflow"]
    client.factory.blocked.add("@workflow")
    pending = asyncio.create_task(
        client.post(
            f"/api/workflows/{workflow['id']}/assistant",
            json={"graph": workflow["graph"], "messages": [{"role": "user", "content": "Help"}]},
        )
    )
    try:
        await asyncio.wait_for(client.factory.entered.wait(), 5)
        response = await asyncio.wait_for(
            client.patch(f"/api/workflows/{workflow['id']}", json={"description": "Edit while model runs"}), 3
        )
        assert response.status_code == 200
    finally:
        for session in client.factory.sessions:
            session.closed.set()
        response = await asyncio.wait_for(pending, 5)
    assert response.status_code == 200


async def test_assistant_uses_configured_api_runtime(engine_client):
    client = engine_client
    agents = (await client.get("/api/agents")).json()
    agent = next(item for item in agents if item["handle"] == "@workflow")
    updated = await client.patch(
        f"/api/agents/{agent['id']}",
        json={
            "runtime": "openai-api",
            "base_url": "http://localhost/v1",
            "model": "workflow-model",
            "api_key": "test-secret",
            "api_params": {"reasoning_format": "reasoning_effort"},
        },
    )
    assert updated.status_code == 200, updated.text
    graph = {
        "nodes": [{"id": "start", "type": "start"}, {"id": "end", "type": "end"}],
        "edges": [{"id": "e1", "source": "start", "target": "end"}],
    }
    client.factory.scripts["@workflow"].append("@@WORKFLOW\n" + json.dumps(graph) + "\n@@END")
    response = await client.post(
        "/api/workflow-templates/add_feature/assistant",
        json={"graph": graph, "messages": [{"role": "user", "content": "Use a blank flow"}]},
    )
    assert response.status_code == 200 and response.json()["graph"]
    cfg = client.factory.sessions[-1].cfg
    assert cfg.runtime == "openai-api" and cfg.model == "workflow-model"
    assert cfg.api_key.get_secret_value() == "test-secret"
