from copy import deepcopy
from uuid import uuid4

import httpx

from tests.api.conftest import project


async def test_builtin_template_resolves_project_roles_and_snapshots_configuration(client):
    entity = await project(client, seeded=True)
    pid = entity["id"]
    templates = (await client.get(f"/api/orchestrator-templates?project_id={pid}")).json()
    template = next(t for t in templates if t["id"] == "add_feature")
    assert template["name"] == "Add new feature" and template["builtin"]
    assert not template["missing_agents"]
    agents = (await client.get(f"/api/projects/{pid}/effective-agents")).json()
    by_id = {a["id"]: a for a in agents}
    config = template["orchestrator"]
    assert by_id[config["coordinator_agent_id"]]["handle"] == "@leader"
    assert [by_id[w["agent_id"]]["handle"] for w in config["workers"]] == [
        "@ba",
        "@planner",
        "@designer",
        "@developer",
        "@tester",
    ]
    response = await client.post(
        f"/api/projects/{pid}/workflows",
        json={
            "name": "Feature team",
            "ticket_prefix": "FEAT",
            "orchestrator": config,
        },
    )
    assert response.status_code == 201, response.text
    workflow = response.json()
    assert workflow["is_valid"]
    assert len(workflow["graph"]["nodes"]) == 8
    designer = next(n for n in workflow["graph"]["nodes"] if n["data"].get("agent_handle") == "@designer")
    assert designer["data"]["document_name"] == "design.md"
    assert (await client.post(f"/api/workflows/{workflow['id']}/publish")).status_code == 200
    update = {
        key: value
        for key, value in template.items()
        if key not in {"id", "builtin", "orchestrator", "missing_agents"}
    }
    update["instructions"] = "Changed template"
    assert (await client.put("/api/orchestrator-templates/add_feature", json=update)).status_code == 200
    unchanged = (await client.get(f"/api/workflows/{workflow['id']}")).json()
    assert unchanged["graph"] == workflow["graph"]
    assert (await client.get(f"/api/workflows/{workflow['id']}/versions/1")).json()["graph"] == workflow[
        "graph"
    ]


async def test_missing_or_inactive_agents_do_not_bind_global_agents(client):
    entity = await project(client)
    pid = entity["id"]
    template = (await client.get(f"/api/orchestrator-templates?project_id={pid}")).json()[0]
    assert template["orchestrator"] is None and len(template["missing_agents"]) == 6
    assert (await client.get(f"/api/orchestrator-templates?project_id={uuid4()}")).status_code == 404
    entity = await project(client, name="Seeded", seeded=True)
    designer = next(a for a in (await client.get("/api/agents")).json() if a["handle"] == "@designer")
    await client.patch(f"/api/agents/{designer['id']}", json={"is_active": False})
    template = (await client.get(f"/api/orchestrator-templates?project_id={entity['id']}")).json()[0]
    assert template["orchestrator"] is None and template["missing_agents"] == ["@designer (DESIGNER)"]


async def test_custom_template_persists_and_rejects_unsafe_document_names(client):
    from app.services.orchestrator_templates import DEFAULT_FEATURE

    body = DEFAULT_FEATURE.model_dump(mode="json")
    body["name"] = "Custom"
    created = await client.post("/api/orchestrator-templates", json=body)
    assert created.status_code == 201, created.text
    key = created.json()["id"]
    body["instructions"] = "New rules"
    assert (await client.put(f"/api/orchestrator-templates/{key}", json=body)).status_code == 200
    saved = next(t for t in (await client.get("/api/orchestrator-templates")).json() if t["id"] == key)
    assert saved["instructions"] == "New rules" and not saved["builtin"]
    bad = deepcopy(body)
    bad["workers"][0]["document_name"] = "../outside.md"
    assert (await client.post("/api/orchestrator-templates", json=bad)).status_code == 422
    assert (await client.put("/api/orchestrator-templates/no-such-template", json=body)).status_code == 404


async def test_worker_selection_rejects_foreign_duplicate_and_coordinator_ids(client):
    entity = await project(client, seeded=True)
    pid = entity["id"]
    config = (await client.get(f"/api/orchestrator-templates?project_id={pid}")).json()[0]["orchestrator"]
    invalid_workers = [
        [{"agent_id": str(uuid4())}],
        [config["workers"][0], config["workers"][0]],
        [{"agent_id": config["coordinator_agent_id"]}],
    ]
    for workers in invalid_workers:
        response = await client.post(
            f"/api/projects/{pid}/workflows",
            json={
                "name": "Invalid",
                "ticket_prefix": "BAD",
                "orchestrator": {**config, "workers": workers},
            },
        )
        assert response.status_code == 422, response.text


async def test_member_cannot_edit_templates_or_read_foreign_project_bindings(client):
    from app.services.orchestrator_templates import DEFAULT_FEATURE

    entity = await project(client, seeded=True)
    await client.post(
        "/api/users",
        json={"email": "member@example.com", "display_name": "Member", "password": "Password123!"},
    )
    login = (
        await client.post("/api/auth/login", json={"email": "member@example.com", "password": "Password123!"})
    ).json()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + login["access_token"]},
    ) as member:
        assert (await member.get("/api/orchestrator-templates")).status_code == 200
        assert (await member.get(f"/api/orchestrator-templates?project_id={entity['id']}")).status_code == 403
        body = DEFAULT_FEATURE.model_dump(mode="json")
        assert (await member.post("/api/orchestrator-templates", json=body)).status_code == 403
        assert (await member.put("/api/orchestrator-templates/add_feature", json=body)).status_code == 403


async def test_template_agent_selections_must_exist_be_active_and_unique(client):
    from app.services.orchestrator_templates import DEFAULT_FEATURE

    body = DEFAULT_FEATURE.model_dump(mode="json")
    unknown = deepcopy(body)
    unknown["workers"][0]["agent_handle"] = "@does_not_exist"
    assert (await client.post("/api/orchestrator-templates", json=unknown)).status_code == 422
    duplicate = deepcopy(body)
    duplicate["workers"].append(duplicate["workers"][0])
    assert (await client.post("/api/orchestrator-templates", json=duplicate)).status_code == 422
    designer = next(a for a in (await client.get("/api/agents")).json() if a["handle"] == "@designer")
    await client.patch(f"/api/agents/{designer['id']}", json={"is_active": False})
    assert (await client.post("/api/orchestrator-templates", json=body)).status_code == 422
    assert (await client.put("/api/orchestrator-templates/add_feature", json=body)).status_code == 422
