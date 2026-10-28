import asyncio
import subprocess
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

# isort: split
from app.acp import pty_manager
from app.core.config import Settings
from app.db.models import TerminalAudit
from app.main import create_app
from app.ws import terminal_ws


@pytest.fixture
def terminal_client(tmp_path, monkeypatch):
    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    app = create_app(
        Settings(
            _env_file=None,
            jwt_secret="workspace-terminal-test",
            database_url="sqlite+aiosqlite:///" + (tmp_path / "app.db").as_posix(),
            checkpoint_db=str(tmp_path / "checkpoint.db"),
            data_dir=tmp_path / "data",
            allowed_workspace_roots=f"{first};{second}",
            bootstrap_admin_email="owner@example.com",
            bootstrap_admin_password="Password123!",
            enable_remote_terminal=True,
        )
    )
    clock = iter(range(0, 10000, 16))
    monkeypatch.setattr(terminal_ws, "time", SimpleNamespace(monotonic=lambda: next(clock)))
    with TestClient(app) as client:
        token = client.post(
            "/api/auth/login",
            json={
                "email": "owner@example.com",
                "password": "Password123!",
            },
        ).json()["access_token"]
        client.headers["Authorization"] = "Bearer " + token
        calls, writes, detached = [], [], []

        async def attach(*args, **kwargs):
            calls.append((args, kwargs))
            return SimpleNamespace(
                id=str(uuid4()),
                initial_seq=0,
                reset=True,
                initial_frames=[],
                queue=asyncio.Queue(),
                process=SimpleNamespace(write=writes.append, setwinsize=lambda *args: None),
            )

        async def detach(session):
            detached.append(session)

        monkeypatch.setattr(app.state.pty_manager, "attach", attach)
        monkeypatch.setattr(app.state.pty_manager, "detach", detach)
        yield client, app, first, second, calls, writes, detached


def test_workspace_terminal_uses_first_allowed_root_and_accepts_input(terminal_client):
    client, app, first, second, calls, writes, detached = terminal_client
    response = client.get("/api/workspace-terminal")
    assert response.status_code == 200
    assert response.json() == {"enabled": True, "workspace": str(first.resolve())}
    with client.websocket_connect("/ws/workspace-terminal?root=" + str(second)) as socket:
        assert socket.receive_json()["type"] == "ready"
        assert socket.receive_json()["type"] == "synced"
        socket.send_json({"type": "input", "data": "pwd\r"})
        socket.send_json({"type": "resize", "cols": 1, "rows": 1})
        frame = socket.receive_json()
        while frame["type"] == "ping":
            frame = socket.receive_json()
        assert frame["type"] == "error"
    assert calls[0][0][2] == first.resolve()
    assert calls[0][0][1] == f"workspace:{first.resolve()}"
    assert calls[0][1]["workspace_only"] is True
    assert writes == ["pwd\r"]
    assert len(detached) == 1


def test_project_terminal_keeps_its_own_workspace(terminal_client):
    client, app, first, second, calls, writes, detached = terminal_client
    subprocess.run(["git", "init", "-b", "main", str(second)], check=True, capture_output=True)
    response = client.post(
        "/api/projects",
        json={
            "name": "Project workspace",
            "workspace_path": str(second),
            "default_branch": "main",
        },
    )
    assert response.status_code == 201, response.text
    project_id = response.json()["id"]
    assert client.get(f"/api/projects/{project_id}/terminal").json()["enabled"] is True
    with client.websocket_connect(f"/ws/terminal/{project_id}") as socket:
        assert socket.receive_json()["type"] == "ready"
        assert socket.receive_json()["type"] == "synced"
        socket.send_json({"type": "resize", "cols": 1, "rows": 1})
        frame = socket.receive_json()
        while frame["type"] == "ping":
            frame = socket.receive_json()
        assert frame["type"] == "error"
    assert calls[0][0][1] == project_id
    assert calls[0][0][2] == second.resolve()
    assert calls[0][1]["workspace_only"] is False


def test_workspace_terminal_rejects_disabled_origin_and_member(terminal_client):
    client, app, first, second, calls, writes, detached = terminal_client
    with client.websocket_connect(
        "/ws/workspace-terminal", headers={"Origin": "https://untrusted.example"}
    ) as socket:
        assert socket.receive_json()["data"] == "Origin not allowed"
    app.state.settings.enable_remote_terminal = False
    assert client.get("/api/workspace-terminal").json()["enabled"] is False
    with client.websocket_connect("/ws/workspace-terminal") as socket:
        assert "tắt" in socket.receive_json()["data"]
    app.state.settings.enable_remote_terminal = True
    response = client.post(
        "/api/users",
        json={
            "email": "member@example.com",
            "display_name": "Member",
            "password": "Password123!",
        },
    )
    assert response.status_code == 201
    token = client.post(
        "/api/auth/login",
        json={
            "email": "member@example.com",
            "password": "Password123!",
        },
    ).json()["access_token"]
    client.headers["Authorization"] = "Bearer " + token
    assert client.get("/api/workspace-terminal").status_code == 403
    with client.websocket_connect("/ws/workspace-terminal") as socket:
        assert "quản trị viên" in socket.receive_json()["data"]
    assert calls == []
    client.headers.pop("Authorization")
    assert client.get("/api/workspace-terminal").status_code == 401


@pytest.mark.parametrize("change", ["root", "disabled"])
def test_workspace_terminal_rechecks_allowed_root_and_enablement(terminal_client, change):
    client, app, first, second, calls, writes, detached = terminal_client
    with client.websocket_connect("/ws/workspace-terminal") as socket:
        assert socket.receive_json()["type"] == "ready"
        assert socket.receive_json()["type"] == "synced"
        if change == "root":
            app.state.settings.allowed_workspace_roots = str(second)
        else:
            app.state.settings.enable_remote_terminal = False
        socket.send_json({"type": "input", "data": "pwd\r"})
        assert socket.receive_json()["type"] == "error"
    assert writes == []


def test_workspace_terminal_missing_first_root_does_not_fallback(terminal_client):
    client, app, first, second, calls, writes, detached = terminal_client
    first.rmdir()
    assert client.get("/api/workspace-terminal").status_code == 400
    with client.websocket_connect("/ws/workspace-terminal") as socket:
        assert "đầu tiên" in socket.receive_json()["data"]
    assert calls == []


async def test_workspace_terminal_audit_does_not_need_project(client, monkeypatch):
    class Process:
        def read(self, size):
            raise EOFError

        def close(self, force=False):
            pass

    monkeypatch.setattr(pty_manager, "spawn", lambda *args: Process())
    manager = client.app.state.pty_manager
    workspace = client.workspace.resolve()
    session = await manager.attach(
        client.owner["id"], f"workspace:{workspace}", workspace, 30, 120, workspace_only=True
    )
    assert session.workspace_only
    await manager.audit_event(session, "input", "pwd")
    await manager.detach(session)
    await manager.close()
    events = (await client.get("/api/audit")).json()
    assert {event["action"] for event in events} >= {
        "terminal.workspace.open",
        "terminal.workspace.input",
        "terminal.workspace.close",
    }
    assert all(event["target"] == str(workspace) for event in events)
    async with client.app.state.db_session() as db:
        assert await db.scalar(select(func.count()).select_from(TerminalAudit)) == 0
