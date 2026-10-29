from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update

from app.core.deps import DB, Admin, CurrentUser, fail, record, require_project
from app.db.models import Agent, Ticket, Workflow, WorkflowTemplate, WorkflowVersion
from app.schemas.common import DeletionPreview, Success
from app.schemas.workflow import (
    Graph,
    OrchestratorConfig,
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
from app.services.workflow_assistant import AssistantRequest, AssistantResponse, chat
from app.services.workflow_service import has_tickets, protect_last_workflow, publish, revalidate
from app.services.workflow_templates import configured_graph
from app.services.workflow_validator import validate_graph

router = APIRouter(tags=["Workflows"])


async def authorized_workflow(db, wid, user, write=False):
    workflow = await record(db, Workflow, wid)
    await require_project(db, workflow.project_id, user, write=write)
    if write:
        await db.refresh(workflow)
    return workflow


@router.post("/workflows/{wid}/assistant", response_model=AssistantResponse)
async def workflow_assistant(wid: UUID, body: AssistantRequest, db: DB, user: CurrentUser, request: Request):
    workflow = await authorized_workflow(db, wid, user, write=True)
    if workflow.status == "ARCHIVED":
        fail(409, "Workflow đã archived")
    return await chat(body, await effective_agents(db, workflow.project_id), db, request)


@router.post("/workflow-templates/{key}/assistant", response_model=AssistantResponse)
async def template_assistant(key: str, body: AssistantRequest, db: DB, user: Admin, request: Request):
    if key not in {"bugfix_default", "add_feature", "bugfix_with_security_review"}:
        fail(404, "Không tìm thấy template")
    agents = list((await db.scalars(select(Agent))).all())
    return await chat(body, agents, db, request)


@router.get("/workflow-templates")
async def templates(db: DB, user: CurrentUser, project_id: UUID | None = None) -> list[dict]:
    if project_id:
        await require_project(db, str(project_id), user)
        agents = await effective_agents(db, str(project_id))
    else:
        agents = list((await db.scalars(select(Agent))).all())
    return [
        {"id": key, "name": name, "graph": (await configured_graph(db, key, agents)).model_dump()}
        for key, name in [
            ("blank", "Trống"),
            ("bugfix_default", "Fix Bug"),
            ("add_feature", "Add feature"),
            ("bugfix_with_security_review", "Fix Bug + Security Review"),
        ]
    ]


class TemplateInstructions(BaseModel):
    instructions: dict[str, str] = Field(default_factory=dict, max_length=30)
    graph: Graph | None = None


@router.put("/workflow-templates/{key}")
async def save_template(key: str, body: TemplateInstructions, db: DB, user: Admin):
    if key not in {"bugfix_default", "add_feature", "bugfix_with_security_review"}:
        fail(404, "Không tìm thấy template")
    agents = list((await db.scalars(select(Agent))).all())
    graph = body.graph or template_graph(key, [])
    if body.graph:
        errors = validate_graph(graph, agents)
        if errors:
            fail(422, "; ".join(errors))
        roles = {agent.id: agent.role_key for agent in agents}
        handles = {agent.id: agent.handle for agent in agents}
        for node in graph.nodes:
            if node.type in {"agent", "git_release"}:
                node.data["agent_role"] = roles.get(str(node.data.get("agent_id", "")))
                node.data["agent_handle"] = handles.get(str(node.data.get("agent_id", "")))
    permitted = {node.id for node in graph.nodes if node.type in {"agent", "git_release"}}
    if set(body.instructions) - permitted or any(len(text) > 20000 for text in body.instructions.values()):
        fail(422, "Hướng dẫn template không hợp lệ")
    config = await db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.key == key))
    if config is None:
        config = WorkflowTemplate(key=key)
        db.add(config)
    config.instructions = body.instructions
    if body.graph:
        config.graph = graph.model_dump()
    await commit(db)
    return {"ok": True}


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
    agents = await effective_agents(db, str(pid))
    if body.orchestrator:
        from app.services.orchestrator import orchestrator_graph

        try:
            graph = orchestrator_graph(body.orchestrator, agents)
        except ValueError as error:
            fail(422, str(error))
    else:
        graph = await configured_graph(db, body.template, agents)
    entity = Workflow(
        project_id=str(pid),
        **body.model_dump(exclude={"template", "orchestrator"}),
        graph=graph.model_dump(mode="json"),
    )
    await revalidate(db, entity)
    db.add(entity)
    await commit(db)
    return entity


@router.get("/workflows/{wid}", response_model=WorkflowOut)
async def get_workflow(wid: UUID, db: DB, user: CurrentUser):
    return await authorized_workflow(db, wid, user)


@router.put("/workflows/{wid}/orchestrator", response_model=WorkflowOut)
async def save_orchestrator(wid: UUID, body: OrchestratorConfig, db: DB, user: CurrentUser):
    from app.services.orchestrator import orchestrator_graph

    entity = await authorized_workflow(db, wid, user, write=True)
    if entity.status == "ARCHIVED" or not entity.graph.get("orchestrator"):
        fail(409, "Chỉ chỉnh cấu hình Orchestrator đang hoạt động")
    try:
        graph = orchestrator_graph(body, await effective_agents(db, entity.project_id))
    except ValueError as error:
        fail(422, str(error))
    entity.graph = graph.model_dump(mode="json")
    entity.current_version += 1
    await revalidate(db, entity)
    await commit(db)
    return entity


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
    if entity.graph.get("orchestrator") or body.orchestrator:
        fail(409, "Sửa Orchestrator bằng màn hình cấu hình")
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
async def delete_workflow(wid: UUID, request: Request, db: DB, user: CurrentUser, cascade: bool = False):
    from app.services.deletion import deleting_tickets

    entity = await authorized_workflow(db, wid, user, write=True)
    ticket_ids = list((await db.scalars(select(Ticket.id).where(Ticket.workflow_id == entity.id))).all())
    if ticket_ids and not cascade:
        fail(409, "Cần xác nhận xóa kèm toàn bộ ticket trong workflow", "cascade_confirmation_required")
    async with deleting_tickets(db, request, ticket_ids):
        await db.delete(entity)
        await commit(db)
    return {"ok": True}


@router.get("/workflows/{wid}/deletion-preview", response_model=DeletionPreview)
async def workflow_deletion_preview(wid: UUID, db: DB, user: CurrentUser):
    entity = await authorized_workflow(db, wid, user, write=True)
    count = await db.scalar(select(func.count()).select_from(Ticket).where(Ticket.workflow_id == entity.id))
    return {"ticket_count": count, "workflow_count": 0}


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
