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
    "tester": PermissionProfile(allow_terminal=True, allow_browser=True).model_dump(),
    "leader": PermissionProfile(allow_terminal=True, can_git_release=True).model_dump(),
    "custom": PermissionProfile().model_dump(),
}
DEFAULT_TEAM = "Core Bugfix Squad"


async def migrate_devops_agent(db) -> None:
    """Rename the built-in agent in place so workflow/team references remain valid."""
    agent = await db.scalar(select(Agent).where(Agent.is_builtin.is_(True), Agent.role_key == "LEADER"))
    if agent is None or agent.handle != "@leader":
        return
    conflict = await db.scalar(select(Agent.id).where(Agent.handle == "@devops", Agent.id != agent.id))
    if conflict:
        raise ValueError("Cannot rename built-in @leader: @devops is already used by another agent")
    agent.handle = "@devops"
    agent.display_name = "DevOps (Git Release)"
    agent.permission_profile = {**agent.permission_profile, "allow_terminal": True, "can_git_release": True}
    agent.system_prompt = DEFAULT_SYSTEM_PROMPTS["LEADER"]
    agent.config_version += 1
    await db.flush()


async def seed(db, settings) -> None:
    await migrate_devops_agent(db)
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
        ("@devops", "DevOps (Git Release)", "LEADER", "claude-code", "🚀", "purple", "leader"),
        ("@leader", "Leader (Điều phối)", "COORDINATOR", "claude-code", "🧭", "sky", "read_only"),
        ("@planner", "Implementation Planner", "PLANNER", "claude-code", "📋", "purple", "read_only"),
        ("@designer", "UI/UX Designer", "DESIGNER", "claude-code", "🎨", "amber", "read_only"),
        ("@workflow", "Workflow", "WORKFLOW", "claude-code", "🔀", "sky", "read_only"),
    ]
    agents = []
    added_feature_agents = []
    for handle, display, role, runtime, icon, color, preset in defaults:
        agent = await db.scalar(select(Agent).where(Agent.handle == handle))
        if agent is None:
            agent = Agent(
                handle=handle,
                display_name=display,
                role_key=role,
                runtime=runtime,
                description="Gợi ý: chọn model nhanh cho BA/Tester."
                if role in {"BA", "TESTER"}
                else "Gợi ý: chọn model mạnh cho Developer/DevOps.",
                icon=icon,
                color=color,
                permission_profile=PRESETS[preset],
                system_prompt=DEFAULT_SYSTEM_PROMPTS.get(
                    role,
                    (
                        "Bạn làm việc theo hướng dẫn của node workflow. "
                        "Đọc mã nguồn và tài liệu để xác minh. "
                        "Không tự commit/push."
                    ),
                ),
                is_builtin=True,
            )
            db.add(agent)
            await db.flush()
            if role in {"COORDINATOR", "PLANNER", "DESIGNER"}:
                added_feature_agents.append(agent)
        if role == "TESTER" and agent.is_builtin and "allow_browser" not in agent.permission_profile:
            agent.permission_profile = {**agent.permission_profile, "allow_browser": True}
            agent.config_version += 1
        if role != "WORKFLOW":
            agents.append(agent)
    team = await db.scalar(select(Team).where(Team.name == DEFAULT_TEAM))
    if team is None:
        team = Team(name=DEFAULT_TEAM, description="Default bugfix team", icon="🐛")
        db.add(team)
        await db.flush()
        db.add_all(
            [TeamAgent(team_id=team.id, agent_id=agent.id, position=i) for i, agent in enumerate(agents)]
        )
    else:
        for i, agent in enumerate(added_feature_agents, start=4):
            db.add(TeamAgent(team_id=team.id, agent_id=agent.id, position=i))
    await db.commit()


def template_graph(name: str, agents: list[Agent]) -> Graph:
    if name == "add_feature":
        from app.services.workflow_templates import feature_graph

        return feature_graph(agents)
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
