from sqlalchemy import delete, select, update

from app.db.models import ProjectMember, Team, TeamAgent
from app.services.common import fields
from app.services.project_service import effective_agents, guard_removed_agents, validate_members


async def team_project_agents(db, team_id: str) -> dict[str, set[str]]:
    pids = (
        await db.scalars(
            select(ProjectMember.project_id).where(
                ProjectMember.member_type == "TEAM", ProjectMember.member_id == team_id
            )
        )
    ).all()
    return {pid: {agent.id for agent in await effective_agents(db, pid)} for pid in pids}


async def set_agents(db, team: Team, identifiers: list[str]) -> None:
    await db.execute(update(Team).where(Team.id == team.id).values(updated_at=Team.updated_at))
    await validate_members(db, identifiers)
    before = await team_project_agents(db, team.id)
    await db.execute(delete(TeamAgent).where(TeamAgent.team_id == team.id))
    db.add_all([TeamAgent(team_id=team.id, agent_id=aid, position=i) for i, aid in enumerate(identifiers)])
    await db.flush()
    for pid, agents in before.items():
        await guard_removed_agents(db, pid, agents)


async def public_team(db, team: Team) -> dict:
    ids = (
        await db.scalars(
            select(TeamAgent.agent_id).where(TeamAgent.team_id == team.id).order_by(TeamAgent.position)
        )
    ).all()
    return fields(team) | {"agent_ids": list(ids)}
