"""In-process event bus. User and ticket websocket consumers can subscribe in later phases."""

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, update

from app.core.config import Settings
from app.db.models import Attachment, Ticket, TicketMessage


class EventBus:
    def __init__(self, sessions=None) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self.sessions = sessions
        self._locks: dict[str, asyncio.Lock] = {}
        self.settings: Settings | None = None

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        if self.sessions and channel.startswith("tickets/"):
            ticket_id = channel.split("/", 1)[1]
            if self.settings:
                from app.acp.security import scrub_data

                event = scrub_data(event)
                encoded = json.dumps(event, ensure_ascii=False)
                if (
                    len(encoded) > self.settings.max_event_chars
                    and event.get("event_type") != "agent_turn_end"
                ):
                    folder = self.settings.data_dir.resolve() / "blobs/events" / ticket_id
                    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
                    blob_id = str(uuid4())
                    await asyncio.to_thread(
                        (folder / (blob_id + ".json")).write_text, encoded, encoding="utf-8"
                    )
                    event = {
                        k: event[k]
                        for k in (
                            "event_type",
                            "sender_type",
                            "sender_name",
                            "sender_id",
                            "run_id",
                            "node_id",
                        )
                        if k in event
                    }
                    event["content"] = encoded[: self.settings.max_event_chars // 2] + "\n[truncated]"
                    event["metadata"] = {
                        "truncated": True,
                        "full_output_url": f"/api/tickets/{ticket_id}/event-blobs/{blob_id}",
                    }
            async with self._locks.setdefault(ticket_id, asyncio.Lock()):
                async with self.sessions() as db:
                    from app.services.ticket_service import add_message

                    # Repair counters on databases imported from an earlier version.
                    ticket = await db.get(Ticket, ticket_id)
                    if ticket is None:
                        return
                    maximum = (
                        await db.scalar(
                            select(func.max(TicketMessage.seq)).where(TicketMessage.ticket_id == ticket_id)
                        )
                        or 0
                    )
                    await db.execute(
                        update(Ticket)
                        .where(Ticket.id == ticket_id, Ticket.next_message_seq <= maximum)
                        .values(next_message_seq=maximum + 1)
                    )
                    row = await add_message(
                        db,
                        ticket_id,
                        content=event.get("content", ""),
                        sender_type=event.get("sender_type", "SYSTEM"),
                        sender_name=event.get("sender_name", "System"),
                        sender_id=event.get("sender_id"),
                        event_type=event.get("event_type", "log"),
                        metadata=event.get("metadata", {})
                        | {
                            k: v
                            for k, v in event.items()
                            if k
                            not in {
                                "content",
                                "sender_type",
                                "sender_name",
                                "sender_id",
                                "event_type",
                                "metadata",
                                "run_id",
                                "node_id",
                                "ticket_id",
                            }
                        },
                        run_id=event.get("run_id"),
                        node_id=event.get("node_id"),
                    )
                    if row.event_type == "browser_report":
                        identifiers = [item["id"] for item in row.event_metadata.get("attachments", [])]
                        if identifiers:
                            await db.execute(
                                update(Attachment)
                                .where(
                                    Attachment.id.in_(identifiers),
                                    Attachment.ticket_id == ticket_id,
                                    Attachment.message_id.is_(None),
                                )
                                .values(message_id=row.id)
                            )
                    await db.commit()
                    event = message_event(row)
                await self.broadcast(channel, event)
            return
        await self.broadcast(channel, event)

    async def broadcast(self, channel: str, event: dict[str, Any]) -> None:
        for queue in tuple(self._subscribers.get(channel, ())):
            if queue.full():
                # Drop the connection explicitly. Client must reconnect/replay from its last seq.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"event_type": "slow_consumer"})
                self._subscribers[channel].discard(queue)
            else:
                queue.put_nowait(event.copy())

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        subscribers = self._subscribers.setdefault(channel, set())
        subscribers.add(queue)
        try:
            yield queue
        finally:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(channel, None)


def message_event(row: TicketMessage) -> dict[str, Any]:
    return jsonable_encoder(
        {
            "id": row.id,
            "ticket_id": row.ticket_id,
            "seq": row.seq,
            "run_id": row.run_id,
            "node_id": row.node_id,
            "sender_type": row.sender_type,
            "sender_id": row.sender_id,
            "sender_name": row.sender_name,
            "event_type": row.event_type,
            "content": row.content,
            "metadata": row.event_metadata,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }
    )
