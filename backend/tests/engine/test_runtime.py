import asyncio
import json
from collections import deque

import httpx
import pytest

from app.acp.api_session import ApiAgentSession
from app.acp.url_policy import URLPolicy
from app.engine.conditions import evaluate
from app.engine.runner import TicketRunner
from tests.engine.conftest import settled
from tests.engine.test_engine import make_ticket


async def test_agent_restart_midturn(engine_client):
    client = engine_client
    client.factory.blocked.add("@developer")
    ticket, _ = await make_ticket(client, auto=True)
    await asyncio.wait_for(client.factory.entered.wait(), 10)
    agent = next(a for a in (await client.get("/api/agents")).json() if a["handle"] == "@developer")
    client.factory.blocked.remove("@developer")
    response = await client.patch(
        f"/api/agents/{agent['id']}", json={"system_prompt": "Updated developer instructions"}
    )
    assert response.status_code == 200, response.text
    await settled(client, ticket["id"], "WAITING_USER_CONFIRM")
    turns = client.factory.prompts["@developer"]
    assert len(turns) == 2 and turns[1][1] == turns[0][1] + 1
    messages = (await client.get(f"/api/tickets/{ticket['id']}/messages")).json()
    assert any(m["event_type"] == "agent_restarted" for m in messages)
    assert any(m["event_type"] == "log" and "↻" in m["content"] for m in messages)
    assert any(m["event_type"] == "agent_turn_end" and m["sender_name"] == "@developer" for m in messages)


async def test_agent_restart_during_startup(engine_client):
    client = engine_client
    entered = asyncio.Event()

    def factory(cfg, workspace):
        session = client.factory(cfg, workspace)
        if cfg.handle == "@developer" and cfg.config_version == 1:

            async def start():
                entered.set()
                await asyncio.Event().wait()

            session.start = start
        return session

    client.app.state.acp_pool.factory = factory
    ticket, _ = await make_ticket(client, auto=True)
    await asyncio.wait_for(entered.wait(), 10)
    agent = next(a for a in (await client.get("/api/agents")).json() if a["handle"] == "@developer")
    response = await client.patch(
        f"/api/agents/{agent['id']}", json={"description": "Restart during startup"}
    )
    assert response.status_code == 200, response.text
    await settled(client, ticket["id"], "WAITING_USER_CONFIRM")
    assert client.factory.prompts["@developer"][0][1] == 2


async def test_checkpoint_reopen_new_connection(engine_client):
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

    client = engine_client
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_CONFIRM")
    old = client.app.state.ticket_runner
    await old.close()
    settings = old.settings
    context = (
        AsyncPostgresSaver.from_conn_string(settings.checkpoint_postgres_url.get_secret_value())
        if settings.checkpoint_postgres_url
        else AsyncSqliteSaver.from_conn_string(settings.checkpoint_db)
    )
    async with context as saver:
        await saver.setup()
        runner = TicketRunner(old.sessions, old.pool, old.events, settings, saver)
        client.app.state.ticket_runner = runner
        await runner.recover()
        assert tid in runner.owned
        await client.post(f"/api/tickets/{tid}/confirm", json={"approved": True})
        await settled(client, tid, "COMPLETED")
        events = (await client.get(f"/api/tickets/{tid}/messages?limit=1000")).json()
        assert sum(e["event_type"] == "gate_waiting" for e in events) == 1
        await runner.close()


async def test_message_with_attachments_and_manual_commands(engine_client):
    client = engine_client
    client.factory.scripts["@ba"] = deque(["More info?\n@@ROUTE: need_info", "Ready\n@@ROUTE: ready"])
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_INPUT")
    ids = []
    for filename in ["trace.log", "steps.txt"]:
        response = await client.post(
            f"/api/tickets/{tid}/attachments", files={"file": (filename, b"repro details", "text/plain")}
        )
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    response = await client.post(
        f"/api/tickets/{tid}/messages", json={"text": "@ba see attached", "attachment_ids": ids}
    )
    assert response.status_code == 201, response.text
    assert len(response.json()["metadata"]["attachments"]) == 2
    await settled(client, tid, "WAITING_USER_CONFIRM")
    assert ".aiteams" in client.factory.prompts["@ba"][-1][0]
    files = list((client.workspace / ".aiteams" / "attachments" / tid).iterdir())
    assert len(files) == 2
    assert ".aiteams" not in client.git("status", "--porcelain", "--untracked-files=all")
    assert (await client.post(f"/api/tickets/{tid}/messages", json={"text": "@devops OK"})).status_code == 201
    await settled(client, tid, "COMPLETED")
    assert ".aiteams" not in client.git("ls-tree", "-r", "--name-only", "HEAD")


