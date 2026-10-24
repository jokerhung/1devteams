import asyncio
from contextlib import suppress
from uuid import UUID

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import ValidationError
from sqlalchemy import select

from app.core.deps import require_project
from app.core.events import message_event
from app.core.security import token_subject
from app.db.models import Ticket, TicketMessage, User
from app.schemas.ticket import Confirm, Reply

router = APIRouter()


def chat_event(row: TicketMessage, compact: bool):
    event = message_event(row)
    if (
        compact
        and row.sender_type != "USER"
        and row.event_type
        not in {
            "agent_turn_start",
            "agent_turn_end",
            "message_chunk",
            "error",
            "ticket_status",
            "gate_waiting",
            "gate_resolved",
        }
    ):
        # Keep every sequence for gap-free reconnect, without sending detail payloads.
        event.update(event_type="detail_available", content="", metadata={"kind": row.event_type})
    return event


async def authenticate(socket: WebSocket):
    authorization = socket.headers.get("authorization", "")
    token = (
        authorization[7:] if authorization.lower().startswith("bearer ") else socket.query_params.get("token")
    )
    if not token:
        frame = await asyncio.wait_for(socket.receive_json(), 5)
        token = frame.get("token") if isinstance(frame, dict) else None
    subject = token_subject(token, socket.app.state.settings) if isinstance(token, str) else None
    async with socket.app.state.db_session() as db:
        user = await db.get(User, str(UUID(subject))) if subject else None
    if user is None:
        raise ValueError("Unauthorized")
    return user, token


async def action(socket: WebSocket, tid: str, user: User, frame: dict):
    runner = socket.app.state.ticket_runner
    name = frame.get("action")
    if name in {"start", "cancel", "retry"}:
        await getattr(runner, name)(tid, user)
    elif name == "reply":
        body = Reply.model_validate({"text": frame.get("text")})
        await runner.reply(tid, body.text, user)
    elif name == "confirm":
        decision = Confirm.model_validate(
            {"approved": frame.get("approved"), "feedback": frame.get("feedback")}
        )
        await runner.confirm(tid, decision.approved, decision.feedback, user)
    else:
        raise ValueError("Unsupported action")
    await socket.send_json({"type": "action_result", "action": name, "accepted": True})


async def channel_socket(socket: WebSocket, identifier: str, ticket_channel: bool):
    await socket.accept()
    receive_task = event_task = None
    try:
        user, token = await authenticate(socket)
        async with socket.app.state.db_session() as db:
            ticket = await db.get(Ticket, identifier) if ticket_channel else None
            if ticket_channel and ticket is None:
                raise ValueError("Not found")
            pid = ticket.project_id if ticket else identifier
            await require_project(db, pid, user)
        channel = f"tickets/{identifier}" if ticket_channel else f"projects/{identifier}"
        after = max(0, int(socket.query_params.get("after_seq", "0")))
        compact = socket.query_params.get("view") == "chat"
        bus = socket.app.state.event_bus
        async with bus.subscribe(channel) as queue:
            if ticket_channel:
                state = await socket.app.state.ticket_runner.state(identifier)
                await socket.send_json({"type": "snapshot", "state": state})
                # Subscribe before replay; dedupe queue events by seq to close the connect race.
                while True:
                    async with socket.app.state.db_session() as db:
                        rows = (
                            await db.scalars(
                                select(TicketMessage)
                                .where(TicketMessage.ticket_id == identifier, TicketMessage.seq > after)
                                .order_by(TicketMessage.seq)
                                .limit(500)
                            )
                        ).all()
                    for row in rows:
                        await socket.send_json({"type": "event", "data": chat_event(row, compact)})
                        after = row.seq
                    if len(rows) < 500:
                        break
            else:
                await socket.send_json({"type": "snapshot", "state": {"project_id": pid}})
            receive_task = asyncio.create_task(socket.receive_json())
            event_task = asyncio.create_task(queue.get())
            while True:
                if not token_subject(token, socket.app.state.settings):
                    raise ValueError("Expired token")
                async with socket.app.state.db_session() as db:
                    actor = await db.get(User, user.id)
                    if actor is None:
                        raise ValueError("Deleted user")
                    await require_project(db, pid, actor)
                done, _ = await asyncio.wait(
                    [receive_task, event_task], timeout=25, return_when=asyncio.FIRST_COMPLETED
                )
                if not done:
                    await socket.send_json({"type": "ping"})
                if event_task in done:
                    event = event_task.result()
                    if event.get("event_type") == "slow_consumer":
                        await socket.close(1013)
                        return
                    if not ticket_channel or event.get("seq", 0) > after:
                        if ticket_channel:
                            # A chat transaction may publish after an engine event with a higher seq.
                            # Read the committed gap so filtering out duplicates never drops a message.
                            while True:
                                async with socket.app.state.db_session() as db:
                                    rows = (
                                        await db.scalars(
                                            select(TicketMessage)
                                            .where(
                                                TicketMessage.ticket_id == identifier,
                                                TicketMessage.seq > after,
                                                TicketMessage.seq <= event["seq"],
                                            )
                                            .order_by(TicketMessage.seq)
                                            .limit(500)
                                        )
                                    ).all()
                                for row in rows:
                                    await socket.send_json(
                                        {"type": "event", "data": chat_event(row, compact)}
                                    )
                                    after = row.seq
                                if len(rows) < 500:
                                    break
                        else:
                            await socket.send_json({"type": "event", "data": event})
                    event_task = asyncio.create_task(queue.get())
                if receive_task in done:
                    frame = receive_task.result()
                    if isinstance(frame, dict) and frame.get("type") == "action" and ticket_channel:
                        try:
                            await action(socket, identifier, actor, frame)
                        except (HTTPException, ValidationError, ValueError) as error:
                            await socket.send_json(
                                {
                                    "type": "action_result",
                                    "accepted": False,
                                    "error": error.detail
                                    if isinstance(error, HTTPException)
                                    else "Invalid action",
                                }
                            )
                    receive_task = asyncio.create_task(socket.receive_json())
    except WebSocketDisconnect:
        pass
    except (ValueError, HTTPException, TimeoutError):
        with suppress(WebSocketDisconnect, RuntimeError):
            await socket.close(1008)
    finally:
        tasks = [t for t in [receive_task, event_task] if t is not None]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@router.websocket("/ws/tickets/{ticket_id}")
async def ticket_socket(socket: WebSocket, ticket_id: UUID):
    await channel_socket(socket, str(ticket_id), True)


@router.websocket("/ws/projects/{project_id}")
async def project_socket(socket: WebSocket, project_id: UUID):
    await channel_socket(socket, str(project_id), False)
