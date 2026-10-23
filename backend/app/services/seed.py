from sqlalchemy import func, select

from app.acp.types import PermissionProfile
from app.core.security import hash_password
from app.db.models import Agent, Team, TeamAgent, User
from app.engine.prompts import DEFAULT_SYSTEM_PROMPTS
from app.schemas.workflow import Graph

PRESETS = {
    "read_only": PermissionProfile().model_dump(),
    "developer": PermissionProfile(
        allow_write=True,
        allow_terminal=True,
        blocked_commands=["git commit", "git push", "git merge", "git reset", "rm -rf"],
    ).model_dump(),
    "tester": PermissionProfile(allow_terminal=True).model_dump(),
    "leader": PermissionProfile(allow_terminal=True, can_git_release=True).model_dump(),
    "custom": PermissionProfile().model_dump(),
}
DEFAULT_TEAM = "Core Bugfix Squad"


async def seed(db, settings) -> None:
    if not await db.scalar(select(func.count()).select_from(User)):
        if (
            settings.bootstrap_admin_email
            and settings.bootstrap_admin_password
            and settings.bootstrap_admin_password.get_secret_value()
        ):
            db.add(
                User(
                    email=settings.bootstrap_admin_email.lower(),
                    display_name="Owner",
                    password_hash=await hash_password(settings.bootstrap_admin_password.get_secret_value()),
                    system_role="OWNER",
                    avatar_initials="O",
                )
            )
    defaults = [
        ("@ba", "Business Analyst", "BA", "claude-code", "🐝", "sky", "read_only"),
        ("@developer", "Frontend Developer", "DEVELOPER", "claude-code", "🛠️", "amber", "developer"),
        ("@tester", "QA Tester", "TESTER", "codex", "🧪", "emerald", "tester"),
        ("@leader", "Tech Lead (Git Release)", "LEADER", "claude-code", "🚀", "purple", "leader"),
    ]
    agents = []
    for handle, display, role, runtime, icon, color, preset in defaults:
        agent = await db.scalar(select(Agent).where(Agent.handle == handle))
        if agent is None:
            agent = Agent(
                handle=handle,
                display_name=display,
                role_key=role,
                runtime=runtime,
                icon=icon,
                color=color,
                permission_profile=PRESETS[preset],
                system_prompt=DEFAULT_SYSTEM_PROMPTS[role],
                is_builtin=True,
            )
            db.add(agent)
            await db.flush()
        agents.append(agent)
    team = await db.scalar(select(Team).where(Team.name == DEFAULT_TEAM))
    if team is None:
        team = Team(name=DEFAULT_TEAM, description="Default bugfix team", icon="🐛")
        db.add(team)
        await db.flush()
        db.add_all(
            [TeamAgent(team_id=team.id, agent_id=agent.id, position=i) for i, agent in enumerate(agents)]
        )
    await db.commit()


def template_graph(name: str, agents: list[Agent]) -> Graph:
    if name == "blank":
        return Graph.model_validate(
            {
                "nodes": [
                    {"id": "start", "type": "start", "position": {"x": 0, "y": 0}},
                    {"id": "end", "type": "end", "position": {"x": 400, "y": 0}},
                ],
                "edges": [{"id": "e0", "source": "start", "target": "end"}],
            }
        )
    roles = {agent.role_key: agent.id for agent in agents if agent.is_active}
    specs = [
        ("start", "start", {}),
        ("n_ba", "agent", {"agent_id": roles.get("BA"), "routing": "ba"}),
        ("g_clar", "human_input", {"label": "BA hỏi lại người dùng"}),
        ("n_dev", "agent", {"agent_id": roles.get("DEVELOPER"), "routing": "none", "requires_write": True}),
        ("n_test", "agent", {"agent_id": roles.get("TESTER"), "routing": "tester"}),
        ("g_conf", "human_confirm", {"message": "Bạn xác nhận lỗi đã được sửa xong?"}),
        ("n_lead", "git_release", {"agent_id": roles.get("LEADER"), "push": True}),
        ("end", "end", {}),
    ]
    links = [
        ("start", "n_ba", None),
        ("n_ba", "g_clar", "need_info"),
        ("g_clar", "n_ba", None),
        ("n_ba", "n_dev", "ready"),
        ("n_dev", "n_test", None),
        ("n_test", "n_dev", "fail"),
        ("n_test", "g_conf", "pass"),
        ("g_conf", "n_lead", "approved"),
        ("g_conf", "n_dev", "rejected"),
        ("n_lead", "end", None),
    ]
    if name == "bugfix_with_security_review":
        security_id = roles.get("SECURITY")
        specs.insert(4, ("n_security", "agent", {"agent_id": security_id, "routing": "review"}))
        links = [(s, "n_security" if s == "n_dev" and t == "n_test" else t, h) for s, t, h in links]
        links += [("n_security", "n_test", "pass"), ("n_security", "n_dev", "fail")]
    return Graph.model_validate(
        {
            "nodes": [
                {"id": key, "type": kind, "data": data, "position": {"x": i * 180, "y": 0}}
                for i, (key, kind, data) in enumerate(specs)
            ],
            "edges": [
                {"id": f"e{i}", "source": source, "target": target, "sourceHandle": handle}
                for i, (source, target, handle) in enumerate(links)
            ],
        }
    )
