import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select, update

from app.db.models import Attachment, ChatHistoryEntry, Notification, Ticket, TicketMessage, WorkflowVersion
from tests.api.conftest import project


@pytest.mark.parametrize("scope", ["tickets", "workflows", "projects"])
async def test_permanent_deletion_cleans_children_and_files(client, monkeypatch, scope):
    entity = await project(client, seeded=True)
    pid, wid = entity["id"], entity["workflow"]["id"]
    ticket = (
        await client.post(f"/api/workflows/{wid}/tickets", json={"title": "Delete me", "auto_start": False})
    ).json()["ticket"]
    tid = ticket["id"]
    uploaded = await client.post(
        f"/api/tickets/{tid}/attachments", files={"file": ("note.txt", b"test", "text/plain")}
    )
    assert uploaded.status_code == 201, uploaded.text
    root = client.app.state.settings.data_dir
    event_folder = root / "blobs/events" / tid
    event_folder.mkdir(parents=True)
    (event_folder / "event.json").write_text("{}")
    async with client.app.state.db_session() as db:
        paths = list(
            (await db.scalars(select(Attachment.storage_path).where(Attachment.ticket_id == tid))).all()
        )
        db.add(ChatHistoryEntry(ticket_id=tid, entry_key="test", first_seq=1, last_seq=1, payload={}))
        db.add(
            Notification(
                user_id=client.owner["id"],
                project_id=pid,
                workflow_id=wid,
                ticket_id=tid,
                type="INFO",
                title="Test",
                gate_key="delete-test",
            )
        )
        await db.commit()
    cleanup = AsyncMock()
    monkeypatch.setattr(client.app.state.ticket_runner.checkpointer, "adelete_thread", cleanup)
    identifier = {"tickets": tid, "workflows": wid, "projects": pid}[scope]
    endpoint = f"/api/{scope}/{identifier}"
    if scope != "tickets":
        preview = (await client.get(endpoint + "/deletion-preview")).json()
        assert preview == {"ticket_count": 1, "workflow_count": int(scope == "projects")}
        assert (await client.delete(endpoint)).status_code == 409
        assert (await client.get(f"/api/tickets/{tid}")).status_code == 200
    response = await client.delete(endpoint + ("?cascade=true" if scope != "tickets" else ""))
    assert response.status_code == 200, response.text
    assert (await client.get(endpoint)).status_code == 404
    assert (await client.get(f"/api/tickets/{tid}")).status_code == 404
    async with client.app.state.db_session() as db:
        for model in [Attachment, TicketMessage, ChatHistoryEntry, Notification]:
            assert await db.scalar(select(func.count()).select_from(model).where(model.ticket_id == tid)) == 0
        if scope != "tickets":
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(WorkflowVersion)
                    .where(WorkflowVersion.workflow_id == wid)
                )
                == 0
            )
    from pathlib import Path

    assert not any(await asyncio.gather(*(asyncio.to_thread(Path(path).exists) for path in paths)))
    assert not event_folder.exists()
    cleanup.assert_awaited_once_with(tid)
    assert client.workspace.exists()
    if scope != "projects":
        assert (await client.get(f"/api/projects/{pid}")).status_code == 200
    if scope == "tickets":
        assert (await client.get(f"/api/workflows/{wid}")).status_code == 200


async def test_deleting_workflow_preserves_other_workflow_and_agents(client):
    entity = await project(client, seeded=True)
    pid, wid = entity["id"], entity["workflow"]["id"]
    agents = (await client.get("/api/agents")).json()
    sibling = (
        await client.post(f"/api/workflows/{wid}/duplicate", json={"name": "Keep", "ticket_prefix": "KEEP"})
    ).json()
    sid = sibling["id"]
    assert (await client.post(f"/api/workflows/{sid}/publish")).status_code == 200
    kept_ticket = (
        await client.post(f"/api/workflows/{sid}/tickets", json={"title": "Keep", "auto_start": False})
    ).json()["ticket"]
    assert (await client.delete(f"/api/workflows/{wid}?cascade=true")).status_code == 200
    assert (await client.get(f"/api/projects/{pid}")).status_code == 200
    assert (await client.get(f"/api/workflows/{sid}")).status_code == 200
    assert (await client.get(f"/api/tickets/{kept_ticket['id']}")).status_code == 200
    assert (await client.get("/api/agents")).json() == agents


@pytest.mark.parametrize("status", ["RUNNING", "WAITING_USER_INPUT", "WAITING_USER_CONFIRM"])
async def test_running_ticket_blocks_all_scope_deletions(client, status):
    entity = await project(client, seeded=True)
    pid, wid = entity["id"], entity["workflow"]["id"]
    tid = (
        await client.post(f"/api/workflows/{wid}/tickets", json={"title": "Busy", "auto_start": False})
    ).json()["ticket"]["id"]
    async with client.app.state.db_session() as db:
        await db.execute(update(Ticket).where(Ticket.id == tid).values(status=status))
        await db.commit()
    for path in [f"tickets/{tid}", f"workflows/{wid}", f"projects/{pid}"]:
        assert (await client.delete(f"/api/{path}?cascade=true")).status_code == 409
        assert (await client.get(f"/api/{path}")).status_code == 200


async def test_ticket_action_lock_blocks_deletion(client):
    entity = await project(client, seeded=True)
    wid = entity["workflow"]["id"]
    tid = (
        await client.post(f"/api/workflows/{wid}/tickets", json={"title": "Busy", "auto_start": False})
    ).json()["ticket"]["id"]
    lock = client.app.state.ticket_runner.action_locks.setdefault(tid, asyncio.Lock())
    async with lock:
        assert (await client.delete(f"/api/tickets/{tid}")).status_code == 409
    assert (await client.delete(f"/api/tickets/{tid}")).status_code == 200
