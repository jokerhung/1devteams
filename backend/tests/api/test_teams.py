from unittest.mock import AsyncMock, patch


async def test_nonempty_and_agent_removal(client):
    assert (await client.post("/api/teams", json={"name": "Empty", "agent_ids": []})).status_code == 422
    agent = (await client.post("/api/agents", json={"handle": "@solo", "display_name": "Solo"})).json()
    response = await client.post("/api/teams", json={"name": "Solo Team", "agent_ids": [agent["id"]]})
    assert response.status_code == 201, response.text
    team = response.json()
    assert (await client.put(f"/api/teams/{team['id']}/agents", json={"agent_ids": []})).status_code == 422
    assert (await client.delete(f"/api/agents/{agent['id']}")).status_code == 409
    assert (await client.patch(f"/api/agents/{agent['id']}", json={"is_active": False})).status_code == 409
    with patch.object(client.app.state.acp_pool, "restart_agent", new_callable=AsyncMock) as restart:
        assert (await client.patch(f"/api/teams/{team['id']}", json={"name": "New Name"})).status_code == 200
        restart.assert_not_awaited()
    await client.delete(f"/api/teams/{team['id']}")
    assert (await client.delete(f"/api/agents/{agent['id']}")).status_code == 200
