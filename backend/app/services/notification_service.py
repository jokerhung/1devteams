from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.base import new_id, now
from app.db.models import Notification, Project, ProjectMember, Ticket
from app.services.common import fields


async def create_gate(
    db,
    ticket: Ticket,
    *,
    kind: str,
    node_id: str,
    interrupt_seq: int,
    title: str,
    body: str = "",
    events=None,
) -> list[Notification]:
    if kind not in {"CONFIRM", "INPUT"}:
        raise ValueError("Unknown gate kind")
    ticket.status = "WAITING_USER_CONFIRM" if kind == "CONFIRM" else "WAITING_USER_INPUT"
    project = await db.get(Project, ticket.project_id)
    users = set(
        (
            await db.scalars(
                select(ProjectMember.member_id).where(
                    ProjectMember.project_id == project.id,
                    ProjectMember.member_type == "USER",
                    ProjectMember.project_role == "MAINTAINER",
                )
            )
        ).all()
    )
    users.add(project.owner_id)
    if kind == "INPUT":
        users.add(ticket.reporter_id)
    key = f"{ticket.id}:{node_id}:{interrupt_seq}"
    if len(key) > 100:
        import hashlib

        key = hashlib.sha256(key.encode()).hexdigest()
    rows = []
    insert = sqlite_insert if db.bind.dialect.name == "sqlite" else pg_insert
    for user_id in sorted(users):
        identifier = new_id()
        statement = (
            insert(Notification)
            .values(
                id=identifier,
                user_id=user_id,
                project_id=ticket.project_id,
                workflow_id=ticket.workflow_id,
                ticket_id=ticket.id,
                type=kind,
                title=title[:200],
                body=body[:500],
                gate_key=key,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "gate_key"])
            .returning(Notification.id)
        )
        created = await db.scalar(statement)
        if created:
            rows.append(await db.get(Notification, created))
    await db.commit()
    if events:
        from fastapi.encoders import jsonable_encoder

        for row in rows:
            await events.publish(
                f"users/{row.user_id}",
                {"event_type": "notification_created", "notification": jsonable_encoder(fields(row))},
            )
    return rows


async def resolve_gate(db, ticket_id: str, outcome: str, *, gate_key: str | None = None, events=None) -> None:
    if outcome not in {"APPROVED", "REJECTED", "ANSWERED", "CANCELLED", "FAILED"}:
        raise ValueError("Unknown gate outcome")
    statement = update(Notification).where(
        Notification.ticket_id == ticket_id, Notification.resolved_at.is_(None)
    )
    if gate_key:
        statement = statement.where(Notification.gate_key == gate_key)
    rows = (
        await db.execute(
            statement.values(resolved_at=now(), outcome=outcome).returning(
                Notification.id, Notification.user_id
            )
        )
    ).all()
    await db.commit()
    if events:
        for identifier, user_id in rows:
            await events.publish(
                f"users/{user_id}",
                {
                    "event_type": "notification_resolved",
                    "id": identifier,
                    "ticket_id": ticket_id,
                    "outcome": outcome,
                },
            )
