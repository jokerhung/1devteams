import asyncio
import json
from collections import deque

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import select

from app.db.models import Agent, Notification
from app.engine.compiler import compile_workflow
from app.engine.markers import parse_release, parse_route
from app.engine.runner import TicketRunner
from app.schemas.workflow import Graph
from app.services.agent_service import runtime_config
from tests.api.conftest import project
from tests.engine.conftest import settled


async def make_ticket(client, workflow=None, auto=False):
    entity = None
    if workflow is None:
        entity = await project(client, seeded=True)
        workflow = entity["workflow"]
    response = await client.post(
        f"/api/workflows/{workflow['id']}/tickets", json={"title": "Repair app", "auto_start": auto}
    )
    assert response.status_code == 201, response.text
    return response.json()["ticket"], entity


async def start(client, tid):
    response = await client.post(f"/api/tickets/{tid}/start")
    assert response.status_code == 200, response.text


async def test_compiler_default_template(engine_client):
    client = engine_client
    _, entity = await make_ticket(client)
    async with client.app.state.db_session() as db:
        agents = (await db.scalars(select(Agent))).all()
        configs = {a.id: runtime_config(a, client.app.state.settings) for a in agents}
    graph = Graph.model_validate(entity["workflow"]["graph"])
    assert compile_workflow(graph, configs, InMemorySaver())
    graph.edges = [e for e in graph.edges if e.source != "g_conf"]
    with pytest.raises(ValueError):
        compile_workflow(graph, configs, InMemorySaver())


async def test_ba_clarification_loop_and_notification_lifecycle(engine_client):
    client = engine_client
    client.factory.scripts["@ba"] = deque(["Question?\n@@ROUTE: need_info", "STR\n@@ROUTE: ready"])
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    state = await settled(client, tid, "WAITING_USER_INPUT")
    assert state["waiting"]["payload"]["question"] == "Question?"
    assert tid not in client.app.state.ticket_runner.owned
    response = await client.post(f"/api/tickets/{tid}/reply", json={"text": "Use large date range"})
    assert response.status_code == 200
    await settled(client, tid, "WAITING_USER_CONFIRM")
    assert "large date range" in client.factory.prompts["@ba"][1][0]
    assert tid in client.app.state.ticket_runner.owned
    async with client.app.state.db_session() as db:
        notifications = (await db.scalars(select(Notification).where(Notification.ticket_id == tid))).all()
        assert [(n.type, n.outcome) for n in notifications] == [("INPUT", "ANSWERED"), ("CONFIRM", None)]
    assert (await client.post(f"/api/tickets/{tid}/cancel")).status_code == 200
    async with client.app.state.db_session() as db:
        assert (
            await db.scalar(select(Notification).where(Notification.type == "CONFIRM"))
        ).outcome == "CANCELLED"


async def test_tester_fail_loops_back_and_confirm_reject(engine_client):
    client = engine_client
    client.factory.scripts["@tester"] = deque(["Bug remains\n@@ROUTE: fail", "Pass\n@@ROUTE: pass"])
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_CONFIRM")
    assert len(client.factory.prompts["@developer"]) == 2
    assert "Bug remains" in client.factory.prompts["@developer"][1][0]
    assert (
        await client.post(
            f"/api/tickets/{tid}/confirm", json={"approved": False, "feedback": "Fix pagination too"}
        )
    ).status_code == 200
    await settled(client, tid, "WAITING_USER_CONFIRM")
    assert "Fix pagination too" in client.factory.prompts["@developer"][2][0]
    async with client.app.state.db_session() as db:
        gates = (await db.scalars(select(Notification).where(Notification.ticket_id == tid))).all()
        assert len(gates) == 2 and gates[0].outcome == "REJECTED"


