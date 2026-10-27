import httpx

from app.services.workspace_settings import WorkspaceSettings


async def test_workspace_settings_apply_immediately_and_survive_reload(client, tmp_path):
    outside = tmp_path / "other-workspace"
    outside.mkdir()
    path = str(client.workspace)
    response = await client.put("/api/settings/workspaces", json={"roots": [path, path + "/."]})
    assert response.status_code == 200, response.text
    assert response.json() == {"roots": [path]}
    assert (await client.get("/api/settings/workspaces")).json() == {"roots": [path]}
    assert (
        await client.get("/api/projects/browse-workspace", params={"path": str(outside)})
    ).status_code == 403
    response = await client.put("/api/settings/workspaces", json={"roots": [path, str(outside)]})
    assert response.status_code == 200, response.text
    assert (
        await client.get("/api/projects/browse-workspace", params={"path": str(outside)})
    ).status_code == 200
    validation = await client.post("/api/projects/validate-workspace", json={"path": str(outside)})
    assert validation.json()["within_allowed_roots"] is True
    fresh = client.app.state.settings.model_copy(update={"allowed_workspace_roots": path})
    reloaded = WorkspaceSettings(fresh)
    await reloaded.load()
    assert reloaded.roots() == [path, str(outside)]


async def test_invalid_workspace_settings_preserve_existing_policy(client, tmp_path, monkeypatch):
    before = (await client.get("/api/settings/workspaces")).json()
    for roots in ([], ["relative/path"], [str(tmp_path / "missing")], ["   "], [str(tmp_path) + ";other"]):
        response = await client.put("/api/settings/workspaces", json={"roots": roots})
        assert response.status_code == 422, response.text
        assert (await client.get("/api/settings/workspaces")).json() == before

    def fail_write(*args):
        raise PermissionError("Read-only settings location")

    monkeypatch.setattr("app.services.workspace_settings.os.replace", fail_write)
    response = await client.put("/api/settings/workspaces", json={"roots": [str(client.workspace)]})
    assert response.status_code == 503
    assert (await client.get("/api/settings/workspaces")).json() == before


async def test_workspace_settings_require_admin(client):
    response = await client.post(
        "/api/users",
        json={
            "email": "member@example.com",
            "display_name": "Member",
            "password": "Password123!",
        },
    )
    assert response.status_code == 201
    login = await client.post(
        "/api/auth/login", json={"email": "member@example.com", "password": "Password123!"}
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app),
        base_url="http://test",
        headers={"Authorization": "Bearer " + login.json()["access_token"]},
    ) as member:
        assert (await member.get("/api/settings/workspaces")).status_code == 403
        assert (
            await member.put("/api/settings/workspaces", json={"roots": [str(client.workspace)]})
        ).status_code == 403
