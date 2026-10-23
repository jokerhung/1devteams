from tests.api.conftest import project


async def test_remove_team_preserves_agents_required_by_workflow(client):
    entity = await project(client, seeded=True)
    pid = entity["id"]
    team = (await client.get("/api/teams")).json()[0]
    response = await client.delete(f"/api/projects/{pid}/members/TEAM/{team['id']}")
    assert response.status_code == 409
    assert "Fix Bug" in response.json()["detail"]
    assert len((await client.get(f"/api/projects/{pid}/effective-agents")).json()) == 4
    # An alternative membership path keeps all workflow agents available.
    for aid in team["agent_ids"]:
        await client.post(f"/api/projects/{pid}/members", json={"member_type": "AGENT", "member_id": aid})
    assert (await client.delete(f"/api/projects/{pid}/members/TEAM/{team['id']}")).status_code == 200


async def test_member_role_can_change_without_removing_membership(client):
    entity = await project(client)
    uid = (
        await client.post(
            "/api/users",
            json={"email": "phase4@example.com", "display_name": "Phase 4", "password": "Password123!"},
        )
    ).json()["id"]
    path = f"/api/projects/{entity['id']}/members"
    await client.post(path, json={"member_type": "USER", "member_id": uid, "project_role": "VIEWER"})
    response = await client.patch(f"{path}/USER/{uid}", json={"project_role": "REPORTER"})
    assert response.status_code == 200
    assert (await client.get(path)).json()["users"][0]["project_role"] == "REPORTER"
    assert (await client.patch(f"{path}/USER/{uid}", json={"project_role": "OWNER"})).status_code == 422


async def test_team_edit_and_delete_cannot_orphan_workflow_agents(client):
    await project(client, seeded=True)
    team = (await client.get("/api/teams")).json()[0]
    endpoint = f"/api/teams/{team['id']}"
    assert (await client.patch(endpoint, json={"agent_ids": team["agent_ids"][:1]})).status_code == 409
    assert (await client.delete(endpoint)).status_code == 409
    assert (await client.get(endpoint)).json()["agent_ids"] == team["agent_ids"]
