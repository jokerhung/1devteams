import re
import unicodedata

from sqlalchemy import select, update

from app.acp.security import scrub, scrub_data
from app.core.deps import fail
from app.db.base import new_id, now
from app.db.models import Project, Ticket, TicketMessage, Workflow, WorkflowVersion
from app.services.common import fields


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value.replace("Đ", "D").replace("đ", "d"))
    value = value.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-") or "ticket"


async def public_ticket(db, ticket: Ticket) -> dict:
    workflow = await db.get(Workflow, ticket.workflow_id)
    return fields(ticket) | {"code": f"#{workflow.ticket_prefix}-{ticket.number}"}


async def create_ticket(db, workflow: Workflow, body, user_id: str) -> Ticket:
    number = await db.scalar(
        update(Project)
        .where(Project.id == workflow.project_id)
        .values(
            next_ticket_number=Project.next_ticket_number + 1,
            last_activity_at=now(),
        )
        .returning(Project.next_ticket_number - 1)
    )
    await db.refresh(workflow)
    if workflow.status != "PUBLISHED" or workflow.published_version is None:
        fail(400, "Workflow phải được xuất bản và chưa archived", "workflow_not_published")
    snapshot = await db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id, WorkflowVersion.version == workflow.published_version
        )
    )
    if snapshot is None:
        fail(400, "Không tìm thấy snapshot đã xuất bản", "workflow_not_published")
    from app.schemas.workflow import Graph
    from app.services.project_service import effective_agents
    from app.services.workflow_validator import validate_graph

    errors = validate_graph(
        Graph.model_validate(snapshot.graph), await effective_agents(db, workflow.project_id)
    )
    if errors:
        fail(400, "; ".join(errors), "invalid_graph")
    base = f"{workflow.ticket_prefix.lower()}-{slugify(body.title)}"[:40].rstrip("-")
    slug = base
    duplicate = await db.scalar(
        select(Ticket.id)
        .where(Ticket.project_id == workflow.project_id, Ticket.channel_slug == slug)
        .limit(1)
    )
    attempt = 0
    while duplicate:
        suffix = f"-{number}" + (f"-{attempt}" if attempt else "")
        slug = base[: 40 - len(suffix)].rstrip("-") + suffix
        duplicate = await db.scalar(
            select(Ticket.id)
            .where(Ticket.project_id == workflow.project_id, Ticket.channel_slug == slug)
            .limit(1)
        )
        attempt += 1
    identifier = new_id()
    ticket = Ticket(
        id=identifier,
        project_id=workflow.project_id,
        workflow_id=workflow.id,
        workflow_version=workflow.published_version,
        number=number,
        channel_slug=slug,
        title=body.title,
        description=body.description,
        reporter_id=user_id,
        thread_id=identifier,
    )
    db.add(ticket)
    return ticket


async def add_message(
    db,
    ticket_id: str,
    *,
    content: str,
    sender_type="SYSTEM",
    sender_id=None,
    sender_name="System",
    event_type="log",
    metadata=None,
    run_id=None,
    node_id=None,
    message_id=None,
):
    seq = await db.scalar(
        update(Ticket)
        .where(Ticket.id == ticket_id)
        .values(next_message_seq=Ticket.next_message_seq + 1)
        .returning(Ticket.next_message_seq - 1)
    )
    if seq is None:
        fail(404, "Không tìm thấy ticket", "not_found")
    message = TicketMessage(
        **({"id": message_id} if message_id else {}),
        ticket_id=ticket_id,
        seq=seq,
        content=scrub(content),
        sender_type=sender_type,
        sender_id=sender_id,
        sender_name=sender_name,
        event_type=event_type,
        event_metadata=scrub_data(metadata or {}),
        run_id=run_id,
        node_id=node_id,
    )
    db.add(message)
    await db.flush()
    from app.services.chat_history import record_summary

    await record_summary(db, message)
    return message
