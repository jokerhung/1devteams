from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select, update

from app.core.deps import DB, CurrentUser, fail, record, require_project
from app.db.models import Agent, Ticket, Workflow, WorkflowVersion
from app.schemas.common import Success
from app.schemas.workflow import (
    Graph,
    ValidationOut,
    WorkflowCreate,
    WorkflowDuplicate,
    WorkflowOut,
    WorkflowPatch,
    WorkflowVersionOut,
)
from app.services.common import commit, fields, patch_values
from app.services.project_service import effective_agents
from app.services.seed import template_graph
from app.services.workflow_service import has_tickets, protect_last_workflow, publish, revalidate
from app.services.workflow_validator import validate_graph

router = APIRouter(tags=["Workflows"])


async def authorized_workflow(db, wid, user, write=False):
    workflow = await record(db, Workflow, wid)
    await require_project(db, workflow.project_id, user, write=write)
    if write:
        await db.refresh(workflow)
    return workflow


@router.get("/workflow-templates")
async def templates(db: DB, user: CurrentUser) -> list[dict]:
    agents = list((await db.scalars(select(Agent).where(Agent.is_builtin.is_(True)))).all())
    return [
        {"id": key, "name": name, "graph": template_graph(key, agents).model_dump()}
        for key, name in [
            ("blank", "Trống"),
            ("bugfix_default", "Fix Bug"),
            ("bugfix_with_security_review", "Fix Bug + Security Review"),
        ]
    ]


@router.get("/projects/{pid}/workflows", response_model=list[WorkflowOut])
async def list_workflows(pid: UUID, db: DB, user: CurrentUser, include_archived: bool = False):
    await require_project(db, str(pid), user)
    query = (
        select(Workflow)
        .where(Workflow.project_id == str(pid))
        .order_by(Workflow.position, Workflow.created_at)
    )
    if not include_archived:
        query = query.where(Workflow.status != "ARCHIVED")
    result = []
    for workflow in (await db.scalars(query)).all():
        counts = (
            await db.execute(
                select(Ticket.status, func.count())
                .where(Ticket.workflow_id == workflow.id)
                .group_by(Ticket.status)
            )
        ).all()
        result.append(fields(workflow) | {"ticket_counts": dict(counts)})
    return result


@router.post("/projects/{pid}/workflows", response_model=WorkflowOut, status_code=201)
async def create_workflow(pid: UUID, body: WorkflowCreate, db: DB, user: CurrentUser):
    await require_project(db, str(pid), user, write=True)
    graph = template_graph(body.template, await effective_agents(db, str(pid)))
    entity = Workflow(project_id=str(pid), **body.model_dump(exclude={"template"}), graph=graph.model_dump())
    await revalidate(db, entity)
    db.add(entity)
    await commit(db)
    return entity


@router.get("/workflows/{wid}", response_model=WorkflowOut)
async def get_workflow(wid: UUID, db: DB, user: CurrentUser):
    return await authorized_workflow(db, wid, user)


@router.patch("/workflows/{wid}", response_model=WorkflowOut)
async def patch_workflow(wid: UUID, body: WorkflowPatch, db: DB, user: CurrentUser):
    entity = await authorized_workflow(db, wid, user, write=True)
    values = patch_values(body)
    if values.get("ticket_prefix", entity.ticket_prefix) != entity.ticket_prefix and await has_tickets(
        db, entity.id
    ):
        fail(409, "Không đổi prefix khi workflow đã có ticket", "immutable_prefix")
    for key, value in values.items():
        setattr(entity, key, value)
    await commit(db)
    return entity


@router.put("/workflows/{wid}/graph", response_model=ValidationOut)
async def save_graph(wid: UUID, body: Graph, db: DB, user: CurrentUser):
    entity = await authorized_workflow(db, wid, user, write=True)
    if entity.status == "ARCHIVED":
        fail(409, "Workflow đã archived", "workflow_archived")
    errors = validate_graph(body, await effective_agents(db, entity.project_id))
    version = await db.scalar(
        update(Workflow)
        .where(Workflow.id == entity.id)
        .values(
            graph=body.model_dump(),
            current_version=Workflow.current_version + 1,
            is_valid=not errors,
            validation_errors=errors,
        )
        .returning(Workflow.current_version)
    )
    await commit(db)
    return {"is_valid": not errors, "errors": errors, "current_version": version}


@router.post("/workflows/{wid}/validate", response_model=ValidationOut)
async def validate(wid: UUID, db: DB, user: CurrentUser, body: Graph | None = None):
    entity = await authorized_workflow(db, wid, user)
    errors = validate_graph(
        body or Graph.model_validate(entity.graph), await effective_agents(db, entity.project_id)
    )
    return {"is_valid": not errors, "errors": errors, "current_version": entity.current_version}


@router.post("/workflows/{wid}/publish", response_model=WorkflowOut)
async def publish_workflow(wid: UUID, db: DB, user: CurrentUser):
    entity = await authorized_workflow(db, wid, user, write=True)
    await publish(db, entity, user.id)
    await commit(db)
    return entity


@router.post("/workflows/{wid}/duplicate", response_model=WorkflowOut, status_code=201)
async def duplicate(wid: UUID, body: WorkflowDuplicate, db: DB, user: CurrentUser):
    original = await authorized_workflow(db, wid, user, write=True)
    entity = Workflow(
        project_id=original.project_id,
        name=body.name,
        ticket_prefix=body.ticket_prefix,
        description=original.description,
        graph=original.graph,
        icon=original.icon,
        color=original.color,
    )
    await revalidate(db, entity)
    db.add(entity)
    await commit(db)
    return entity


@router.post("/workflows/{wid}/archive", response_model=WorkflowOut)
async def archive(wid: UUID, db: DB, user: CurrentUser):
    entity = await authorized_workflow(db, wid, user, write=True)
    await protect_last_workflow(db, entity)
    entity.status = "ARCHIVED"
    await commit(db)
    return entity


@router.post("/workflows/{wid}/unarchive", response_model=WorkflowOut)
async def unarchive(wid: UUID, db: DB, user: CurrentUser):
    entity = await authorized_workflow(db, wid, user, write=True)
    entity.status = "PUBLISHED" if entity.published_version else "DRAFT"
    await commit(db)
    return entity


@router.delete("/workflows/{wid}", response_model=Success)
async def delete_workflow(wid: UUID, db: DB, user: CurrentUser):
    entity = await authorized_workflow(db, wid, user, write=True)
    if await has_tickets(db, entity.id):
        fail(409, "Workflow đã có ticket; hãy archive", "workflow_in_use")
    await protect_last_workflow(db, entity)
    await db.delete(entity)
    await commit(db)
    return {"ok": True}


@router.get("/workflows/{wid}/versions", response_model=list[WorkflowVersionOut])
async def versions(wid: UUID, db: DB, user: CurrentUser) -> list[dict]:
    await authorized_workflow(db, wid, user)
    rows = (
        await db.scalars(
            select(WorkflowVersion)
            .where(WorkflowVersion.workflow_id == str(wid))
            .order_by(WorkflowVersion.version.desc())
        )
    ).all()
    return [fields(row) for row in rows]


@router.get("/workflows/{wid}/versions/{version}", response_model=WorkflowVersionOut)
async def version(wid: UUID, version: int, db: DB, user: CurrentUser) -> dict:
    await authorized_workflow(db, wid, user)
    row = await db.scalar(
        select(WorkflowVersion).where(
            WorkflowVersion.workflow_id == str(wid), WorkflowVersion.version == version
        )
    )
    if row is None:
        fail(404, "Không có version này", "not_found")
    return fields(row)
