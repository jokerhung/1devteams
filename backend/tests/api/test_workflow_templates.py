from tests.api.conftest import project


async def test_template_instructions_persist_for_new_workflows_only(client):
    entity = await project(client, seeded=True)
    pid = entity["id"]

    async def create(name, prefix):
        response = await client.post(
            f"/api/projects/{pid}/workflows",
            json={"name": name, "ticket_prefix": prefix, "template": "add_feature"},
        )
        assert response.status_code == 201, response.text
        workflow = response.json()
        assert workflow["is_valid"], workflow["validation_errors"]
        return workflow

    original = await create("Feature original", "FEAT")
    saved = await client.put(
        "/api/workflow-templates/add_feature",
        json={"instructions": {"n_ba": "Write acceptance criteria and business rules"}},
    )
    assert saved.status_code == 200, saved.text
    templates = (await client.get(f"/api/workflow-templates?project_id={pid}")).json()
    graph = next(t["graph"] for t in templates if t["id"] == "add_feature")
    assert next(n for n in graph["nodes"] if n["id"] == "n_ba")["data"]["instructions"].startswith(
        "Write acceptance"
    )
    updated = await create("Feature updated", "NEWFEAT")
    old = (await client.get(f"/api/workflows/{original['id']}")).json()
    old_ba = next(n for n in old["graph"]["nodes"] if n["id"] == "n_ba")
    new_ba = next(n for n in updated["graph"]["nodes"] if n["id"] == "n_ba")
    assert old_ba["data"]["instructions"] != new_ba["data"]["instructions"]
    assert len([n for n in graph["nodes"] if n["type"] in {"agent", "git_release"}]) == 8
    assert (
        await client.put("/api/workflow-templates/add_feature", json={"instructions": {"g_confirm": "skip"}})
    ).status_code == 422
    assert (await client.put("/api/workflow-templates/missing", json={"instructions": {}})).status_code == 404


async def test_canvas_template_graph_persists_and_rebinds_agents(client):
    entity = await project(client, seeded=True)
    templates = (await client.get("/api/workflow-templates")).json()
    graph = next(t["graph"] for t in templates if t["id"] == "add_feature")
    ba = next(n for n in graph["nodes"] if n["id"] == "n_ba")
    ba["data"]["instructions"] = "Canvas edited requirements"
    ba["position"] = {"x": 250, "y": 650}
    saved = await client.put("/api/workflow-templates/add_feature", json={"graph": graph})
    assert saved.status_code == 200, saved.text
    templates = (await client.get("/api/workflow-templates")).json()
    restored = next(t["graph"] for t in templates if t["id"] == "add_feature")
    restored_ba = next(n for n in restored["nodes"] if n["id"] == "n_ba")
    assert restored_ba["position"] == ba["position"]
    assert restored_ba["data"]["instructions"] == "Canvas edited requirements"
    assert restored_ba["data"]["agent_role"] == "BA"
    created = await client.post(
        f"/api/projects/{entity['id']}/workflows",
        json={"name": "Canvas template", "ticket_prefix": "FEAT", "template": "add_feature"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["is_valid"]
    assert next(n for n in created.json()["graph"]["nodes"] if n["id"] == "n_ba") == restored_ba
    graph["edges"].append({"id": "unsafe", "source": "start", "target": "n_devops"})
    assert (await client.put("/api/workflow-templates/add_feature", json={"graph": graph})).status_code == 422
