from tests.api.conftest import project


async def test_allowed_folders_list_and_read_without_project(client):
    root = client.workspace
    client.app.state.settings.allowed_workspace_roots = str(root)
    (root / "notes").mkdir()
    (root / "notes" / "readme.md").write_text("# Allowed folder\n", encoding="utf-8", newline="\n")
    (root / ".env").write_text("SECRET=hidden", encoding="utf-8")
    response = await client.get("/api/projects/workspace-files")
    assert response.status_code == 200
    assert response.json()["entries"] == [{"name": str(root), "path": str(root), "kind": "directory"}]
    response = await client.get("/api/projects/workspace-files", params={"root": str(root)})
    assert response.status_code == 200
    assert response.json()["entries"] == [{"name": "notes", "path": "notes", "kind": "directory"}]
    response = await client.get(
        "/api/projects/workspace-file", params={"root": str(root), "path": "notes/readme.md"}
    )
    assert response.status_code == 200
    assert response.json()["content"] == "# Allowed folder\n"
    entity = await project(client)
    response = await client.get(f"/api/projects/{entity['id']}/files", params={"path": "notes"})
    assert response.status_code == 200
    assert response.json()["entries"][0]["name"] == "readme.md"


async def test_allowed_folder_boundaries_and_authentication(client):
    root = client.workspace
    client.app.state.settings.allowed_workspace_roots = str(root)
    (root / ".env").write_text("SECRET=hidden", encoding="utf-8")
    for endpoint, params in [
        ("workspace-files", {"root": str(root.parent)}),
        ("workspace-files", {"root": str(root), "path": ".."}),
        ("workspace-files", {"path": str(root)}),
        ("workspace-file", {"root": str(root), "path": ".env"}),
        ("workspace-file", {"root": str(root), "path": "../outside.txt"}),
        ("workspace-file", {"root": str(root), "path": str(root / "absolute.txt")}),
    ]:
        response = await client.get(f"/api/projects/{endpoint}", params=params)
        assert response.status_code == 403, response.text
    client.headers.pop("Authorization")
    assert (await client.get("/api/projects/workspace-files")).status_code == 401
