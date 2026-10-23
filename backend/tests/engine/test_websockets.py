import asyncio
import subprocess

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.events import EventBus
from app.main import create_app
from tests.engine.conftest import ScriptFactory


def test_ws_replay_live_actions_and_project_channel(tmp_path):
    repo = tmp_path / "workspace"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    app = create_app(
        Settings(
            jwt_secret="ws-test",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'db.sqlite'}",
            checkpoint_db=str(tmp_path / "cp.sqlite"),
            allowed_workspace_roots=str(tmp_path),
            data_dir=tmp_path / "data",
            bootstrap_admin_email="ws@example.com",
            bootstrap_admin_password="Password123!",
        )
    )
    with TestClient(app) as client:
        app.state.acp_pool.factory = ScriptFactory()
        token = client.post(
            "/api/auth/login", json={"email": "ws@example.com", "password": "Password123!"}
        ).json()["access_token"]
        client.headers["Authorization"] = "Bearer " + token
        project = client.post(
            "/api/projects",
            json={"name": "WS project", "workspace_path": str(repo), "default_branch": "main"},
        ).json()
        workflow = client.post(f"/api/projects/{project['id']}/seed-default").json()["workflow"]
        with client.websocket_connect(f"/ws/projects/{project['id']}") as project_ws:
            project_ws.send_json({"token": token})
            assert project_ws.receive_json()["type"] == "snapshot"
            ticket = client.post(
                f"/api/workflows/{workflow['id']}/tickets", json={"title": "WS ticket", "auto_start": False}
            ).json()["ticket"]
            assert project_ws.receive_json()["data"]["event_type"] == "ticket_created"
            tid = ticket["id"]
            for content in ["first", "second", "third"]:
                client.post(f"/api/tickets/{tid}/messages", json={"text": content})
            with client.websocket_connect(f"/ws/tickets/{tid}?after_seq=1") as ws:
                ws.send_json({"token": token})
                assert ws.receive_json()["state"]["status"] == "OPEN"
                assert [ws.receive_json()["data"]["content"] for _ in range(2)] == ["second", "third"]
                client.post(f"/api/tickets/{tid}/messages", json={"text": "fourth"})
                assert ws.receive_json()["data"]["seq"] == 4
                ws.send_json({"type": "action", "action": "cancel"})
                for _ in range(20):
                    frame = ws.receive_json()
                    if frame["type"] == "action_result":
                        assert frame["accepted"]
                        break
                else:
                    raise AssertionError("No action_result")
            with client.websocket_connect(
                f"/ws/tickets/{tid}?token=invalid", headers={"Authorization": "Bearer invalid"}
            ) as ws:
                assert ws.receive()["code"] == 1008


async def test_slow_consumer_and_persisted_sequence(engine_client):
    from tests.engine.test_engine import make_ticket

    client = engine_client
    ticket, _ = await make_ticket(client)
    bus = client.app.state.event_bus
    channel = f"tickets/{ticket['id']}"
    async with bus.subscribe(channel) as queue:
        await asyncio.gather(
            *(bus.publish(channel, {"event_type": "log", "content": str(i)}) for i in range(20))
        )
        events = [queue.get_nowait() for _ in range(20)]
        assert [e["seq"] for e in events] == list(range(1, 21))
    simple = EventBus()
    async with simple.subscribe("slow") as queue:
        for i in range(1001):
            await simple.publish("slow", {"index": i})
        assert queue.qsize() == 1 and (await queue.get())["event_type"] == "slow_consumer"
