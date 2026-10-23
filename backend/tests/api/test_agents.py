from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.db.models import Agent
from app.services.seed import seed


async def test_create_handle_and_builtin(client):
    response = await client.post(
        "/api/agents", json={"handle": "@security_checker", "display_name": "Security", "runtime": "codex"}
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["role_key"] == "CUSTOM" and not created["is_builtin"]
    assert (
        await client.post("/api/agents", json={"handle": "@security_checker", "display_name": "Again"})
    ).status_code == 409
    builtin = (await client.get("/api/agents")).json()[0]
    assert (await client.delete(f"/api/agents/{builtin['id']}")).status_code == 409
    assert (
        await client.patch(f"/api/agents/{builtin['id']}", json={"role_key": "CUSTOM"})
    ).status_code == 422
    assert (
        await client.patch(f"/api/agents/{created['id']}", json={"handle": "@changed"})
    ).status_code == 422
    assert (
        await client.post(f"/api/agents/{created['id']}/duplicate", json={"handle": "@copy"})
    ).status_code == 201
    assert (await client.delete(f"/api/agents/{created['id']}")).status_code == 200


async def test_edit_restarts_only_if_changed(client):
    agent = (await client.get("/api/agents")).json()[0]
    with patch.object(client.app.state.acp_pool, "restart_agent", new_callable=AsyncMock) as restart:
        response = await client.patch(f"/api/agents/{agent['id']}", json={"model": "custom-model"})
        assert response.status_code == 200, response.text
        assert response.json()["restart"] and response.json()["agent"]["config_version"] == 2
        restart.assert_awaited_once_with(agent["id"], 2)
        restart.reset_mock()
        response = await client.patch(f"/api/agents/{agent['id']}", json={"model": "custom-model"})
        assert response.json()["restart"] is False
        restart.assert_not_awaited()
        assert (await client.post(f"/api/agents/{agent['id']}/restart")).json()["agent"][
            "config_version"
        ] == 3


async def test_seed_is_idempotent(client):
    async with client.app.state.db_session() as db:
        await seed(db, client.app.state.settings)
        await seed(db, client.app.state.settings)
        assert len((await db.scalars(select(Agent))).all()) == 4
    teams = (await client.get("/api/teams")).json()
    assert len(teams) == 1 and len(teams[0]["agent_ids"]) == 4
    assert (await client.get("/api/projects")).json()["total"] == 0


async def test_catalog_and_presets(client):
    assert "codex" in (await client.get("/api/agents/models-catalog")).json()
    catalog = client.app.state.models_catalog
    catalog.observe("codex", [{"modelId": "runtime-model", "name": "Runtime"}])
    assert any(
        item["id"] == "runtime-model"
        for item in (await client.get("/api/agents/models-catalog")).json()["codex"]
    )
    assert (await client.get("/api/agents/permission-presets")).json()["leader"]["can_git_release"]


async def test_concurrent_edits_increment_each_version(client):
    import asyncio

    aid = (await client.get("/api/agents")).json()[0]["id"]
    responses = await asyncio.gather(
        *(client.patch(f"/api/agents/{aid}", json={"model": f"model-{i}"}) for i in range(4))
    )
    assert all(response.status_code == 200 for response in responses)
    assert sorted(response.json()["agent"]["config_version"] for response in responses) == [2, 3, 4, 5]
