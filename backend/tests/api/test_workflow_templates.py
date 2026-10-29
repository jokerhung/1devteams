import httpx

from tests.api.conftest import project


async def test_create_blank_template_and_use_in_project(client):
    response = await client.post(
        "/api/workflow-templates", json={"name": "  New process  ", "description": "Our own workflow"}
    )
    assert response.status_code == 201, response.text
    template = response.json()
    assert template["id"].startswith("wf_") and template["name"] == "New process"
    assert not template["builtin"]
    assert [n["type"] for n in template["graph"]["nodes"]] == ["start", "end"]
    catalog = (await client.get("/api/workflow-templates")).json()
    assert (
        len(catalog) == 5
        and next(t for t in catalog if t["id"] == template["id"])["description"] == "Our own workflow"
    )
    entity = await project(client)
    created = await client.post(
        f"/api/projects/{entity['id']}/workflows",
        json={"name": "From custom", "ticket_prefix": "CUSTOM", "template": template["id"]},
    )
    assert created.status_code == 201, created.text
    assert created.json()["graph"] == template["graph"]


async def test_clone_edit_and_bind_custom_template_without_changing_source_or_snapshots(client):
    entity = await project(client, seeded=True)
    original = next(
        t for t in (await client.get("/api/workflow-templates")).json() if t["id"] == "bugfix_default"
    )
    template = (
        await client.post(
            "/api/workflow-templates", json={"name": "Custom bugfix", "source_template": "bugfix_default"}
        )
    ).json()
    key = template["id"]
    created = await client.post(
        f"/api/projects/{entity['id']}/workflows",
        json={"name": "Snapshot", "ticket_prefix": "COPY", "template": key},
    )
    assert created.status_code == 201, created.text
    saved_workflow = created.json()
    graph = template["graph"]
    node = next(n for n in graph["nodes"] if n["id"] == "n_ba")
    assert node["data"]["agent_role"] == "BA" and node["data"]["agent_handle"] == "@ba"
    node["data"]["instructions"] = "Custom instruction"
    response = await client.put(f"/api/workflow-templates/{key}", json={"graph": graph})
    assert response.status_code == 200, response.text
    catalog = (await client.get("/api/workflow-templates")).json()
    assert next(t for t in catalog if t["id"] == "bugfix_default") == original
    assert next(t for t in catalog if t["id"] == key)["name"] == "Custom bugfix"
    unchanged = (await client.get(f"/api/workflows/{saved_workflow['id']}")).json()
    assert unchanged["graph"] == saved_workflow["graph"]
    empty = await project(client, "Empty")
    scoped = next(
        t
        for t in (await client.get(f"/api/workflow-templates?project_id={empty['id']}")).json()
        if t["id"] == key
    )
    assert all(not n["data"].get("agent_id") for n in scoped["graph"]["nodes"] if n["type"] == "agent")
    copied = await client.post(
        "/api/workflow-templates", json={"name": "Copy of custom", "source_template": key}
    )
    assert copied.status_code == 201, copied.text
    assert (
        next(n for n in copied.json()["graph"]["nodes"] if n["id"] == "n_ba")["data"]["instructions"]
        == "Custom instruction"
    )


async def test_template_creation_validation_and_member_permissions(client):
    for body in [
        {"name": "   "},
        {"name": "X", "source_template": "invalid"},
        {"name": "X", "source_template": "wf_" + "0" * 32},
    ]:
        assert (await client.post("/api/workflow-templates", json=body)).status_code == 422
    await client.post(
        "/api/users",
        json={"email": "member@example.com", "display_name": "Member", "password": "Password123!"},
    )
    token = (
        await client.post("/api/auth/login", json={"email": "member@example.com", "password": "Password123!"})
    ).json()["access_token"]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as member:
        assert (await member.post("/api/workflow-templates", json={"name": "No"})).status_code == 403