async def test_api_agent_text_only_custom_insertion(engine_client):
    client = engine_client
    ticket, entity = await make_ticket(client)
    pid = entity["id"]
    response = await client.post(
        "/api/agents",
        json={
            "handle": "@security_checker",
            "display_name": "Security",
            "runtime": "openai-api",
            "base_url": "http://localhost/v1",
            "api_key": "private-test-key",
            "model": "review-model",
        },
    )
    assert response.status_code == 201, response.text
    aid = response.json()["id"]
    assert (
        await client.post(f"/api/projects/{pid}/members", json={"member_type": "AGENT", "member_id": aid})
    ).status_code == 201
    (client.workspace / "context.txt").write_text("reference code\n" * 3000)
    (client.workspace / ".env").write_text("SECRET_CONTEXT=never-expose")
    graph = entity["workflow"]["graph"]
    graph["nodes"].append(
        {
            "id": "security",
            "type": "agent",
            "data": {
                "agent_id": aid,
                "routing": "review",
                "context_files": ["context.txt", ".env", "../escape"],
            },
        }
    )
    for edge in graph["edges"]:
        if edge["source"] == "n_dev":
            edge["target"] = "security"
    graph["edges"] += [
        {"id": "sec-pass", "source": "security", "target": "n_test", "sourceHandle": "pass"},
        {"id": "sec-fail", "source": "security", "target": "n_dev", "sourceHandle": "fail"},
    ]
    wid = entity["workflow"]["id"]
    assert (await client.put(f"/api/workflows/{wid}/graph", json=graph)).status_code == 200
    assert (await client.post(f"/api/workflows/{wid}/publish")).status_code == 200
    requests = []

    async def handler(request):
        payload = json.loads(request.content)
        requests.append(payload)
        delta = {"choices": [{"delta": {"content": "Security pass\n@@ROUTE: pass"}, "finish_reason": "stop"}]}
        return httpx.Response(
            200,
            text="data: " + json.dumps(delta) + "\n\ndata: [DONE]\n\n",
            headers={"Content-Type": "text/event-stream"},
        )

    def factory(cfg, workspace):
        if cfg.runtime == "openai-api":
            return ApiAgentSession(
                cfg,
                workspace,
                policy=URLPolicy({"localhost"}, {"localhost"}),
                transport=httpx.MockTransport(handler),
            )
        return client.factory(cfg, workspace)

    client.app.state.acp_pool.factory = factory
    new, _ = await make_ticket(client, entity["workflow"], auto=True)
    await settled(client, new["id"], "WAITING_USER_CONFIRM")
    assert len(requests) == 1
    payload = requests[0]
    assert "tools" not in payload and "tool_choice" not in payload
    prompt = payload["messages"][-1]["content"]
    assert "repair 1" in prompt and "reference code" in prompt and "[truncated]" in prompt
    assert "never-expose" not in prompt
    assert "không có công cụ" in prompt
    runner = client.app.state.ticket_runner
    compiled, ctx, _ = await runner.load(new["id"])
    state = (await compiled.aget_state(runner.config(new["id"], ctx))).values
    output = next(o for o in state["outputs"] if o["node_id"] == "security")
    assert output["modified_files"] == [] and output["route"] == "pass"
    bad = json.loads(json.dumps(graph))
    next(n for n in bad["nodes"] if n["id"] == "n_lead")["data"]["agent_id"] = aid
    result = await client.put(f"/api/workflows/{wid}/graph", json=bad)
    assert result.status_code == 200
    assert (await client.post(f"/api/workflows/{wid}/publish")).status_code == 400


async def test_restart_marks_running_failed_and_retry(engine_client):
    client = engine_client
    client.factory.blocked.add("@developer")
    ticket, _ = await make_ticket(client, auto=True)
    await asyncio.wait_for(client.factory.entered.wait(), 10)
    old = client.app.state.ticket_runner
    await old.close()
    client.factory.blocked.clear()
    runner = TicketRunner(old.sessions, old.pool, old.events, old.settings, old.checkpointer)
    client.app.state.ticket_runner = runner
    await runner.recover()
    assert (await client.get(f"/api/tickets/{ticket['id']}")).json()["result"]["error"] == "server restart"
    assert (await client.post(f"/api/tickets/{ticket['id']}/retry")).status_code == 200
    await settled(client, ticket["id"], "WAITING_USER_CONFIRM")
    assert len(client.factory.prompts["@ba"]) == 1  # retry resumes checkpoint, not the start node
    await runner.close()


async def test_action_authorization(engine_client):
    client = engine_client
    ticket, entity = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_CONFIRM")
    response = await client.post(
        "/api/users",
        json={"email": "reporter@example.com", "display_name": "Reporter", "password": "Password123!"},
    )
    uid = response.json()["id"]
    token = (
        await client.post(
            "/api/auth/login", json={"email": "reporter@example.com", "password": "Password123!"}
        )
    ).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    assert (
        await client.post(f"/api/tickets/{tid}/confirm", headers=headers, json={"approved": True})
    ).status_code == 403
    await client.post(
        f"/api/projects/{entity['id']}/members",
        json={"member_type": "USER", "member_id": uid, "project_role": "REPORTER"},
    )
    assert (
        await client.post(f"/api/tickets/{tid}/confirm", headers=headers, json={"approved": True})
    ).status_code == 403
    assert (
        await client.post(f"/api/tickets/{tid}/messages", headers=headers, json={"text": "@devops OK"})
    ).status_code == 403
    assert (await client.post(f"/api/tickets/{tid}/cancel", headers=headers)).status_code == 200


@pytest.mark.parametrize(
    "expression,state,result",
    [
        ('last_route.n_ba == "ready"', {"last_route": {"n_ba": "ready"}}, True),
        ("len(modified_files) > 0", {"modified_files": ["a"]}, True),
        ("iteration.n-test >= 2", {"iteration": {"n-test": 1}}, False),
    ],
)
def test_conditions(expression, state, result):
    assert evaluate(expression, state) is result
    with pytest.raises(ValueError):
        evaluate('__import__("os").system("whoami")', {})
