import httpx

from tests.api.conftest import project


async def test_workspace_empty_project_and_effective_agents(client):
    bad = await client.post(
        "/api/projects", json={"name": "Bad", "workspace_path": "C:/Windows", "default_branch": "main"}
    )
    assert bad.status_code == 400
    details = (
        await client.post("/api/projects/validate-workspace", json={"path": str(client.workspace)})
    ).json()
    assert details["is_git_repo"] and details["current_branch"] == "main"
    entity = await project(client)
    pid = entity["id"]
    assert (await client.get(f"/api/projects/{pid}/workflows")).json() == []
    assert (await client.get(f"/api/projects/{pid}/members")).json() == {
        "users": [],
        "agents": [],
        "teams": [],
    }
    team = (await client.get("/api/teams")).json()[0]
    assert (
        await client.post(
            f"/api/projects/{pid}/members", json={"member_type": "TEAM", "member_id": team["id"]}
        )
    ).status_code == 201
    assert len((await client.get(f"/api/projects/{pid}/effective-agents")).json()) == 7
    aid = team["agent_ids"][0]
    await client.post(f"/api/projects/{pid}/members", json={"member_type": "AGENT", "member_id": aid})
    assert len((await client.get(f"/api/projects/{pid}/effective-agents")).json()) == 7
    await client.delete(f"/api/projects/{pid}/members/TEAM/{team['id']}")
    assert [agent["id"] for agent in (await client.get(f"/api/projects/{pid}/effective-agents")).json()] == [
        aid
    ]


async def test_recent_activity_and_pin(client):
    projects = [await project(client, f"Project {index}", seeded=index == 0) for index in range(6)]
    expected = [item["id"] for item in reversed(projects)]
    assert [item["id"] for item in (await client.get("/api/projects/recent")).json()] == expected[:5]
    await client.get(f"/api/projects/{projects[0]['id']}")
    assert [item["id"] for item in (await client.get("/api/projects/recent")).json()] == expected[:5]
    pinned = (await client.get(f"/api/projects/recent?pin={projects[0]['id']}")).json()
    assert [item["id"] for item in pinned] == expected[:4] + [projects[0]["id"]]
    await client.post(f"/api/workflows/{projects[0]['workflow']['id']}/tickets", json={"title": "Activity"})
    assert (await client.get("/api/projects/recent")).json()[0]["id"] == projects[0]["id"]


async def test_project_authorization(client):
    entity = await project(client, seeded=True)
    wid = entity["workflow"]["id"]
    tid = (
        await client.post(f"/api/workflows/{wid}/tickets", json={"title": "Protected", "auto_start": False})
    ).json()["ticket"]["id"]
    response = await client.post(
        "/api/users",
        json={"email": "viewer@example.com", "display_name": "Viewer", "password": "Password123!"},
    )
    uid = response.json()["id"]
    login = (
        await client.post("/api/auth/login", json={"email": "viewer@example.com", "password": "Password123!"})
    ).json()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + login["access_token"]},
    ) as viewer:
        assert (await viewer.get(f"/api/projects/{entity['id']}")).status_code == 403
        assert (await viewer.get("/api/projects")).json()["total"] == 0
        await client.post(
            f"/api/projects/{entity['id']}/members",
            json={"member_type": "USER", "member_id": uid, "project_role": "VIEWER"},
        )
        assert (await viewer.get(f"/api/projects/{entity['id']}")).status_code == 200
        assert (
            await viewer.patch(f"/api/projects/{entity['id']}", json={"name": "Hacked"})
        ).status_code == 403
        assert (await viewer.post(f"/api/projects/{entity['id']}/seed-default")).status_code == 403
        for scope, identifier in [("projects", entity["id"]), ("workflows", wid), ("tickets", tid)]:
            assert (await viewer.delete(f"/api/{scope}/{identifier}?cascade=true")).status_code == 403
            if scope != "tickets":
                assert (await viewer.get(f"/api/{scope}/{identifier}/deletion-preview")).status_code == 403
