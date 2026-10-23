from sqlalchemy import or_, select

from app.core.deps import fail
from app.db.models import Agent, Project, ProjectMember, TeamAgent, User


def visible_projects(user: User):
    if user.system_role in {"OWNER", "ADMIN"}:
        return select(Project)
    memberships = select(ProjectMember.project_id).where(
        ProjectMember.member_type == "USER",
        ProjectMember.member_id == user.id,
    )
    return select(Project).where(or_(Project.owner_id == user.id, Project.id.in_(memberships)))


async def effective_agents(db, project_id: str) -> list[Agent]:
    direct = select(ProjectMember.member_id).where(
        ProjectMember.project_id == project_id,
        ProjectMember.member_type == "AGENT",
    )
    teams = select(ProjectMember.member_id).where(
        ProjectMember.project_id == project_id,
        ProjectMember.member_type == "TEAM",
    )
    indirect = select(TeamAgent.agent_id).where(TeamAgent.team_id.in_(teams))
    return list(
        (
            await db.scalars(
                select(Agent).where(or_(Agent.id.in_(direct), Agent.id.in_(indirect))).order_by(Agent.handle)
            )
        ).all()
    )


async def validate_members(db, ids: list[str]) -> None:
    if not ids or len(set(ids)) != len(ids):
        fail(422, "AI Team phải có ít nhất 1 agent, không trùng lặp", "validation_error")
    agents = list((await db.scalars(select(Agent).where(Agent.id.in_(ids), Agent.is_active.is_(True)))).all())
    if len(agents) != len(ids):
        fail(422, "Agent không tồn tại hoặc đã vô hiệu hóa", "validation_error")
