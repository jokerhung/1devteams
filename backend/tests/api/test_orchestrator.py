from uuid import uuid4

from tests.api.conftest import project


async def test_orchestrator_create_publish_edit_snapshot_and_project_scope(client):
    entity = await project(client, seeded=True)
    pid = entity["id"]
    agents = (await client.get(f"/api/projects/{pid}/effective-agents")).json()
    leader = next(a for a in agents if a["handle"] == "@leader")
    config = {"coordinator_agent_id": leader["id"], "instructions": "BA → Developer → Tester; sửa nếu FAIL"}
    response = await client.post(
        f"/api/projects/{pid}/workflows",
        json={
            "name": "Orchestrator",
            "ticket_prefix": "ORCH",
            "orchestrator": config,
        },
    )
    assert response.status_code == 201, response.text
    workflow = response.json()
    wid = workflow["id"]
    assert workflow["is_valid"]
    assert workflow["graph"]["orchestrator"]["instructions"] == config["instructions"]
    assert (await client.post(f"/api/workflows/{wid}/publish")).status_code == 200
    original = (await client.get(f"/api/workflows/{wid}/versions/1")).json()
    response = await client.put(
        f"/api/workflows/{wid}/orchestrator", json={**config, "instructions": "Updated"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["current_version"] == 2
    assert (await client.post(f"/api/workflows/{wid}/publish")).json()["published_version"] == 2
    assert (await client.get(f"/api/workflows/{wid}/versions/1")).json() == original
    assert (await client.put(f"/api/workflows/{wid}/graph", json=workflow["graph"])).status_code == 409
    response = await client.put(
        f"/api/workflows/{wid}/orchestrator",
        json={
            **config,
            "coordinator_agent_id": str(uuid4()),
        },
    )
    assert response.status_code == 422
    for patch in ({"max_rounds": 0}, {"max_rounds": 41}, {"instructions": ""}):
        assert (
            await client.put(f"/api/workflows/{wid}/orchestrator", json={**config, **patch})
        ).status_code == 422
    # Existing ticket lifecycle accepts the same published version mechanism.
    ticket = await client.post(
        f"/api/workflows/{wid}/tickets", json={"title": "New task", "auto_start": False}
    )
    assert ticket.status_code == 201, ticket.text
    assert ticket.json()["ticket"]["workflow_version"] == 2
    normal_id = entity["workflow"]["id"]
    assert (await client.put(f"/api/workflows/{normal_id}/orchestrator", json=config)).status_code == 409
