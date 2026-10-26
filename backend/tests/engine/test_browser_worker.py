"""Browser actions use real Chromium; provider replies are deterministic to isolate the bridge."""

import asyncio
import json
import threading
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import httpx
import pytest
from sqlalchemy import select

from app.acp.api_session import ApiAgentSession
from app.db.models import Attachment, Project, Ticket
from app.services.agent_service import policy
from app.services.browser_worker import BrowserAction, BrowserWorkerManager
from tests.api.conftest import ticket

LOGIN = b"""<!doctype html><title>Browser test</title><h1>Login</h1>
<form method="post" action="/login"><label>Username<input name="username"></label>
<label>Password<input name="password" type="password"></label><button>Log in</button></form>"""


@pytest.fixture
async def browser_site():
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, status, body, **headers):
            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name.replace("_", "-"), value)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/dashboard":
                if "test-session=ok" not in self.headers.get("Cookie", ""):
                    self.send(302, b"", Location="/login")
                else:
                    self.send(200, b"<h1>Dashboard</h1><p>Signed in as tester</p>")
            else:
                self.send(200, LOGIN)

        def do_POST(self):
            data = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
            if data == {"username": ["tester"], "password": ["correct-secret"]}:
                self.send(303, b"", Location="/dashboard", Set_Cookie="test-session=ok; Path=/; HttpOnly")
            else:
                self.send(401, LOGIN + b'<p role="alert">Invalid credentials</p>')

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        thread.join(timeout=3)


def actions(url, *, password="correct-secret", fail=False):
    return [
        {"action": "navigate", "url": url + "/login", "test_case": "Login"},
        {"action": "fill", "target": {"label": "Username"}, "value": "tester"},
        {"action": "fill", "target": {"label": "Password"}, "value": password, "secret": True},
        {"action": "click", "target": {"role": "button", "name": "Log in"}},
        {"action": "assert_url", "url": url + "/dashboard", "timeout_ms": 1000},
        {
            "action": "assert_visible",
            "target": {"role": "heading", "name": "Wrong" if fail else "Dashboard"},
            "timeout_ms": 100,
        },
    ]


def block(items):
    return "@@BROWSER\n" + json.dumps({"actions": items}) + "\n@@END"


async def setup_run(client):
    row = await ticket(client)
    runner = client.app.state.ticket_runner
    async with client.app.state.db_session() as db:
        entity = await db.get(Ticket, row["id"])
        project = await db.get(Project, entity.project_id)
    agents = (await client.get("/api/agents")).json()
    tester = next(agent for agent in agents if agent["handle"] == "@tester")
    return runner, entity, runner.context(entity, project), tester


async def test_real_browser_assertions_secrets_and_isolation(engine_client, browser_site):
    manager = BrowserWorkerManager(engine_client.app.state.settings)
    worker = manager.worker()
    try:
        for item in actions(browser_site):
            result = await worker.execute(BrowserAction.model_validate(item))
            assert result["status"] == "OK", result
            assert "correct-secret" not in json.dumps(result)
        report = worker.report(summary="No credentials in evidence: correct-secret")
        assert report["status"] == "PASS" and len(report["checks"]) == 2
        assert "correct-secret" not in json.dumps(report)
        assert (await worker.screenshot()).startswith(b"\x89PNG")
        other = manager.worker()
        result = await other.execute(BrowserAction(action="navigate", url=browser_site + "/dashboard"))
        assert result["url"].endswith("/login")  # A separate run cannot inherit authentication.
        assert other.report()["status"] == "BLOCKED"  # HTTP 200 is not a successful test.
        result = await other.execute(
            BrowserAction(
                action="assert_visible",
                target={"role": "heading", "name": "Dashboard"},
                timeout_ms=100,
            )
        )
        assert result["status"] == "FAIL" and other.report()["status"] == "FAIL"
    finally:
        await manager.close()
    assert not manager.workers


@pytest.mark.parametrize("custom_api", [False, True])
async def test_browser_chat_report_history_and_authorized_screenshot(engine_client, browser_site, custom_api):
    client = engine_client
    runner, entity, ctx, tester = await setup_run(client)
    replies = deque(
        [
            block(actions(browser_site)),
            block([{"action": "report", "summary": "Login verified"}]),
            "Login verified.\n@@ROUTE: pass",
        ]
    )
    if custom_api:
        response = await client.patch(
            f"/api/agents/{tester['id']}",
            json={
                "runtime": "openai-api",
                "base_url": "http://localhost/v1",
                "model": "test-model",
                "api_key": "test-provider-key",
                "permission_profile": {"allow_browser": True},
            },
        )
        assert response.status_code == 200, response.text

        async def respond(request):
            value = json.loads(request.content)
            assert (
                value["model"] == "test-model" and "Managed Browser Worker" in value["messages"][1]["content"]
            )
            text = replies.popleft()
            data = {"choices": [{"index": 0, "delta": {"content": text}, "finish_reason": "stop"}]}
            return httpx.Response(200, text="data: " + json.dumps(data) + "\n\ndata: [DONE]\n\n")

        def factory(cfg, workspace):
            return ApiAgentSession(
                cfg,
                workspace,
                transport=httpx.MockTransport(respond),
                policy=policy(client.app.state.settings),
            )

        client.app.state.acp_pool.factory = factory
    else:
        client.factory.scripts["@tester"].extend(replies)
    await runner.execute_adhoc(entity, ctx, tester["id"], "Test the login page and attach evidence")
    messages = (await client.get(f"/api/tickets/{entity.id}/messages?limit=1000")).json()
    reports = [message for message in messages if message["event_type"] == "browser_report"]
    assert len(reports) == 1, [(m["event_type"], m["content"]) for m in messages]
    report = reports[0]["metadata"]
    assert report["status"] == "PASS" and report["attachments"]
    assert "correct-secret" not in json.dumps(messages) and "@@BROWSER" not in json.dumps(messages)
    picture = report["attachments"][0]
    response = await client.get(picture["url"])
    assert response.status_code == 200 and response.content.startswith(b"\x89PNG")
    assert (await client.get(picture["thumbnail_url"])).status_code == 200
    async with client.app.state.db_session() as db:
        attachment = await db.get(Attachment, picture["id"])
        assert attachment.message_id == reports[0]["id"]
    history = (await client.get(f"/api/tickets/{entity.id}/history?limit=10")).json()
    turn = next(group for group in history["groups"] if group["type"] == "turn")
    assert turn["browserReports"][0]["attachments"][0]["id"] == picture["id"]
    assert turn["browserReports"][0]["status"] == "PASS"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=client.app), base_url="http://test"
    ) as anonymous:
        assert (await anonymous.get(picture["url"])).status_code == 401
    assert not runner.browser_manager.workers


