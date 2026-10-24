import json

from sqlalchemy import func, select, update

from app.acp.types import AgentRuntimeConfig, APIParams, PermissionProfile
from app.acp.url_policy import URLPolicy, URLPolicyError
from app.core.deps import fail
from app.core.security import decrypt, encrypt
from app.db.models import Agent, Team, TeamAgent, Ticket, Workflow, WorkflowVersion
from app.schemas.agent import AgentOut
from app.services.common import fields
from app.services.seed import PRESETS


def unseal(value: str, settings) -> str:
    try:
        return decrypt(value, settings)
    except ValueError:
        fail(503, "APP_SECRET_KEY không có hoặc không giải mã được credential", "encryption_unavailable")


def policy(settings) -> URLPolicy:
    return URLPolicy(
        {v.strip().lower() for v in settings.api_allowed_http_hosts.split(",") if v.strip()},
        {v.strip().lower() for v in settings.api_allowed_private_hosts.split(",") if v.strip()},
    )


def public_agent(agent: Agent) -> dict:
    data = fields(agent)
    data.pop("api_key_enc")
    data["has_key"] = bool(agent.api_key_enc)
    data["api_params"] = {
        key: value for key, value in (agent.api_params or {}).items() if key != "extra_headers_enc"
    }
    return AgentOut.model_validate(data).model_dump(mode="json")


def api_parameters(agent: Agent, settings) -> dict:
    values = dict(agent.api_params or {})
    encrypted = values.pop("extra_headers_enc", None)
    values["extra_headers"] = json.loads(unseal(encrypted, settings)) if encrypted else {}
    return values


async def prepare_agent(body, settings, previous: Agent | None = None) -> dict:
    # Preserve SecretStr objects until encryption; never serialize them into audit/HTTP output.
    values = (
        {name: getattr(body, name) for name in body.model_fields_set}
        if previous
        else {name: getattr(body, name) for name in type(body).model_fields}
    )
    for key in (
        "display_name",
        "system_prompt",
        "runtime",
        "permission_profile",
        "icon",
        "color",
        "is_active",
        "role_key",
        "api_params",
    ):
        if key in values and values[key] is None:
            fail(422, "Không được để trống trường bắt buộc", "validation_error")
    if "role_key" in values:
        values["role_key"] = values["role_key"].upper()
        if previous and previous.is_builtin and values["role_key"] != previous.role_key:
            fail(422, "Không đổi role_key của agent built-in", "immutable_field")
    runtime = values.get("runtime", previous.runtime if previous else None)
    if (
        previous
        and runtime == "openai-api"
        and previous.runtime != runtime
        and "permission_profile" not in values
    ):
        values["permission_profile"] = PermissionProfile()
    if "permission_profile" in values:
        profile = values["permission_profile"]
        values["permission_profile"] = (
            PRESETS[profile].copy() if isinstance(profile, str) else profile.model_dump()
        )
    profile = values.get(
        "permission_profile", previous.permission_profile if previous else PRESETS["read_only"]
    )
    key = values.pop("api_key", None)
    if key is not None:
        raw = key.get_secret_value()
        if not raw:
            fail(422, "API key không được rỗng", "validation_error")
        old = unseal(previous.api_key_enc, settings) if previous and previous.api_key_enc else None
        if raw != old:
            try:
                values["api_key_enc"] = encrypt(raw, settings)
            except ValueError:
                fail(503, "Cần cấu hình APP_SECRET_KEY hợp lệ", "encryption_unavailable")
            values["api_key_last4"] = raw[-4:]
    if "api_params" in values:
        params = values["api_params"]
        headers = {name: val.get_secret_value() for name, val in params.extra_headers.items()}
        if previous and "extra_headers" not in params.model_fields_set:
            headers = api_parameters(previous, settings)["extra_headers"]
        if any(
            name.lower() in {"host", "content-length", "transfer-encoding", "connection"} for name in headers
        ):
            fail(422, "Header không an toàn", "validation_error")
        if any("\n" in name + value or "\r" in name + value for name, value in headers.items()):
            fail(422, "Header không hợp lệ", "validation_error")
        plain = params.model_dump(exclude={"extra_headers"}, exclude_none=True)
        old_plain = api_parameters(previous, settings) if previous else {}
        if previous and plain | {"extra_headers": headers} == old_plain:
            values["api_params"] = previous.api_params
        else:
            if headers:
                try:
                    plain["extra_headers_enc"] = encrypt(json.dumps(headers), settings)
                except ValueError:
                    fail(503, "Cần cấu hình APP_SECRET_KEY hợp lệ", "encryption_unavailable")
            values["api_params"] = plain
    if runtime == "openai-api":
        url = values.get("base_url", previous.base_url if previous else None)
        model = values.get("model", previous.model if previous else None)
        if not url or not model or not (values.get("api_key_enc") or (previous and previous.api_key_enc)):
            fail(422, "OpenAI Custom cần base_url, model và api_key", "validation_error")
        if any(profile.get(name) for name in ("allow_write", "allow_terminal", "can_git_release")):
            fail(
                422,
                "OpenAI Custom chỉ trả lời văn bản; không được ghi/chạy lệnh/phát hành Git",
                "validation_error",
            )
        try:
            await policy(settings).validate(url)
        except URLPolicyError:
            fail(422, "base_url không được phép hoặc không phân giải được", "unsafe_url")
    fallback_runtime = values.get("fallback_runtime", previous.fallback_runtime if previous else None)
    fallback_agent = values.get("fallback_agent_id", previous.fallback_agent_id if previous else None)
    if fallback_runtime == "openai-api" or fallback_agent:
        if any(profile.get(name) for name in ("allow_write", "allow_terminal", "can_git_release")):
            fail(422, "Fallback agent chỉ dành cho vai trò text-only", "unsafe_fallback")
        if not fallback_agent:
            fail(422, "Chọn fallback_agent_id cho API credential riêng", "invalid_fallback")
    return values


