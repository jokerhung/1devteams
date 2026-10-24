from uuid import uuid4

from app.services.ticket_service import add_message
from tests.api.conftest import ticket


async def test_reverse_history_keeps_whole_turns_and_stable_snapshot(client):
    item = await ticket(client)
    tid = item["id"]
    async with client.app.state.db_session() as db:
        for index in range(23):
            run = str(uuid4())
            for kind, content in [
                ("agent_turn_start", ""),
                ("message_chunk", f"part-{index}"),
                ("agent_turn_end", f"answer-{index}"),
            ]:
                await add_message(
                    db,
                    tid,
                    sender_type="AGENT",
                    sender_name="@leader",
                    event_type=kind,
                    content=content,
                    run_id=run,
                )
        await db.commit()
    response = await client.get(f"/api/tickets/{tid}/history?limit=10")
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["has_more"]
    assert len(page["groups"]) == 10
    assert page["groups"][0]["content"] == "answer-13"
    assert page["groups"][-1]["content"] == "answer-22"
    watermark = page["last_seq"]
    collected = list(page["groups"])
    async with client.app.state.db_session() as db:
        await add_message(db, tid, sender_type="USER", content="new after snapshot")
        await db.commit()
    while page["has_more"]:
        response = await client.get(
            f"/api/tickets/{tid}/history?limit=10&before_seq={page['before_seq']}&through_seq={watermark}"
        )
        assert response.status_code == 200, response.text
        older = response.json()
        assert all(group["historySeq"] < page["before_seq"] for group in older["groups"])
        collected = older["groups"] + collected
        page = older
    assert len(collected) == 24
    assert len({group["id"] for group in collected}) == 24
    assert [group["content"] for group in collected if group["type"] == "turn"] == [
        f"answer-{i}" for i in range(23)
    ]
    assert (await client.get(f"/api/tickets/{tid}/history?limit=11")).status_code == 422


async def test_summary_omits_details_preserves_full_answer_and_raw_events(client):
    from sqlalchemy import select

    from app.db.models import ChatHistoryEntry

    item = await ticket(client)
    tid, run = item["id"], str(uuid4())
    full_answer = "Full answer " * 12000
    async with client.app.state.db_session() as db:
        for kind, text in [
            ("agent_turn_start", ""),
            ("message_chunk", "partial"),
            ("terminal_output", "private-terminal-detail" * 200),
            ("file_edit", "private-diff-detail"),
            ("log", "private-log-detail"),
            ("agent_turn_end", full_answer),
        ]:
            await add_message(
                db, tid, sender_type="AGENT", sender_name="@leader", run_id=run, event_type=kind, content=text
            )
        waiting = await add_message(
            db,
            tid,
            event_type="gate_waiting",
            content="",
            metadata={"gate_key": "gate", "kind": "human_confirm"},
        )
        await add_message(
            db, tid, event_type="gate_resolved", content="", metadata={"gate_key": "gate", "approved": True}
        )
        await db.commit()
        entry = await db.scalar(select(ChatHistoryEntry).where(ChatHistoryEntry.entry_key == "run:" + run))
        assert entry.payload["content"] == full_answer
    response = await client.get(f"/api/tickets/{tid}/history")
    group = next(group for group in response.json()["groups"] if group["type"] == "turn")
    assert group["content"] == full_answer
    assert group["gate"]["resolved"]["approved"]
    historical = (await client.get(f"/api/tickets/{tid}/history?through_seq={waiting.seq}")).json()
    old_gate = next(group for group in historical["groups"] if group["type"] == "turn")["gate"]
    assert "resolved" not in old_gate
    assert (
        group["tools"] == {} and group["files"] == {} and group["terminals"] == [] and group["logLines"] == []
    )
    assert "private-terminal-detail" not in response.text and "private-diff-detail" not in response.text
    details = (await client.get(f"/api/tickets/{tid}/turns/{run}/details")).json()
    assert len(details) == 6
    assert details[-1]["content"] == full_answer
    assert details[2]["content"].startswith("private-terminal-detail")
    from app.db.models import TicketMessage
    from app.ws.ticket_ws import chat_event

    async with client.app.state.db_session() as db:
        terminal = await db.scalar(
            select(TicketMessage).where(
                TicketMessage.ticket_id == tid,
                TicketMessage.event_type == "terminal_output",
            )
        )
        compact = chat_event(terminal, True)
        assert compact["event_type"] == "detail_available" and compact["content"] == ""
        assert compact["seq"] == terminal.seq
        assert chat_event(terminal, False)["content"].startswith("private-terminal-detail")


async def test_backfill_is_idempotent_and_active_turn_exposes_only_text(client):
    from sqlalchemy import delete, func, select

    from app.db.models import ChatHistoryEntry
    from app.services.chat_history import backfill_chat_history

    item = await ticket(client)
    tid, run = item["id"], str(uuid4())
    async with client.app.state.db_session() as db:
        for kind, text in [
            ("agent_turn_start", ""),
            ("message_chunk", "live answer"),
            ("terminal_output", "secret-detail"),
        ]:
            await add_message(
                db,
                tid,
                sender_type="AGENT",
                sender_name="@developer",
                run_id=run,
                event_type=kind,
                content=text,
            )
        await db.execute(delete(ChatHistoryEntry).where(ChatHistoryEntry.ticket_id == tid))
        await db.commit()
        await backfill_chat_history(db)
        count = await db.scalar(select(func.count()).select_from(ChatHistoryEntry))
        await backfill_chat_history(db)
        assert await db.scalar(select(func.count()).select_from(ChatHistoryEntry)) == count
    response = await client.get(f"/api/tickets/{tid}/history")
    group = response.json()["groups"][-1]
    assert group["content"] == "live answer"
    assert "secret-detail" not in response.text
    assert "endedAt" not in group


async def test_final_answer_is_not_truncated_by_event_limit(client):
    item = await ticket(client)
    tid, run = item["id"], str(uuid4())
    client.app.state.settings.max_event_chars = 1024
    answer = "complete answer " * 1000
    await client.app.state.event_bus.publish(
        f"tickets/{tid}",
        {
            "event_type": "agent_turn_end",
            "sender_type": "AGENT",
            "sender_name": "@leader",
            "run_id": run,
            "content": answer,
        },
    )
    response = await client.get(f"/api/tickets/{tid}/history")
    assert response.json()["groups"][-1]["content"] == answer
