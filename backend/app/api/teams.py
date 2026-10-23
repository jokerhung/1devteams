from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import delete, select

from app.core.deps import DB, Admin, CurrentUser, record
from app.db.models import ProjectMember, Team
from app.schemas.common import Success
from app.schemas.team import TeamAgents, TeamCreate, TeamOut, TeamPatch
from app.services.common import commit, patch_values
from app.services.project_service import guard_removed_agents
from app.services.team_service import public_team, set_agents, team_project_agents

router = APIRouter(prefix="/teams", tags=["Teams"])


@router.get("", response_model=list[TeamOut])
async def list_teams(db: DB, user: CurrentUser):
    teams = (await db.scalars(select(Team).order_by(Team.name))).all()
    return [await public_team(db, team) for team in teams]


@router.post("", response_model=TeamOut, status_code=201)
async def create_team(body: TeamCreate, db: DB, user: Admin):
    team = Team(**body.model_dump(exclude={"agent_ids"}))
    db.add(team)
    from sqlalchemy.exc import IntegrityError

    try:
        await db.flush()
    except IntegrityError:
        from app.core.deps import fail

        fail(409, "Tên AI Team đã tồn tại", "conflict")
    await set_agents(db, team, [str(aid) for aid in body.agent_ids])
    await commit(db)
    return await public_team(db, team)


@router.get("/{tid}", response_model=TeamOut)
async def get_team(tid: UUID, db: DB, user: CurrentUser):
    return await public_team(db, await record(db, Team, tid))


@router.patch("/{tid}", response_model=TeamOut)
async def patch_team(tid: UUID, body: TeamPatch, db: DB, user: Admin):
    team = await record(db, Team, tid)
    values = patch_values(body, nullable={"logo_url"})
    ids = values.pop("agent_ids", None)
    if ids is not None:
        await set_agents(db, team, [str(aid) for aid in ids])
    for key, value in values.items():
        setattr(team, key, value)
    await commit(db)
    return await public_team(db, team)


@router.put("/{tid}/agents", response_model=TeamOut)
async def update_agents(tid: UUID, body: TeamAgents, db: DB, user: Admin):
    team = await record(db, Team, tid)
    await set_agents(db, team, [str(aid) for aid in body.agent_ids])
    await commit(db)
    return await public_team(db, team)


@router.delete("/{tid}", response_model=Success)
async def delete_team(tid: UUID, db: DB, user: Admin):
    team = await record(db, Team, tid)
    before = await team_project_agents(db, team.id)
    await db.execute(
        delete(ProjectMember).where(ProjectMember.member_type == "TEAM", ProjectMember.member_id == team.id)
    )
    await db.delete(team)
    for pid, agents in before.items():
        await guard_removed_agents(db, pid, agents)
    await commit(db)
    return {"ok": True}
