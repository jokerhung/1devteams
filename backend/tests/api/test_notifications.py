from sqlalchemy import select

from app.db.models import Ticket
from app.services.notification_service import create_gate, resolve_gate
from tests.api.conftest import ticket


async def test_gate_idempotency_resolution_and_inbox(client):
    item = await ticket(client)
    maintainer = (
        await client.post(
            "/api/users",
            json={
                "email": "maintainer@example.com",
                "display_name": "Maintainer",
                "password": "Password123!",
            },
        )
    ).json()
    await client.post(
        f"/api/projects/{item['project_id']}/members",
        json={"member_type": "USER", "member_id": maintainer["id"], "project_role": "MAINTAINER"},
    )
    bus = client.app.state.event_bus
    async with bus.subscribe(f"users/{client.owner['id']}") as queue:
        async with client.app.state.db_session() as db:
            entity = await db.scalar(select(Ticket).where(Ticket.id == item["id"]))
            entity.status = "WAITING_USER_CONFIRM"
            created = await create_gate(
                db, entity, kind="CONFIRM", node_id="gate", interrupt_seq=1, title="Confirm", events=bus
            )
            assert len(created) == 2
            assert (await queue.get())["event_type"] == "notification_created"
            assert (
                await create_gate(
                    db, entity, kind="CONFIRM", node_id="gate", interrupt_seq=1, title="Confirm", events=bus
                )
                == []
            )
    assert (await client.get("/api/notifications/unread-count")).json() == {"open": 1}
    notification = (await client.get("/api/notifications")).json()["items"][0]
    assert notification["ticket"]["code"] == "#BUG-1"
    assert (await client.post(f"/api/notifications/{notification['id']}/read")).status_code == 200
    assert (await client.get("/api/notifications/unread-count")).json() == {"open": 1}
    async with client.app.state.db_session() as db:
        await resolve_gate(db, item["id"], "APPROVED", events=bus)
    assert (await client.get("/api/notifications/unread-count")).json() == {"open": 0}
    resolved = (await client.get("/api/notifications?status=resolved")).json()["items"]
    assert len(resolved) == 1 and resolved[0]["outcome"] == "APPROVED" and resolved[0]["resolved_at"]
    async with client.app.state.db_session() as db:
        entity = await db.get(Ticket, item["id"])
        await create_gate(db, entity, kind="INPUT", node_id="input", interrupt_seq=2, title="Input")
        await resolve_gate(db, item["id"], "CANCELLED")
    assert (await client.get("/api/notifications?status=resolved")).json()["total"] == 2


async def test_preferences_and_cursors(client):
    agent = (await client.get("/api/agents")).json()[0]
    assert (
        await client.put(
            "/api/me/preferences", json={"key": "default_mention_agent_id", "value": agent["id"]}
        )
    ).status_code == 200
    assert (await client.get("/api/me/preferences")).json()["default_mention_agent_id"] == agent["id"]
    assert (
        await client.put("/api/me/preferences", json={"key": "default_mention_agent_id", "value": "bad"})
    ).status_code == 422
    item = await ticket(client)
    async with client.app.state.db_session() as db:
        entity = await db.get(Ticket, item["id"])
        for sequence in range(3):
            await create_gate(
                db, entity, kind="INPUT", node_id="input", interrupt_seq=sequence, title="Question"
            )
    first = (await client.get("/api/notifications?limit=2")).json()
    second = (await client.get(f"/api/notifications?limit=2&cursor={first['next_cursor']}")).json()
    assert len(first["items"]) == 2 and len(second["items"]) == 1
    assert (await client.post("/api/notifications/read-all")).status_code == 200
    assert all(item["is_read"] for item in (await client.get("/api/notifications")).json()["items"])
