import re
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import or_, select

from app.api.workflows import authorized_workflow
from app.core.deps import DB, CurrentUser, fail, record, require_project
from app.db.models import ChatHistoryEntry, Ticket, TicketMessage
from app.schemas.ticket import (
    HistoryOut,
    LogOut,
    MessageOut,
    TicketCreate,
    TicketCreated,
    TicketOut,
    TicketPatch,
)
from app.services.common import commit, fields, patch_values
from app.services.ticket_service import create_ticket, public_ticket

router = APIRouter(tags=["Tickets"])


async def authorized_ticket(db, tid, user, report=False):
    ticket = await record(db, Ticket, tid)
    await require_project(db, ticket.project_id, user, report=report)
    return ticket


async def ticket_list(db, query, status, q, limit, offset):
    if status:
        query = query.where(Ticket.status == status)
    if q:
        query = query.where(
            or_(Ticket.title.icontains(q, autoescape=True), Ticket.description.icontains(q, autoescape=True))
        )
    tickets = (
        await db.scalars(query.order_by(Ticket.created_at.desc(), Ticket.id).limit(limit).offset(offset))
    ).all()
    return [await public_ticket(db, item) for item in tickets]


@router.get("/workflows/{wid}/tickets", response_model=list[TicketOut])
async def workflow_tickets(
    wid: UUID,
    db: DB,
    user: CurrentUser,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    await authorized_workflow(db, wid, user)
    return await ticket_list(
        db, select(Ticket).where(Ticket.workflow_id == str(wid)), status, q, limit, offset
    )


@router.get("/projects/{pid}/tickets", response_model=list[TicketOut])
async def project_tickets(
    pid: UUID,
    db: DB,
    user: CurrentUser,
    workflow_id: UUID | None = None,
    status: str | None = None,
    q: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    await require_project(db, str(pid), user)
    query = select(Ticket).where(Ticket.project_id == str(pid))
    if workflow_id:
        query = query.where(Ticket.workflow_id == str(workflow_id))
    return await ticket_list(db, query, status, q, limit, offset)


@router.post("/workflows/{wid}/tickets", response_model=TicketCreated, status_code=201)
async def new_ticket(wid: UUID, body: TicketCreate, request: Request, db: DB, user: CurrentUser):
    workflow = await authorized_workflow(db, wid, user)
    await require_project(db, workflow.project_id, user, report=True)
    ticket = await create_ticket(db, workflow, body, user.id)
    await db.flush()
    from app.services.ticket_service import add_message

    await add_message(
        db,
        ticket.id,
        content=body.description or body.title,
        sender_type="USER",
        sender_id=user.id,
        sender_name=user.display_name,
        event_type="message_chunk",
        metadata={"initial": True},
    )
    await commit(db)
    runner = getattr(request.app.state, "ticket_runner", None)
    if body.auto_start and runner is not None:
        await runner.start(ticket.id, user)
    await request.app.state.event_bus.publish(
        f"projects/{workflow.project_id}",
        {"event_type": "ticket_created", "ticket_id": ticket.id, "workflow_id": workflow.id},
    )
    return {
        "ticket": await public_ticket(db, ticket),
        "chat_url": f"/projects/{workflow.project_id}/workflows/{workflow.id}/tickets/{ticket.id}",
        "auto_start_pending": body.auto_start and runner is None,
    }


@router.get("/tickets/{tid}", response_model=TicketOut)
async def get_ticket(tid: UUID, db: DB, user: CurrentUser):
    return await public_ticket(db, await authorized_ticket(db, tid, user))


@router.patch("/tickets/{tid}", response_model=TicketOut)
async def patch_ticket(tid: UUID, body: TicketPatch, db: DB, user: CurrentUser):
    ticket = await authorized_ticket(db, tid, user, report=True)
    if ticket.status != "OPEN":
        fail(409, "Chỉ sửa ticket đang OPEN", "ticket_not_open")
    for key, value in patch_values(body).items():
        setattr(ticket, key, value)
    await commit(db)
    return await public_ticket(db, ticket)


@router.get("/tickets/{tid}/messages", response_model=list[MessageOut])
async def messages(
    tid: UUID,
    db: DB,
    user: CurrentUser,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict]:
    await authorized_ticket(db, tid, user)
    rows = (
        await db.scalars(
            select(TicketMessage)
            .where(TicketMessage.ticket_id == str(tid), TicketMessage.seq > after_seq)
            .order_by(TicketMessage.seq)
            .limit(limit)
        )
    ).all()
    result = []
    for row in rows:
        value = fields(row)
        value["metadata"] = value.pop("event_metadata")
        result.append(value)
    return result


@router.get("/tickets/{tid}/history", response_model=HistoryOut)
async def history(
    tid: UUID,
    db: DB,
    user: CurrentUser,
    before_seq: int | None = Query(default=None, ge=1),
    through_seq: int | None = Query(default=None, ge=0),
    limit: int = Query(default=10, ge=1, le=10),
) -> dict:
    ticket = await authorized_ticket(db, tid, user)
    watermark = (
        min(through_seq, ticket.next_message_seq - 1)
        if through_seq is not None
        else ticket.next_message_seq - 1
    )
    query = select(ChatHistoryEntry).where(
        ChatHistoryEntry.ticket_id == str(tid),
        ChatHistoryEntry.first_seq <= watermark,
    )
    if before_seq is not None:
        query = query.where(ChatHistoryEntry.first_seq < before_seq)
    entries = list(
        (await db.scalars(query.order_by(ChatHistoryEntry.first_seq.desc()).limit(limit + 1))).all()
    )
    groups = []
    from app.services.chat_history import project_events

    historical = None
    for entry in reversed(entries[:limit]):
        payload = entry.payload
        last_seq = entry.last_seq
        if entry.last_seq > watermark:
            if historical is None:
                rows = (
                    await db.scalars(
                        select(TicketMessage)
                        .where(
                            TicketMessage.ticket_id == str(tid),
                            TicketMessage.seq <= watermark,
                        )
                        .order_by(TicketMessage.seq)
                    )
                ).all()
                historical = project_events(rows)
            projected = historical.get(entry.entry_key)
            if projected is None:
                continue
            payload = projected["payload"]
            last_seq = projected["last"]
        elif payload["type"] == "turn" and not payload.get("endedAt"):
            # Reconstruct only visible text for active/historical-in-progress turns.
            rows = (
                await db.scalars(
                    select(TicketMessage)
                    .where(
                        TicketMessage.ticket_id == str(tid),
                        TicketMessage.run_id == payload["id"],
                        TicketMessage.seq <= watermark,
                        TicketMessage.event_type.in_(
                            ["agent_turn_start", "message_chunk", "agent_turn_end", "error"]
                        ),
                    )
                    .order_by(TicketMessage.seq)
                )
            ).all()
            projected = project_events(rows).get(entry.entry_key)
            if projected:
                payload = projected["payload"]
                if "gate" in entry.payload and entry.last_seq <= watermark:
                    payload["gate"] = entry.payload["gate"]
            last_seq = watermark
        groups.append({**payload, "historySeq": entry.first_seq, "lastSeq": min(last_seq, watermark)})
    return {
        "groups": groups,
        "before_seq": entries[min(limit, len(entries)) - 1].first_seq if entries else None,
        "has_more": len(entries) > limit,
        "last_seq": watermark,
    }


@router.get("/tickets/{tid}/turns/{run_id}/details", response_model=list[MessageOut])
async def turn_details(tid: UUID, run_id: UUID, db: DB, user: CurrentUser) -> list[dict]:
    await authorized_ticket(db, tid, user)
    rows = (
        await db.scalars(
            select(TicketMessage)
            .where(
                TicketMessage.ticket_id == str(tid),
                TicketMessage.run_id == str(run_id),
            )
            .order_by(TicketMessage.seq)
        )
    ).all()
    result = []
    for row in rows:
        value = fields(row)
        value["metadata"] = value.pop("event_metadata")
        result.append(value)
    return result


@router.get("/tickets/{tid}/logs", response_model=list[LogOut])
async def logs(
    tid: UUID,
    db: DB,
    user: CurrentUser,
    agent: str | None = None,
    after_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[dict]:
    await authorized_ticket(db, tid, user)
    query = select(TicketMessage).where(
        TicketMessage.ticket_id == str(tid),
        TicketMessage.seq > after_seq,
        or_(
            TicketMessage.event_type.in_(
                ["tool_call", "tool_call_update", "permission", "thought_chunk", "plan", "error", "log"]
            ),
            TicketMessage.sender_type == "SYSTEM",
        ),
    )
    if agent:
        query = query.where(TicketMessage.sender_name == agent)
    rows = (await db.scalars(query.order_by(TicketMessage.seq).limit(limit))).all()
    return [
        {
            "seq": row.seq,
            "run_id": row.run_id,
            "agent": row.sender_name,
            "kind": row.event_type,
            "text": row.content,
            "at": row.created_at,
            "metadata": row.event_metadata,
        }
        for row in rows
    ]


from app.schemas.ticket import ChatMessage, Confirm, Reply  # noqa: E402


@router.post("/tickets/{tid}/start")
async def start_ticket(tid: UUID, request: Request, user: CurrentUser):
    await request.app.state.ticket_runner.start(str(tid), user)
    return {"accepted": True}


@router.post("/tickets/{tid}/reply")
async def reply_ticket(tid: UUID, body: Reply, request: Request, db: DB, user: CurrentUser):
    if body.client_msg_id or body.attachment_ids:
        ticket = await authorized_ticket(db, tid, user, report=True)
        existing = await db.get(TicketMessage, str(body.client_msg_id)) if body.client_msg_id else None
        if ticket.status != "WAITING_USER_INPUT" and existing is None:
            fail(409, "Ticket không chờ câu trả lời", "invalid_ticket_status")
        value = await send_message(tid, ChatMessage(**body.model_dump()), request, db, user)
        return {"accepted": True, "message": value}
    await request.app.state.ticket_runner.reply(str(tid), body.text, user)
    return {"accepted": True}


@router.post("/tickets/{tid}/confirm")
async def confirm_ticket(tid: UUID, body: Confirm, request: Request, user: CurrentUser):
    await request.app.state.ticket_runner.confirm(str(tid), body.approved, body.feedback, user)
    return {"accepted": True}


@router.post("/tickets/{tid}/cancel")
async def cancel_ticket(tid: UUID, request: Request, user: CurrentUser):
    await request.app.state.ticket_runner.cancel(str(tid), user)
    return {"accepted": True}


@router.post("/tickets/{tid}/retry")
async def retry_ticket(tid: UUID, request: Request, user: CurrentUser):
    await request.app.state.ticket_runner.retry(str(tid), user)
    return {"accepted": True}


@router.post("/tickets/{tid}/force-release", status_code=202)
async def force_release_ticket(tid: UUID, request: Request, user: CurrentUser):
    await request.app.state.ticket_runner.force_release(str(tid), user)
    return {"accepted": True}


@router.get("/tickets/{tid}/state")
async def ticket_state(tid: UUID, request: Request, db: DB, user: CurrentUser):
    await authorized_ticket(db, tid, user)
    await db.rollback()
    return await request.app.state.ticket_runner.state(str(tid))


@router.get("/tickets/{tid}/chat-config")
async def chat_config(tid: UUID, request: Request, db: DB, user: CurrentUser):
    from app.db.models import Project, ProjectMember

    ticket = await authorized_ticket(db, tid, user)
    project = await db.get(Project, ticket.project_id)
    assert project is not None
    role = await db.scalar(
        select(ProjectMember.project_role).where(
            ProjectMember.project_id == ticket.project_id,
            ProjectMember.member_type == "USER",
            ProjectMember.member_id == user.id,
        )
    )
    admin = user.system_role in {"OWNER", "ADMIN"} or project.owner_id == user.id
    settings = request.app.state.settings
    return {
        "max_files": settings.attach_max_files,
        "max_mb": settings.attach_max_mb,
        "can_report": admin or role in {"REPORTER", "MAINTAINER"},
        "can_confirm": admin or role == "MAINTAINER",
    }


@router.post("/tickets/{tid}/messages", response_model=MessageOut, status_code=201)
async def send_message(tid: UUID, body: ChatMessage, request: Request, db: DB, user: CurrentUser):
    import asyncio
    import shutil
    from pathlib import Path

    from app.core.events import message_event
    from app.db.models import Attachment, Project
    from app.services.assets import attach_to_message
    from app.services.git_service import GitService
    from app.services.ticket_service import add_message

    ticket = await authorized_ticket(db, tid, user, report=True)
    status = ticket.status
    if body.client_msg_id:
        previous = await db.get(TicketMessage, str(body.client_msg_id))
        if previous:
            if previous.ticket_id != str(tid) or previous.sender_id != user.id:
                fail(409, "ID tin nhắn đã được sử dụng", "message_conflict")
            return message_event(previous)
    if status in {"COMPLETED", "CANCELLED"}:
        fail(409, "Ticket đã kết thúc", "invalid_ticket_status")
    mentioned = None
    if status not in {"WAITING_USER_INPUT", "WAITING_USER_CONFIRM"}:
        from app.services.project_service import effective_agents

        handles = set(re.findall(r"@[\w-]+", body.text.lower()))
        mentioned = next(
            (a for a in await effective_agents(db, ticket.project_id) if a.handle in handles and a.is_active),
            None,
        )
        runner = request.app.state.ticket_runner
        if mentioned and (str(tid) in runner.tasks or str(tid) in runner.adhoc_tasks):
            fail(409, "Agent đang bận; gửi lại sau lượt hiện tại", "agent_busy")
    message = await add_message(
        db,
        str(tid),
        content=body.text,
        sender_type="USER",
        sender_id=user.id,
        sender_name=user.display_name,
        event_type="message_chunk",
        metadata={"client_msg_id": str(body.client_msg_id)} if body.client_msg_id else {},
        message_id=str(body.client_msg_id) if body.client_msg_id else None,
    )
    ids = [str(i) for i in body.attachment_ids]
    await attach_to_message(db, str(tid), message.id, ids, user.id, request.app.state.settings)
    attachments = list((await db.scalars(select(Attachment).where(Attachment.id.in_(ids)))).all())
    if attachments:
        project = await db.get(Project, ticket.project_id)
        assert project is not None
        git = GitService(Path(project.workspace_path))
        await git.exclude_attachments()
        folder = git.workspace / ".aiteams" / "attachments" / str(tid)
        # Use the same path guard as runtime fs handlers; rejects symlink escapes.
        from app.acp.guard import DynamicPermissionGuard
        from app.acp.types import PermissionProfile

        guard = DynamicPermissionGuard(PermissionProfile(allow_write=True), git.workspace)
        safe_folder = guard.resolve_path(str(folder))
        await asyncio.to_thread(safe_folder.mkdir, parents=True, exist_ok=True)
        info = []
        for item in attachments:
            destination = guard.resolve_path(str(safe_folder / f"{item.id}_{item.filename}"))
            source = await asyncio.to_thread(Path(item.storage_path).resolve)
            if not source.is_relative_to(request.app.state.settings.data_dir.resolve()):
                fail(422, "Tệp không hợp lệ", "invalid_attachment")
            await asyncio.to_thread(shutil.copyfile, source, destination)
            info.append(
                {
                    "id": item.id,
                    "filename": item.filename,
                    "mime": item.mime,
                    "size": item.size,
                    "url": f"/api/attachments/{item.id}",
                    "path": str(destination.relative_to(git.workspace)),
                }
            )
        message.event_metadata = {**message.event_metadata, "attachments": info}
    await commit(db)
    value = message_event(message)
    await request.app.state.event_bus.broadcast(f"tickets/{tid}", value)
    runner = request.app.state.ticket_runner
    if status == "WAITING_USER_INPUT":
        await runner.reply(str(tid), body.text or "Xem tệp đính kèm trong tin nhắn.", user)
    elif status == "WAITING_USER_CONFIRM":
        if re.search(r"@leader\b", body.text, re.I) and re.search(
            r"\b(CONFIRM|DONE|OK|ĐÃ FIX|XÁC NHẬN)\b", body.text, re.I
        ):
            await runner.confirm(str(tid), True, None, user)
        elif re.search(r"@developer\b", body.text, re.I):
            await runner.confirm(str(tid), False, body.text, user)
    elif mentioned:
        await runner.adhoc(str(tid), mentioned.id, body.text, user)
    return value


@router.post("/tickets/{tid}/stop-agent")
async def stop_agent(tid: UUID, request: Request, user: CurrentUser):
    await request.app.state.ticket_runner.stop_agent(str(tid), user)
    return {"accepted": True}


@router.post("/tickets/{tid}/stash")
async def stash_ticket(tid: UUID, request: Request, db: DB, user: CurrentUser):
    import asyncio
    import os
    from pathlib import Path

    from app.services.audit import audit
    from app.services.git_service import GitService

    ticket = await authorized_ticket(db, tid, user)
    project = await require_project(db, ticket.project_id, user, write=True)
    if ticket.status != "CANCELLED":
        fail(409, "Huỷ ticket trước khi cất thay đổi vào stash")
    runner = request.app.state.ticket_runner
    git = GitService(Path(project.workspace_path))
    key = os.path.normcase(str(git.workspace))
    lock = runner.workspace_locks.setdefault(key, asyncio.Lock())
    if lock.locked():
        fail(409, "Workspace đang được ticket khác sử dụng")
    async with lock:
        result = await git.run("stash", "push", "-u", "-m", f"aiteams-ticket-{ticket.number}")
    await audit(db, "ticket.stash", str(tid), user_id=user.id)
    await commit(db)
    return {"ok": True, "message": result}


@router.delete("/tickets/{tid}")
async def delete_ticket(tid: UUID, request: Request, db: DB, user: CurrentUser):
    from app.services.assets import attachment_paths, remove_ticket_files

    ticket = await authorized_ticket(db, tid, user)
    await require_project(db, ticket.project_id, user, write=True)
    runner = request.app.state.ticket_runner
    if (
        ticket.status not in {"CANCELLED", "COMPLETED"}
        or str(tid) in runner.tasks
        or str(tid) in runner.adhoc_tasks
    ):
        fail(409, "Chỉ xoá ticket đã kết thúc")
    paths = await attachment_paths(db, [str(tid)])
    await db.delete(ticket)
    await commit(db)
    await remove_ticket_files(request.app.state.settings, [str(tid)], paths)
    await runner.checkpointer.adelete_thread(str(tid))
    return {"ok": True}


@router.get("/tickets/{tid}/event-blobs/{blob_id}")
async def event_blob(tid: UUID, blob_id: UUID, request: Request, db: DB, user: CurrentUser):
    from pathlib import Path

    from fastapi.responses import FileResponse

    await authorized_ticket(db, tid, user)
    path = request.app.state.settings.data_dir.resolve() / "blobs/events" / str(tid) / f"{blob_id}.json"
    if not path.is_file():
        fail(404, "Không tìm thấy output")
    return FileResponse(
        Path(path),
        media_type="application/json",
        filename=f"{blob_id}.json",
        headers={"Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff"},
    )
