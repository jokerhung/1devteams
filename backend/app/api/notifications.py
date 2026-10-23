from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import and_, func, or_, select, update

from app.core.deps import DB, CurrentUser, fail, record
from app.db.models import Notification, Project, Ticket, Workflow
from app.schemas.common import Page, Success
from app.schemas.notification import NotificationOut
from app.services.common import commit, fields

router = APIRouter(prefix="/notifications", tags=["Notifications"])


@router.get("/unread-count")
async def count(db: DB, user: CurrentUser) -> dict:
    total = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.resolved_at.is_(None))
    )
    return {"open": total}


@router.post("/read-all", response_model=Success)
async def read_all(db: DB, user: CurrentUser):
    await db.execute(update(Notification).where(Notification.user_id == user.id).values(is_read=True))
    await commit(db)
    return {"ok": True}


@router.get("", response_model=Page[NotificationOut])
async def inbox(
    db: DB,
    user: CurrentUser,
    status: Literal["open", "resolved"] = "open",
    limit: int = Query(default=100, ge=1, le=500),
    cursor: UUID | None = None,
):
    query = select(Notification).where(Notification.user_id == user.id)
    query = query.where(
        Notification.resolved_at.is_(None) if status == "open" else Notification.resolved_at.is_not(None)
    )
    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    if cursor:
        previous = await record(db, Notification, cursor)
        if previous.user_id != user.id:
            fail(404, "Không có cursor này", "not_found")
        query = query.where(
            or_(
                Notification.created_at < previous.created_at,
                and_(Notification.created_at == previous.created_at, Notification.id < previous.id),
            )
        )
    rows = list(
        (
            await db.scalars(
                query.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)
            )
        ).all()
    )
    items = []
    for row in rows[:limit]:
        project = await record(db, Project, row.project_id)
        workflow = await record(db, Workflow, row.workflow_id)
        ticket = await record(db, Ticket, row.ticket_id)
        items.append(
            fields(row)
            | {
                "project": {"id": project.id, "name": project.name},
                "workflow": {"id": workflow.id, "name": workflow.name},
                "ticket": {
                    "id": ticket.id,
                    "code": f"#{workflow.ticket_prefix}-{ticket.number}",
                    "title": ticket.title,
                },
            }
        )
    return {"items": items, "total": total, "next_cursor": rows[limit - 1].id if len(rows) > limit else None}


@router.post("/{nid}/read", response_model=Success)
async def read_notification(nid: UUID, db: DB, user: CurrentUser):
    notification = await record(db, Notification, nid)
    if notification.user_id != user.id:
        fail(404, "Không tìm thấy thông báo", "not_found")
    notification.is_read = True
    await commit(db)
    return {"ok": True}
