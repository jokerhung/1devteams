import re
from uuid import UUID

from fastapi import APIRouter, Query, Request
from sqlalchemy import or_, select

from app.api.workflows import authorized_workflow
from app.core.deps import DB, CurrentUser, fail, record, require_project
from app.db.models import Ticket, TicketMessage
from app.schemas.ticket import LogOut, MessageOut, TicketCreate, TicketCreated, TicketOut, TicketPatch
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
        }
        for row in rows
    ]


from app.schemas.ticket import ChatMessage, Confirm, Reply  # noqa: E402


@router.post("/tickets/{tid}/start")
async def start_ticket(tid: UUID, request: Request, user: CurrentUser):
    await request.app.state.ticket_runner.start(str(tid), user)
    return {"accepted": True}


@router.post("/tickets/{tid}/reply")
async def reply_ticket(tid: UUID, body: Reply, request: Request, user: CurrentUser):
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


@router.get("/tickets/{tid}/state")
async def ticket_state(tid: UUID, request: Request, db: DB, user: CurrentUser):
    await authorized_ticket(db, tid, user)
    await db.rollback()
    return await request.app.state.ticket_runner.state(str(tid))


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
    message = await add_message(
        db,
        str(tid),
        content=body.text,
        sender_type="USER",
        sender_id=user.id,
        sender_name=user.display_name,
        event_type="message_chunk",
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
                    "path": str(destination.relative_to(git.workspace)),
                }
            )
        message.event_metadata = {"attachments": info}
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
    elif status == "OPEN" and re.search(r"@ba\b", body.text, re.I):
        await runner.start(str(tid), user)
    return value