async def test_release_success_and_permission_denial(engine_client):
    client = engine_client
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_CONFIRM")
    original = client.git("rev-parse", "HEAD").strip()
    messages = (await client.get(f"/api/tickets/{tid}/messages")).json()
    assert any(m["event_type"] == "permission" and m["metadata"]["allowed"] is False for m in messages)
    assert (await client.post(f"/api/tickets/{tid}/confirm", json={"approved": True})).status_code == 200
    await settled(client, tid, "COMPLETED")
    current = client.git("rev-parse", "HEAD").strip()
    assert current != original
    remote_head = client.git("--git-dir", str(client.remote), "rev-parse", "main").strip()
    assert current == remote_head
    result = (await client.get(f"/api/tickets/{tid}")).json()["result"]
    assert result["commit_hash_full"] == current and result["files"] == ["app.txt"]
    assert not client.app.state.ticket_runner.owned


async def test_release_filters_sensitive_and_unrelated_index(engine_client):
    client = engine_client
    (client.workspace / ".env").write_text("PRIVATE=hidden")
    (client.workspace / "unrelated.txt").write_text("user staged content")
    client.git("add", "unrelated.txt")
    client.factory.scripts["@leader"].append(
        "@@RELEASE\n"
        + json.dumps(
            {"approve": True, "files": [".env", "app.txt"], "commit_message": "repair app", "concerns": []}
        )
        + "\n@@END"
    )
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_CONFIRM")
    await client.post(f"/api/tickets/{tid}/confirm", json={"approved": True})
    await settled(client, tid, "COMPLETED")
    assert client.git("diff", "--name-only", "HEAD~1", "HEAD").strip() == "app.txt"
    assert client.git("diff", "--cached", "--name-only").strip() == "unrelated.txt"
    assert "hidden" not in str(client.factory.prompts["@leader"])


async def test_missing_marker_followup_and_fallback(engine_client):
    client = engine_client
    client.factory.scripts["@ba"] = deque(["Forgot routing", "@@ROUTE: ready"])
    ticket, _ = await make_ticket(client, auto=True)
    await settled(client, ticket["id"], "WAITING_USER_CONFIRM")
    assert len(client.factory.prompts["@ba"]) == 2
    assert "@@ROUTE:" in client.factory.prompts["@ba"][1][0]


async def test_max_iterations(engine_client):
    client = engine_client
    client.factory.scripts["@tester"] = deque(["Fail\n@@ROUTE: fail"] * 6)
    ticket, _ = await make_ticket(client, auto=True)
    state = await settled(client, ticket["id"], "WAITING_USER_INPUT")
    assert state["waiting"]["node_id"] == "n_dev"
    assert "5" in state["waiting"]["payload"]["question"]
    assert len(client.factory.prompts["@developer"]) == 5
    assert ticket["id"] in client.app.state.ticket_runner.owned


async def test_workspace_queue_across_workflows(engine_client):
    client = engine_client
    first, entity = await make_ticket(client, auto=True)
    await settled(client, first["id"], "WAITING_USER_CONFIRM")
    duplicate = (
        await client.post(
            f"/api/workflows/{entity['workflow']['id']}/duplicate",
            json={"name": "Second flow", "ticket_prefix": "FEAT"},
        )
    ).json()
    await client.post(f"/api/workflows/{duplicate['id']}/publish")
    second, _ = await make_ticket(client, duplicate, auto=True)
    runner = client.app.state.ticket_runner
    async with runner.events.subscribe(f"tickets/{second['id']}"):
        # Waiting message may already be persisted, so poll registry only until task is queued.
        await asyncio.sleep(0.05)
        assert second["id"] in runner.tasks and second["id"] not in runner.owned
    assert (await client.get(f"/api/tickets/{second['id']}")).json()["status"] == "OPEN"
    await client.post(f"/api/tickets/{first['id']}/cancel")
    await settled(client, second["id"], "WAITING_USER_CONFIRM")