def graph_uses(graph: dict, agent_id: str) -> bool:
    return any(node.get("data", {}).get("agent_id") == agent_id for node in graph.get("nodes", []))


async def usage(db, agent: Agent) -> dict:
    workflows = list((await db.scalars(select(Workflow).where(Workflow.status != "ARCHIVED"))).all())
    used = []
    for flow in workflows:
        published = await db.scalar(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == flow.id, WorkflowVersion.version == flow.published_version
            )
        )
        if graph_uses(flow.graph, agent.id) or (published and graph_uses(published.graph, agent.id)):
            used.append(flow)
    running = []
    tickets = list(
        (
            await db.scalars(
                select(Ticket).where(
                    Ticket.status.in_(["RUNNING", "WAITING_USER_INPUT", "WAITING_USER_CONFIRM"])
                )
            )
        ).all()
    )
    for ticket in tickets:
        snapshot = await db.scalar(
            select(WorkflowVersion).where(
                WorkflowVersion.workflow_id == ticket.workflow_id,
                WorkflowVersion.version == ticket.workflow_version,
            )
        )
        if snapshot and graph_uses(snapshot.graph, agent.id):
            flow = await db.get(Workflow, ticket.workflow_id)
            running.append(
                {
                    "id": ticket.id,
                    "code": f"#{flow.ticket_prefix}-{ticket.number}",
                    "title": ticket.title,
                    "status": ticket.status,
                }
            )
    teams = list((await db.scalars(select(Team).join(TeamAgent).where(TeamAgent.agent_id == agent.id))).all())
    return {
        "running_tickets": running,
        "teams": [{"id": t.id, "name": t.name} for t in teams],
        "workflows": [{"id": w.id, "name": w.name} for w in used],
    }


async def guard_agent_removal(db, agent: Agent, deleting: bool = False) -> None:
    if deleting and agent.is_builtin:
        fail(409, "Không xóa agent built-in; hãy vô hiệu hóa", "agent_in_use")
    teams = list((await db.scalars(select(TeamAgent.team_id).where(TeamAgent.agent_id == agent.id))).all())
    for team_id in sorted(teams):
        await db.execute(update(Team).where(Team.id == team_id).values(updated_at=Team.updated_at))
        count = await db.scalar(
            select(func.count())
            .select_from(TeamAgent)
            .join(Agent)
            .where(TeamAgent.team_id == team_id, Agent.is_active.is_(True), Agent.id != agent.id)
        )
        if not count:
            fail(409, "Agent là thành viên hoạt động duy nhất của AI Team", "agent_in_use")
    used = await usage(db, agent)
    if used["running_tickets"] or (deleting and used["workflows"]):
        fail(409, "Agent đang được sử dụng; hãy vô hiệu hóa hoặc cập nhật workflow", "agent_in_use")


def runtime_config(agent: Agent, settings) -> AgentRuntimeConfig:
    return AgentRuntimeConfig(
        agent_id=agent.id,
        handle=agent.handle,
        runtime=agent.runtime,
        model=agent.model,
        fallback_model=agent.fallback_model,
        fallback_runtime=agent.fallback_runtime,
        fallback_agent_id=agent.fallback_agent_id,
        system_prompt=agent.system_prompt,
        permission_profile=PermissionProfile(**agent.permission_profile),
        config_version=agent.config_version,
        base_url=agent.base_url,
        api_key=unseal(agent.api_key_enc, settings) if agent.api_key_enc else None,
        api_params=APIParams(**api_parameters(agent, settings)),
    )
