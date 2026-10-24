import asyncio

import pytest

from app.acp.types import ACPStreamEvent
from app.engine.retry import RuntimeFailure, overloaded, retry_after
from tests.engine.conftest import settled
from tests.engine.test_engine import make_ticket


@pytest.mark.parametrize("status,expected", [(429, True), (529, True), (401, False), (404, False)])
def test_retry_classification(status, expected):
    assert overloaded(RuntimeFailure("capacity", {"status_code": status}), "capacity") is expected
    assert retry_after("3") == 3
    assert retry_after("invalid") == 0


async def test_capacity_retries_fallback(engine_client, monkeypatch):
    client = engine_client
    client.app.state.settings.model_retry_delays = "30,60"
    waits = []

    async def wait(seconds):
        waits.append(seconds)

    monkeypatch.setattr("app.engine.nodes.wait_for_retry", wait)
    agents = (await client.get("/api/agents")).json()
    ba = next(a for a in agents if a["handle"] == "@ba")
    assert (
        await client.patch(f"/api/agents/{ba['id']}", json={"model": "primary", "fallback_model": "backup"})
    ).status_code == 200
    factory = client.factory
    attempts = []

    def overloaded_factory(cfg, workspace):
        session = factory(cfg, workspace)
        if cfg.handle == "@ba" and cfg.model == "primary":

            async def prompt(text):
                attempts.append(cfg.model)
                yield ACPStreamEvent(
                    agent_handle=cfg.handle,
                    event_type="error",
                    content="Selected model at capacity",
                    metadata={"status_code": 429, "retry_after": "45"},
                )

            session.prompt = prompt
        return session

    client.app.state.acp_pool.factory = overloaded_factory
    ticket, _ = await make_ticket(client, auto=True)
    await settled(client, ticket["id"], "WAITING_USER_CONFIRM")
    assert attempts == ["primary"] * 3
    assert waits == [45, 60]
    assert any(s.cfg.model == "backup" for s in factory.sessions)
    logs = (await client.get(f"/api/tickets/{ticket['id']}/messages?limit=1000")).json()
    assert any("backup" in e["content"] for e in logs if e["sender_type"] == "SYSTEM")


async def test_adhoc_preserves_status_and_stop(engine_client):
    client = engine_client
    ticket, _ = await make_ticket(client, auto=False)
    response = await client.post(
        f"/api/tickets/{ticket['id']}/messages", json={"text": "@ba explain the ticket"}
    )
    assert response.status_code == 201, response.text
    runner = client.app.state.ticket_runner
    if task := runner.adhoc_tasks.get(ticket["id"]):
        await asyncio.wait_for(asyncio.shield(task), 10)
    state = (await client.get(f"/api/tickets/{ticket['id']}/state")).json()
    assert state["status"] == "OPEN"
    assert "explain the ticket" in client.factory.prompts["@ba"][-1][0]
    client.factory.blocked.add("@ba")
    assert (
        await client.post(f"/api/tickets/{ticket['id']}/messages", json={"text": "@ba wait"})
    ).status_code == 201
    await asyncio.wait_for(client.factory.entered.wait(), 10)
    assert (await client.post(f"/api/tickets/{ticket['id']}/stop-agent")).status_code == 200
    assert ticket["id"] not in runner.adhoc_tasks
    assert (await client.get(f"/api/tickets/{ticket['id']}/state")).json()["status"] == "OPEN"


async def test_overload_gate_resume_after_model_change(engine_client):
    client = engine_client
    client.app.state.settings.model_retry_delays = "0,0"
    original = client.factory
    attempts = []

    def factory(cfg, workspace):
        session = original(cfg, workspace)
        if cfg.handle == "@ba" and cfg.model != "repaired":

            async def prompt(text):
                attempts.append(cfg.model)
                yield ACPStreamEvent(agent_handle=cfg.handle, event_type="error", content="capacity")

            session.prompt = prompt
        return session

    client.app.state.acp_pool.factory = factory
    ticket, _ = await make_ticket(client, auto=True)
    state = await settled(client, ticket["id"], "WAITING_USER_INPUT")
    assert state["waiting"]["payload"]["reason"] == "model_overload" and len(attempts) == 3
    ba = next(a for a in (await client.get("/api/agents")).json() if a["handle"] == "@ba")
    assert (await client.patch(f"/api/agents/{ba['id']}", json={"model": "repaired"})).status_code == 200
    assert (
        await client.post(f"/api/tickets/{ticket['id']}/reply", json={"text": "Retry"})
    ).status_code == 200
    await settled(client, ticket["id"], "WAITING_USER_CONFIRM")
    assert len(attempts) == 3


async def test_auth_error_no_retry(engine_client):
    client = engine_client
    original = client.factory
    attempts = []

    def factory(cfg, workspace):
        session = original(cfg, workspace)
        if cfg.handle == "@ba":

            async def prompt(text):
                attempts.append(text)
                yield ACPStreamEvent(
                    agent_handle=cfg.handle,
                    event_type="error",
                    content="Invalid API key (401)",
                    metadata={"status_code": 401},
                )

            session.prompt = prompt
        return session

    client.app.state.acp_pool.factory = factory
    ticket, _ = await make_ticket(client, auto=True)
    await settled(client, ticket["id"], "FAILED")
    assert len(attempts) == 1


async def test_adhoc_writer_lock_and_recovery_stash(engine_client):
    client = engine_client
    ticket, _ = await make_ticket(client)
    tid = ticket["id"]
    assert (
        await client.post(f"/api/tickets/{tid}/messages", json={"text": "@developer inspect"})
    ).status_code == 201
    runner = client.app.state.ticket_runner
    await asyncio.wait_for(asyncio.shield(runner.adhoc_tasks[tid]), 10)
    assert tid in runner.owned
    assert (await client.get(f"/api/tickets/{tid}/state")).json()["status"] == "OPEN"
    assert (await client.post(f"/api/tickets/{tid}/cancel")).status_code == 200
    assert tid not in runner.owned
    assert (await client.post(f"/api/tickets/{tid}/stash")).status_code == 200
    assert "aiteams-ticket-" in client.git("stash", "list")
    assert (client.workspace / "app.txt").read_text() == "original\n"
