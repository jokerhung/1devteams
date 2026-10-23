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


async def guard_removed_agents(db, project_id: str, before: set[str]) -> None:
    """Reject changes that remove the last membership path to a workflow agent."""
    removed = before - {agent.id for agent in await effective_agents(db, project_id)}
    if not removed:
        return
    from app.db.models import Workflow, WorkflowVersion
    from app.services.agent_service import graph_uses

    used = []
    workflows = (
        await db.scalars(
            select(Workflow).where(Workflow.project_id == project_id, Workflow.status != "ARCHIVED")
        )
    ).all()
    for workflow in workflows:
        published = await db.scalar(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == workflow.id,
                WorkflowVersion.version == workflow.published_version,
            )
        )
        if any(
            graph_uses(workflow.graph, aid) or (published and graph_uses(published.graph, aid))
            for aid in removed
        ):
            used.append(workflow.name)
    if used:
        fail(409, "Không gỡ được: agent đang dùng trong workflow: " + ", ".join(used), "member_in_use")
