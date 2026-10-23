from sqlalchemy import delete, select, update

from app.db.models import Team, TeamAgent
from app.services.common import fields
from app.services.project_service import validate_members


async def set_agents(db, team: Team, identifiers: list[str]) -> None:
    await db.execute(update(Team).where(Team.id == team.id).values(updated_at=Team.updated_at))
    await validate_members(db, identifiers)
    await db.execute(delete(TeamAgent).where(TeamAgent.team_id == team.id))
    db.add_all([TeamAgent(team_id=team.id, agent_id=aid, position=i) for i, aid in enumerate(identifiers)])


async def public_team(db, team: Team) -> dict:
    ids = (
        await db.scalars(
            select(TeamAgent.agent_id).where(TeamAgent.team_id == team.id).order_by(TeamAgent.position)
        )
    ).all()
    return fields(team) | {"agent_ids": list(ids)}
