from uuid import UUID, uuid4

from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import DB, Admin, CurrentUser, fail, require_project
from app.db.models import Agent, WorkflowTemplate
from app.schemas.common import Success
from app.schemas.orchestrator_template import OrchestratorTemplateInput, OrchestratorTemplateOut
from app.services.common import commit
from app.services.orchestrator_templates import (
    PREFIX,
    bind_template,
    template_definitions,
    validate_template_agents,
)
from app.services.project_service import effective_agents

router = APIRouter(prefix="/orchestrator-templates", tags=["Orchestrator templates"])


@router.get("", response_model=list[OrchestratorTemplateOut])
async def list_templates(db: DB, user: CurrentUser, project_id: UUID | None = None):
    agents = None
    if project_id:
        await require_project(db, str(project_id), user)
        agents = await effective_agents(db, str(project_id))
    return [
        bind_template(key, template, agents) for key, template in (await template_definitions(db)).items()
    ]


@router.post("", response_model=OrchestratorTemplateOut, status_code=201)
async def create_template(body: OrchestratorTemplateInput, db: DB, user: Admin):
    try:
        validate_template_agents(body, (await db.scalars(select(Agent))).all())
    except ValueError as error:
        fail(422, str(error))
    key = uuid4().hex
    db.add(WorkflowTemplate(key=PREFIX + key, graph=body.model_dump(mode="json")))
    await commit(db)
    return bind_template(key, body)


@router.put("/{key}", response_model=Success)
async def update_template(key: str, body: OrchestratorTemplateInput, db: DB, user: Admin):
    if key not in await template_definitions(db):
        fail(404, "Không tìm thấy template Orchestrator")
    try:
        validate_template_agents(body, (await db.scalars(select(Agent))).all())
    except ValueError as error:
        fail(422, str(error))
    row = await db.scalar(select(WorkflowTemplate).where(WorkflowTemplate.key == PREFIX + key))
    if row is None:
        row = WorkflowTemplate(key=PREFIX + key)
        db.add(row)
    row.graph = body.model_dump(mode="json")
    await commit(db)
    return {"ok": True}
