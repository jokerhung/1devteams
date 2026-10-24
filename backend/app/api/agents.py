from uuid import UUID

from fastapi import APIRouter, Request
from sqlalchemy import delete, select, update

from app.core.deps import DB, Admin, CurrentUser, fail, record
from app.db.base import now
from app.db.models import Agent, ProjectMember, TeamAgent
from app.schemas.agent import (
    AgentCreate,
    AgentDuplicate,
    AgentEditOut,
    AgentOut,
    AgentPatch,
    ConnectionDraft,
    ConnectionOut,
)
from app.schemas.common import Success
from app.services import connections
from app.services.agent_service import guard_agent_removal, prepare_agent, public_agent, runtime_config, usage
from app.services.audit import audit
from app.services.common import commit
from app.services.seed import PRESETS

router = APIRouter(prefix="/agents", tags=["Agents"])


async def validate_fallback(db, identifier: str | None) -> None:
    if identifier:
        target = await db.get(Agent, identifier)
        if target is None or not target.is_active or target.runtime != "openai-api":
            fail(422, "Agent fallback phải là OpenAI API đang hoạt động", "invalid_fallback")


@router.get("/models-catalog")
async def models_catalog(request: Request, user: CurrentUser) -> dict:
    return request.app.state.models_catalog.get()


@router.get("/permission-presets")
async def presets(user: CurrentUser) -> dict:
    return PRESETS


@router.post("/test-connection-draft", response_model=ConnectionOut)
async def draft_connection(body: ConnectionDraft, request: Request, user: Admin):
    request.app.state.connection_limiter.check(user.id)
    return await connections.test_api(body, request.app.state.settings)


@router.get("", response_model=list[AgentOut])
async def list_agents(db: DB, user: CurrentUser, active: bool | None = None):
    query = select(Agent).order_by(Agent.created_at, Agent.id)
    if active is not None:
        query = query.where(Agent.is_active == active)
    return [public_agent(agent) for agent in (await db.scalars(query)).all()]


@router.post("", response_model=AgentOut, status_code=201)
async def create_agent(body: AgentCreate, request: Request, db: DB, user: Admin):
    agent = Agent(**await prepare_agent(body, request.app.state.settings))
    await validate_fallback(db, agent.fallback_agent_id)
    db.add(agent)
    await db.flush()
    await audit(db, "agent.create", agent.id, user_id=user.id, payload={"handle": agent.handle})
    await commit(db)
    return public_agent(agent)


@router.get("/{aid}", response_model=AgentOut)
async def get_agent(aid: UUID, db: DB, user: CurrentUser):
    return public_agent(await record(db, Agent, aid))


@router.patch("/{aid}", response_model=AgentEditOut)
async def patch_agent(aid: UUID, body: AgentPatch, request: Request, db: DB, user: Admin):
    agent = await record(db, Agent, aid)
    await db.execute(
        update(Agent)
        .where(Agent.id == agent.id)
        .values(config_version=Agent.config_version, updated_at=Agent.updated_at)
    )
    await db.refresh(agent)
    values = await prepare_agent(body, request.app.state.settings, agent)
    await validate_fallback(db, values.get("fallback_agent_id", agent.fallback_agent_id))
    changed = any(getattr(agent, key) != value for key, value in values.items())
    if changed:
        affected = [tid for tid, aid in request.app.state.acp_pool.sessions if aid == agent.id]
        if values.get("is_active") is False and agent.is_active:
            await guard_agent_removal(db, agent)
        for key, value in values.items():
            setattr(agent, key, value)
        agent.config_version += 1
        agent.restarted_at = now()
        await audit(
            db,
            "agent.permission" if "permission_profile" in values else "agent.update",
            agent.id,
            user_id=user.id,
            payload={"fields": sorted(values), "restart": True, "tickets": affected},
            ip=request.client.host if request.client else None,
        )
        await commit(db)
        await request.app.state.acp_pool.restart_agent(agent.id, agent.config_version)
    return {"agent": public_agent(agent), "restart": changed}


@router.post("/{aid}/restart", response_model=AgentEditOut)
async def restart_agent(aid: UUID, request: Request, db: DB, user: Admin):
    agent = await record(db, Agent, aid)
    await db.execute(
        update(Agent)
        .where(Agent.id == agent.id)
        .values(config_version=Agent.config_version + 1, restarted_at=now())
    )
    await db.refresh(agent)
    await audit(
        db,
        "agent.restart",
        agent.id,
        user_id=user.id,
        payload={
            "restart": True,
            "tickets": [tid for tid, aid in request.app.state.acp_pool.sessions if aid == agent.id],
        },
    )
    await commit(db)
    await request.app.state.acp_pool.restart_agent(agent.id, agent.config_version)
    return {"agent": public_agent(agent), "restart": True}


@router.get("/{aid}/usage")
async def agent_usage(aid: UUID, db: DB, user: Admin) -> dict:
    return await usage(db, await record(db, Agent, aid))


@router.delete("/{aid}", response_model=Success)
async def delete_agent(aid: UUID, request: Request, db: DB, user: Admin):
    agent = await record(db, Agent, aid)
    await guard_agent_removal(db, agent, deleting=True)
    await db.execute(delete(TeamAgent).where(TeamAgent.agent_id == agent.id))
    await db.execute(
        delete(ProjectMember).where(ProjectMember.member_type == "AGENT", ProjectMember.member_id == agent.id)
    )
    await db.delete(agent)
    await commit(db)
    await request.app.state.acp_pool.restart_agent(agent.id, agent.config_version + 1)
    return {"ok": True}


@router.post("/{aid}/duplicate", response_model=AgentOut, status_code=201)
async def duplicate_agent(aid: UUID, body: AgentDuplicate, db: DB, user: Admin):
    original = await record(db, Agent, aid)
    from app.services.common import fields

    values = fields(original)
    for key in ("id", "created_at", "updated_at", "restarted_at"):
        values.pop(key)
    values.update(
        handle=body.handle,
        display_name=body.display_name or original.display_name,
        is_builtin=False,
        config_version=1,
    )
    agent = Agent(**values)
    db.add(agent)
    await commit(db)
    return public_agent(agent)


@router.post("/{aid}/test-connection", response_model=ConnectionOut)
async def test_connection(aid: UUID, request: Request, db: DB, user: Admin):
    request.app.state.connection_limiter.check(user.id)
    agent = await record(db, Agent, aid)
    cfg = runtime_config(agent, request.app.state.settings)
    if cfg.runtime == "openai-api":
        body = ConnectionDraft(
            base_url=cfg.base_url,
            api_key=cfg.api_key,
            model=cfg.model,
            extra_headers=cfg.api_params.extra_headers,
        )
        return await connections.test_api(body, request.app.state.settings)
    return await connections.test_native(cfg, request.app.state.models_catalog)
