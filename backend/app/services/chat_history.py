"""Compact chat projections. Raw events are retained for replay and on-demand details."""

from copy import deepcopy
from typing import Any

from sqlalchemy import exists, select

from app.core.events import message_event
from app.db.models import ChatHistoryEntry, Ticket, TicketMessage


def project_events(rows):
    entries = {}
    latest: dict[str, Any] | None = None
    gates: dict[str, tuple[dict[str, Any], dict[str, Any] | None]] = {}
    for row in rows:
        event = message_event(row)
        kind, meta = row.event_type, row.event_metadata or {}
        if row.sender_type == "USER":
            entries[row.id] = {
                "first": row.seq,
                "last": row.seq,
                "payload": {
                    "type": "user",
                    "id": row.id,
                    "event": event,
                },
            }
            continue
        if kind == "gate_waiting":
            gate: dict[str, Any] = {
                "key": str(meta.get("gate_key", row.id)),
                "kind": str(meta.get("kind")),
                "payload": meta,
            }
            gates[gate["key"]] = (gate, latest)
            if latest:
                latest["payload"]["gate"] = gate
                latest["last"] = row.seq
            continue
        if kind == "gate_resolved":
            saved = gates.get(str(meta.get("gate_key")))
            if saved:
                gate, owner = saved
                gate["resolved"] = {
                    "approved": meta.get("approved"),
                    "user": meta.get("user"),
                    "at": event["created_at"],
                }
                if owner:
                    owner["last"] = row.seq
            if meta.get("approved") is False:
                entries[row.id] = {
                    "first": row.seq,
                    "last": row.seq,
                    "payload": {
                        "type": "system",
                        "id": row.id,
                        "at": event["created_at"],
                        "text": "🔄 Luồng đã quay lại @developer — "
                        + str(meta.get("feedback", "Yêu cầu sửa lại")),
                    },
                }
            continue
        if kind == "ticket_status":
            continue
        if row.run_id:
            key = "run:" + row.run_id
            if key not in entries:
                entries[key] = {
                    "first": row.seq,
                    "last": row.seq,
                    "payload": {
                        "type": "turn",
                        "id": row.run_id,
                        "agent": row.sender_name,
                        "nodeId": row.node_id,
                        "at": event["created_at"],
                        "content": "",
                        "thinking": "",
                        "tools": {},
                        "files": {},
                        "terminals": [],
                        "permissions": [],
                        "plans": [],
                        "logLines": [],
                        "detailsAvailable": True,
                        "detailCounts": {},
                    },
                }
            latest = entries[key]
            latest["last"] = row.seq
            payload = latest["payload"]
            if row.sender_type == "AGENT":
                payload["agent"] = row.sender_name
            if meta.get("model_effective") or meta.get("model"):
                payload["model"] = meta.get("model_effective") or meta["model"]
            if meta.get("runtime"):
                payload["runtime"] = meta["runtime"]
            if kind == "message_chunk":
                payload["content"] += row.content
            elif kind == "agent_turn_end":
                payload["content"] = row.content
                payload["endedAt"] = event["created_at"]
            elif kind == "error":
                payload["failed"] = True
            counts = payload["detailCounts"]
            counts[kind] = counts.get(kind, 0) + 1
        elif kind == "error" or (kind == "log" and row.content):
            entries[row.id] = {
                "first": row.seq,
                "last": row.seq,
                "payload": {
                    "type": "system",
                    "id": row.id,
                    "at": event["created_at"],
                    "text": row.content,
                },
            }
    return entries


async def record_summary(db, row):
    """Called in the raw event transaction; chunks need no extra projection writes."""
    if row.event_type in {"gate_waiting", "gate_resolved"}:
        # Gates can arrive after the turn is finalized. Rebuild only the compact projection.
        rows = (
            await db.scalars(
                select(TicketMessage)
                .where(TicketMessage.ticket_id == row.ticket_id)
                .order_by(TicketMessage.seq)
            )
        ).all()
        await save_entries(db, row.ticket_id, project_events(rows))
        return
    if row.run_id and row.event_type not in {"agent_turn_start", "agent_turn_end", "error"}:
        return
    if not row.run_id and row.sender_type != "USER" and row.event_type not in {"log", "error"}:
        return
    rows = [row]
    if row.run_id:
        rows = (
            await db.scalars(
                select(TicketMessage)
                .where(
                    TicketMessage.ticket_id == row.ticket_id,
                    TicketMessage.run_id == row.run_id,
                )
                .order_by(TicketMessage.seq)
            )
        ).all()
    await save_entries(db, row.ticket_id, project_events(rows))


async def save_entries(db, ticket_id, entries):
    for key, value in entries.items():
        entry = await db.scalar(
            select(ChatHistoryEntry).where(
                ChatHistoryEntry.ticket_id == ticket_id,
                ChatHistoryEntry.entry_key == key,
            )
        )
        if entry is None:
            entry = ChatHistoryEntry(
                ticket_id=ticket_id,
                entry_key=key,
                first_seq=value["first"],
                last_seq=value["last"],
                payload=value["payload"],
            )
            db.add(entry)
        else:
            payload = deepcopy(value["payload"])
            if "gate" in entry.payload and "gate" not in payload:
                payload["gate"] = entry.payload["gate"]
            entry.payload = payload
            entry.first_seq = value["first"]
            entry.last_seq = value["last"]


async def backfill_chat_history(db):
    """One atomic backfill per existing ticket, before accepting application traffic."""
    missing = (
        await db.scalars(select(Ticket.id).where(~exists().where(ChatHistoryEntry.ticket_id == Ticket.id)))
    ).all()
    for tid in missing:
        rows = (
            await db.scalars(
                select(TicketMessage).where(TicketMessage.ticket_id == tid).order_by(TicketMessage.seq)
            )
        ).all()
        await save_entries(db, tid, project_events(rows))
        await db.commit()