async def test_ticket_uses_snapshot_and_auto_start(engine_client):
    client = engine_client
    first, entity = await make_ticket(client, auto=True)
    await settled(client, first["id"], "WAITING_USER_CONFIRM")
    graph = entity["workflow"]["graph"]
    for node in graph["nodes"]:
        if node["id"] == "n_dev":
            node["data"]["instructions"] = "NEW SNAPSHOT INSTRUCTION"
    wid = entity["workflow"]["id"]
    await client.put(f"/api/workflows/{wid}/graph", json=graph)
    await client.post(f"/api/workflows/{wid}/publish")
    await client.post(f"/api/tickets/{first['id']}/confirm", json={"approved": False, "feedback": "Retry"})
    await settled(client, first["id"], "WAITING_USER_CONFIRM")
    assert "NEW SNAPSHOT" not in client.factory.prompts["@developer"][-1][0]
    await client.post(f"/api/tickets/{first['id']}/cancel")
    second, _ = await make_ticket(client, entity["workflow"], auto=True)
    await settled(client, second["id"], "WAITING_USER_CONFIRM")
    assert "NEW SNAPSHOT" in client.factory.prompts["@developer"][-1][0]


async def test_restart_resume(engine_client):
    client = engine_client
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_CONFIRM")
    old = client.app.state.ticket_runner
    await old.close()
    runner = TicketRunner(old.sessions, old.pool, old.events, old.settings, old.checkpointer)
    client.app.state.ticket_runner = runner
    await runner.recover()
    assert tid in runner.owned
    await client.post(f"/api/tickets/{tid}/confirm", json={"approved": True})
    await settled(client, tid, "COMPLETED")
    async with runner.sessions() as db:
        gates = (await db.scalars(select(Notification).where(Notification.ticket_id == tid))).all()
        assert len(gates) == 1 and gates[0].outcome == "APPROVED"
    await runner.close()


async def test_runtime_failure_retry_and_cancel(engine_client):
    client = engine_client
    client.factory.scripts["@ba"] = deque(["ERROR", "ERROR"])
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "FAILED")
    runner = client.app.state.ticket_runner
    graph, ctx, _ = await runner.load(tid)
    failed = await graph.aget_state(runner.config(tid, ctx))
    assert failed.values["error"] and failed.next == ("n_ba",)
    assert (await client.post(f"/api/tickets/{tid}/retry")).status_code == 200
    await settled(client, tid, "WAITING_USER_CONFIRM")
    recovered = await graph.aget_state(runner.config(tid, ctx))
    assert recovered.values["error"] is None
    await client.post(f"/api/tickets/{tid}/cancel")
    assert (await client.get(f"/api/tickets/{tid}")).json()["status"] == "CANCELLED"


async def test_cancel_does_not_require_compilable_snapshot(engine_client):
    client = engine_client
    ticket, _ = await make_ticket(client)
    tid = ticket["id"]
    agent = next(a for a in (await client.get("/api/agents")).json() if a["handle"] == "@ba")
    disabled = await client.patch(f"/api/agents/{agent['id']}", json={"is_active": False})
    assert disabled.status_code == 200, disabled.text
    assert (await client.post(f"/api/tickets/{tid}/start")).status_code == 409
    response = await client.post(f"/api/tickets/{tid}/cancel")
    assert response.status_code == 200, response.text
    assert (await client.get(f"/api/tickets/{tid}")).json()["status"] == "CANCELLED"
    state = await client.get(f"/api/tickets/{tid}/state")
    assert state.status_code == 200 and state.json()["status"] == "CANCELLED"


@pytest.mark.parametrize(
    "text,routing,route",
    [
        ("X\n@@ROUTE: ready\n@@ROUTE: need_info", "ba", "need_info"),
        ("[STATUS:TEST_PASSED]", "tester", "pass"),
        ("@@ROUTE: bogus", "ba", None),
    ],
)
def test_markers(text, routing, route):
    clean, actual = parse_route(text, routing)
    assert actual == route and "@@ROUTE" not in clean
    with pytest.raises(ValueError):
        parse_release("No JSON")