async def test_failed_assertion_overrules_claim_and_incomplete_test_is_blocked(engine_client, browser_site):
    from app.engine.nodes import agent_turn
    from app.schemas.workflow import Node

    client = engine_client
    runner, entity, ctx, tester = await setup_run(client)
    client.factory.scripts["@tester"].extend(
        [
            block(actions(browser_site, fail=True)),
            "Everything passed!\n@@ROUTE: pass",
        ]
    )
    node = Node(id="web_test", type="agent", data={"agent_id": tester["id"], "routing": "tester"})
    state = {
        "ticket_id": entity.id,
        "workspace_path": str(ctx.git.workspace),
        "title": "Browser test",
        "description": "Test login on " + browser_site,
    }
    result = await agent_turn(node, state, ctx)
    messages = (await client.get(f"/api/tickets/{entity.id}/messages?limit=1000")).json()
    report = next(m for m in messages if m["event_type"] == "browser_report")
    assert report["metadata"]["status"] == "FAIL"
    assert ctx.completion_metadata["browser_status"] == "FAIL"
    assert result[3] == "fail"  # The model's pass route cannot override failing browser assertions.
    client.factory.scripts["@tester"].extend([block(actions(browser_site)[:1]), "ERROR"])
    await runner.execute_adhoc(entity, ctx, tester["id"], "Test interrupted")
    messages = (await client.get(f"/api/tickets/{entity.id}/messages?limit=1000")).json()
    reports = [m for m in messages if m["event_type"] == "browser_report"]
    assert reports[-1]["metadata"]["status"] == "BLOCKED"
    assert not runner.browser_manager.workers


async def test_browser_is_closed_and_reported_when_cancelled(engine_client, browser_site, monkeypatch):
    from app.services.browser_worker import BrowserWorker

    client = engine_client
    runner, entity, ctx, tester = await setup_run(client)
    waiting = asyncio.Event()
    execute = BrowserWorker.execute

    async def observe(self, action):
        if action.action == "wait_visible":
            waiting.set()
        return await execute(self, action)

    monkeypatch.setattr(BrowserWorker, "execute", observe)
    client.factory.scripts["@tester"].append(
        block(
            [
                actions(browser_site)[0],
                {"action": "wait_visible", "target": {"text": "Never shown"}},
            ]
        )
    )
    task = asyncio.create_task(runner.execute_adhoc(entity, ctx, tester["id"], "Test cancellation"))
    await asyncio.wait_for(waiting.wait(), 15)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not runner.browser_manager.workers
    messages = (await client.get(f"/api/tickets/{entity.id}/messages?limit=1000")).json()
    report = next(m for m in messages if m["event_type"] == "browser_report")
    assert report["metadata"]["status"] == "BLOCKED"


async def test_browser_permission_toggle_and_revoke(engine_client, browser_site):
    from app.engine.nodes import stream_turn

    client = engine_client
    runner, entity, ctx, tester = await setup_run(client)
    assert tester["permission_profile"]["allow_browser"]
    cfg = await ctx.agent(tester["id"])
    session = await ctx.pool.get_or_start(cfg, ctx.git.workspace, entity.id)
    response = await client.patch(
        f"/api/agents/{tester['id']}", json={"permission_profile": {"allow_browser": False}}
    )
    assert response.status_code == 200
    # A session that was already authorized must recheck access before dispatching commands.
    client.factory.scripts["@tester"].append(block(actions(browser_site)[:1]))
    session.turn_interrupted = False
    session.alive = True
    with pytest.raises(PermissionError, match="revoked"):
        await stream_turn(ctx, session, "Test login", "adhoc", "00000000-0000-0000-0000-000000000001")
    assert not runner.browser_manager.workers
    async with client.app.state.db_session() as db:
        from app.db.models import Agent
        from app.services.seed import seed

        await seed(db, client.app.state.settings)
        saved = await db.scalar(select(Agent).where(Agent.id == tester["id"]))
        assert (
            saved.permission_profile["allow_browser"] is False
        )  # Restart preserves the administrator's choice.
