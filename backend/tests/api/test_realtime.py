from fastapi.testclient import TestClient

from app.core.config import Settings
from app.db.models import Ticket
from app.main import create_app


def test_authenticated_websocket_and_notification_delivery(tmp_path):
    app = create_app(
        Settings(
            jwt_secret="ws-secret",
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'ws.db'}",
            data_dir=tmp_path / "data",
            bootstrap_admin_email="ws@example.com",
            bootstrap_admin_password="Password123!",
        )
    )
    with TestClient(app) as client:
        login = client.post(
            "/api/auth/login", json={"email": "ws@example.com", "password": "Password123!"}
        ).json()
        with client.websocket_connect("/ws/users/me") as socket:
            socket.send_json({"token": login["access_token"]})
            assert socket.receive_json()["event_type"] == "connected"

            async def emit():
                await app.state.event_bus.publish(
                    f"users/{login['user']['id']}", {"event_type": "notification_created", "id": "test"}
                )

            client.portal.call(emit)
            assert socket.receive_json() == {"event_type": "notification_created", "id": "test"}
        with client.websocket_connect("/ws/users/me") as socket:
            socket.send_json({"token": "bad"})
            assert socket.receive()["code"] == 1008


async def test_notification_and_file_isolation(client):
    from app.services.notification_service import create_gate
    from tests.api.conftest import ticket

    item = await ticket(client)
    attachment = (
        await client.post(
            f"/api/tickets/{item['id']}/attachments", files={"file": ("file.txt", b"text", "text/plain")}
        )
    ).json()
    async with client.app.state.db_session() as db:
        entity = await db.get(Ticket, item["id"])
        await create_gate(db, entity, kind="INPUT", node_id="gate", interrupt_seq=1, title="Input")
    notification = (await client.get("/api/notifications")).json()["items"][0]
    await client.post(
        "/api/users", json={"email": "other@example.com", "display_name": "Other", "password": "Password123!"}
    )
    login = (
        await client.post("/api/auth/login", json={"email": "other@example.com", "password": "Password123!"})
    ).json()
    headers = {"Authorization": "Bearer " + login["access_token"]}
    assert (await client.get(attachment["url"], headers=headers)).status_code == 403
    assert (
        await client.post(f"/api/notifications/{notification['id']}/read", headers=headers)
    ).status_code == 404
    assert (await client.get("/api/notifications", headers=headers)).json()["total"] == 0
