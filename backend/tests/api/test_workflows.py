from copy import deepcopy

from tests.api.conftest import project


async def test_templates_versions_and_validation(client):
    entity = await project(client, seeded=True)
    workflow = entity["workflow"]
    wid = workflow["id"]
    assert workflow["status"] == "PUBLISHED" and workflow["is_valid"]
    assert len((await client.get("/api/workflow-templates")).json()) == 4
    response = await client.post(
        f"/api/projects/{entity['id']}/workflows", json={"name": "Feature", "ticket_prefix": "FEAT"}
    )
    assert response.status_code == 201, response.text
    assert (
        await client.post(
            f"/api/projects/{entity['id']}/workflows", json={"name": "Other", "ticket_prefix": "FEAT"}
        )
    ).status_code == 409
    graph = deepcopy(workflow["graph"])
    graph["edges"] = [edge for edge in graph["edges"] if edge.get("sourceHandle") != "fail"]
    saved = await client.put(f"/api/workflows/{wid}/graph", json=graph)
    assert saved.status_code == 200, saved.text
    assert not saved.json()["is_valid"] and saved.json()["current_version"] == 2
    assert (await client.post(f"/api/workflows/{wid}/publish")).status_code == 400
    graph = deepcopy(workflow["graph"])
    graph["edges"].append({"id": "bypass", "source": "start", "target": "n_lead"})
    response = await client.post(f"/api/workflows/{wid}/validate", json=graph)
    assert any("human_confirm" in message for message in response.json()["errors"])
    graph = deepcopy(workflow["graph"])
    assert (await client.put(f"/api/workflows/{wid}/graph", json=graph)).json()["is_valid"]
    assert (await client.post(f"/api/workflows/{wid}/publish")).json()["published_version"] == 3
    assert len((await client.get(f"/api/workflows/{wid}/versions")).json()) == 2
    original = (await client.get(f"/api/workflows/{wid}/versions/1")).json()
    assert original["graph"] == workflow["graph"]
    duplicate = await client.post(
        f"/api/workflows/{wid}/duplicate", json={"name": "Copy", "ticket_prefix": "COPY"}
    )
    assert duplicate.json()["status"] == "DRAFT" and duplicate.json()["published_version"] is None


async def test_archive_and_delete_rules(client):
    entity = await project(client, seeded=True)
    wid, pid = entity["workflow"]["id"], entity["id"]
    assert (
        await client.post(f"/api/workflows/{wid}/tickets", json={"title": "Ticket", "auto_start": False})
    ).status_code == 201
    assert (await client.post(f"/api/workflows/{wid}/archive")).status_code == 409
    assert (await client.delete(f"/api/workflows/{wid}")).status_code == 409
    assert (await client.patch(f"/api/workflows/{wid}", json={"ticket_prefix": "NEW"})).status_code == 409
    draft = (
        await client.post(f"/api/projects/{pid}/workflows", json={"name": "Second", "ticket_prefix": "SEC"})
    ).json()
    assert (await client.post(f"/api/workflows/{wid}/archive")).status_code == 200
    assert (await client.post(f"/api/workflows/{wid}/tickets", json={"title": "No"})).status_code == 400
    assert (await client.delete(f"/api/workflows/{draft['id']}")).status_code == 200
    assert (await client.post(f"/api/workflows/{wid}/unarchive")).status_code == 200
    assert (await client.delete(f"/api/workflows/{draft['id']}")).status_code == 404
    assert (await client.delete(f"/api/projects/{pid}?cascade=true")).status_code == 200


async def test_cycle_and_inactive_agent_validation(client):
    entity = await project(client, seeded=True)
    wid = entity["workflow"]["id"]
    graph = deepcopy(entity["workflow"]["graph"])
    graph["edges"].append({"id": "loop", "source": "g_clar", "target": "g_clar"})
    response = await client.post(f"/api/workflows/{wid}/validate", json=graph)
    assert any("chu trình" in error for error in response.json()["errors"])
    removal = await client.delete(
        f"/api/projects/{entity['id']}/members/TEAM/{(await client.get('/api/teams')).json()[0]['id']}"
    )
    assert removal.status_code == 409
    ba = next(agent for agent in (await client.get("/api/agents")).json() if agent["handle"] == "@ba")
    assert (await client.patch(f"/api/agents/{ba['id']}", json={"is_active": False})).status_code == 200
    response = await client.post(f"/api/workflows/{wid}/validate")
    assert not response.json()["is_valid"]


async def test_concurrent_graph_versions_and_published_agent_usage(client):
    import asyncio

    entity = await project(client, seeded=True)
    wid = entity["workflow"]["id"]
    graph = entity["workflow"]["graph"]
    responses = await asyncio.gather(
        *(client.put(f"/api/workflows/{wid}/graph", json=graph) for _ in range(4))
    )
    assert all(response.status_code == 200 for response in responses)
    assert sorted(response.json()["current_version"] for response in responses) == [2, 3, 4, 5]
    agent = (
        await client.post("/api/agents", json={"handle": "@reviewer", "display_name": "Reviewer"})
    ).json()
    await client.post(
        f"/api/projects/{entity['id']}/members", json={"member_type": "AGENT", "member_id": agent["id"]}
    )
    minimal = {
        "nodes": [
            {"id": "s", "type": "start"},
            {"id": "r", "type": "agent", "data": {"agent_id": agent["id"]}},
            {"id": "e", "type": "end"},
        ],
        "edges": [{"id": "a", "source": "s", "target": "r"}, {"id": "b", "source": "r", "target": "e"}],
    }
    assert (await client.put(f"/api/workflows/{wid}/graph", json=minimal)).json()["is_valid"]
    assert (await client.post(f"/api/workflows/{wid}/publish")).status_code == 200
    await client.put(f"/api/workflows/{wid}/graph", json=graph)
    assert (await client.delete(f"/api/agents/{agent['id']}")).status_code == 409
    used = (await client.get(f"/api/agents/{agent['id']}/usage")).json()
    assert used["workflows"][0]["id"] == wid


async def test_api_agent_cannot_be_developer_or_tester(client):
    entity = await project(client, seeded=True)
    api = (
        await client.post(
            "/api/agents",
            json={
                "handle": "@text",
                "display_name": "Text",
                "runtime": "openai-api",
                "base_url": "http://localhost/v1",
                "api_key": "secret",
                "model": "fake",
            },
        )
    ).json()
    await client.post(
        f"/api/projects/{entity['id']}/members", json={"member_type": "AGENT", "member_id": api["id"]}
    )
    for node_id in ["n_dev", "n_test", "n_lead"]:
        graph = deepcopy(entity["workflow"]["graph"])
        next(node for node in graph["nodes"] if node["id"] == node_id)["data"]["agent_id"] = api["id"]
        response = await client.post(f"/api/workflows/{entity['workflow']['id']}/validate", json=graph)
        assert not response.json()["is_valid"] and any(
            "OpenAI Custom" in item for item in response.json()["errors"]
        )
