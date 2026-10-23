from copy import deepcopy

from sqlalchemy import func, select

from app.core.deps import fail
from app.db.models import Ticket, Workflow, WorkflowVersion
from app.schemas.workflow import Graph
from app.services.project_service import effective_agents
from app.services.workflow_validator import validate_graph


async def revalidate(db, workflow: Workflow) -> list[str]:
    errors = validate_graph(
        Graph.model_validate(workflow.graph), await effective_agents(db, workflow.project_id)
    )
    workflow.is_valid = not errors
    workflow.validation_errors = errors
    return errors


async def publish(db, workflow: Workflow, user_id: str) -> None:
    if workflow.status == "ARCHIVED":
        fail(409, "Hãy khôi phục workflow trước khi xuất bản", "workflow_archived")
    if await revalidate(db, workflow):
        fail(400, "; ".join(workflow.validation_errors), "invalid_graph")
    existing = await db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == workflow.id, WorkflowVersion.version == workflow.current_version
        )
    )
    if existing is None:
        db.add(
            WorkflowVersion(
                workflow_id=workflow.id,
                version=workflow.current_version,
                graph=deepcopy(workflow.graph),
                published_by=user_id,
            )
        )
    workflow.published_version = workflow.current_version
    workflow.status = "PUBLISHED"


async def has_tickets(db, workflow_id: str) -> bool:
    return bool(await db.scalar(select(Ticket.id).where(Ticket.workflow_id == workflow_id).limit(1)))


async def protect_last_workflow(db, workflow: Workflow) -> None:
    any_tickets = await db.scalar(select(Ticket.id).where(Ticket.project_id == workflow.project_id).limit(1))
    if workflow.status != "ARCHIVED" and any_tickets:
        count = await db.scalar(
            select(func.count())
            .select_from(Workflow)
            .where(Workflow.project_id == workflow.project_id, Workflow.status != "ARCHIVED")
        )
        if count <= 1:
            fail(409, "Project có ticket phải còn ít nhất 1 workflow chưa archived", "last_workflow")
