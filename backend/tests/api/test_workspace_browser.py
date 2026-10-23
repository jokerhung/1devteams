async def test_workspace_browser_lists_directories_and_blocks_escape(client, workspace):
    root = workspace.parent
    (root / "folder-a").mkdir()
    (root / "file.txt").write_text("text")
    roots = await client.get("/api/projects/browse-workspace")
    assert roots.status_code == 200
    assert roots.json()["directories"] == [{"name": str(root), "path": str(root)}]
    response = await client.get("/api/projects/browse-workspace", params={"path": str(root)})
    assert response.status_code == 200
    data = response.json()
    assert data["path"] == str(root) and data["parent"] is None
    assert "folder-a" in [item["name"] for item in data["directories"]]
    assert "file.txt" not in [item["name"] for item in data["directories"]]
    response = await client.get("/api/projects/browse-workspace", params={"path": str(workspace)})
    assert response.json()["parent"] == str(root)
    assert (
        await client.get("/api/projects/browse-workspace", params={"path": str(root.parent)})
    ).status_code == 403
    assert (
        await client.get("/api/projects/browse-workspace", params={"path": "relative"})
    ).status_code == 422
    assert (
        await client.get("/api/projects/browse-workspace", params={"path": str(root / "missing")})
    ).status_code == 404
