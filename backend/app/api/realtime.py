import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.core.security import token_subject
from app.db.models import Project, ProjectMember, User

router = APIRouter()


@router.websocket("/ws/users/me")
async def user_events(socket: WebSocket):
    # Browser clients send {"token": "..."} as their first frame, avoiding JWTs in URL/access logs.
    await socket.accept()
    try:
        authorization = socket.headers.get("authorization", "")
        if authorization.lower().startswith("bearer "):
            token = authorization[7:]
        else:
            frame = await asyncio.wait_for(socket.receive_json(), 5)
            token = frame.get("token", "") if isinstance(frame, dict) else ""
        if not isinstance(token, str):
            await socket.close(1008)
            return
        subject = token_subject(token, socket.app.state.settings)
        subject = str(UUID(subject)) if subject else None
        async with socket.app.state.db_session() as db:
            user = await db.scalar(select(User).where(User.id == subject)) if subject else None
        if user is None:
            await socket.close(1008)
            return
        bus = socket.app.state.event_bus
        async with bus.subscribe(f"users/{user.id}") as personal, bus.subscribe("users") as global_events:
            await socket.send_json({"event_type": "connected"})
            personal_task = asyncio.create_task(personal.get())
            global_task = asyncio.create_task(global_events.get())
            disconnect_task = asyncio.create_task(socket.receive())
            try:
                while True:
                    done, _ = await asyncio.wait(
                        [personal_task, global_task, disconnect_task], return_when=asyncio.FIRST_COMPLETED
                    )
                    if disconnect_task in done:
                        break
                    if personal_task in done:
                        await socket.send_json(personal_task.result())
                        personal_task = asyncio.create_task(personal.get())
                    if global_task in done:
                        event = global_task.result()
                        permitted = True
                        if event.get("ticket_id") and user.system_role not in {"OWNER", "ADMIN"}:
                            from app.db.models import Ticket

                            async with socket.app.state.db_session() as db:
                                ticket = await db.get(Ticket, event["ticket_id"])
                                project = await db.get(Project, ticket.project_id) if ticket else None
                                member = (
                                    await db.scalar(
                                        select(ProjectMember.id).where(
                                            ProjectMember.project_id == project.id,
                                            ProjectMember.member_type == "USER",
                                            ProjectMember.member_id == user.id,
                                        )
                                    )
                                    if project
                                    else None
                                )
                                permitted = bool(project and (project.owner_id == user.id or member))
                        if permitted:
                            await socket.send_json(event)
                        global_task = asyncio.create_task(global_events.get())
            finally:
                for task in [personal_task, global_task, disconnect_task]:
                    task.cancel()
                await asyncio.gather(personal_task, global_task, disconnect_task, return_exceptions=True)
    except (WebSocketDisconnect, TimeoutError, ValueError, KeyError):
        await socket.close(1008)
