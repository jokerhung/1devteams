import asyncio
import sys

import pytest
from fastapi import HTTPException

from app.services import adapter_actions
from app.services.adapter_actions import AdapterActions, command_for


def test_commands_are_allowlisted_and_use_provider_login(monkeypatch):
    monkeypatch.setattr(adapter_actions, "resolve_binary", lambda binary: f"/bin/{binary}")
    monkeypatch.setattr(adapter_actions.shutil, "which", lambda binary: "/bin/npm")
    assert command_for("codex-acp", "login") == ["/bin/codex", "login", "--device-auth"]
    assert command_for("claude-agent-acp", "login") == ["/bin/claude", "auth", "login"]
    assert command_for("codex-acp", "update") == [
        "/bin/npm",
        "install",
        "--save-dev",
        "--save-exact",
        "@agentclientprotocol/codex-acp@latest",
    ]
    assert command_for("claude", "install") == [
        "/bin/npm",
        "install",
        "--save-dev",
        "--save-exact",
        "@anthropic-ai/claude-code@latest",
    ]
    with pytest.raises(HTTPException) as error:
        command_for("arbitrary-command", "install")
    assert error.value.status_code == 404


async def test_jobs_stream_output_report_failure_and_are_private(monkeypatch):
    monkeypatch.setattr(
        adapter_actions,
        "command_for",
        lambda *args: [sys.executable, "-c", "print('progress'); raise SystemExit(3)"],
    )
    manager = AdapterActions()
    job = manager.start("codex", "install", "owner")
    assert job.task
    await job.task
    assert job.status == "failed"
    assert job.exit_code == 3
    assert "progress" in job.output
    assert "command" not in job.public()
    with pytest.raises(HTTPException):
        manager.get(job.id, "another-user")
    await manager.close()


async def test_jobs_prevent_duplicates_and_cancel_process(monkeypatch):
    monkeypatch.setattr(
        adapter_actions,
        "command_for",
        lambda *args: [sys.executable, "-u", "-c", "import time; print('ready'); time.sleep(60)"],
    )
    manager = AdapterActions()
    job = manager.start("codex", "login", "owner")
    try:
        with pytest.raises(HTTPException) as error:
            manager.start("claude", "update", "owner")
        assert error.value.status_code == 409
        async with asyncio.timeout(5):
            while "ready" not in job.output:  # noqa: ASYNC110 - verify actual subprocess output before cancellation
                await asyncio.sleep(0.01)
        await manager.cancel(job)
        assert job.status == "cancelled"
        assert job.process and job.process.returncode is not None
    finally:
        await manager.close()


async def test_adapter_api_actions_are_admin_only_and_reject_active_agent(engine_client, monkeypatch):
    client = engine_client
    runner = client.app.state.ticket_runner
    runner.tasks["active"] = object()
    try:
        response = await client.post("/api/settings/adapters/codex/actions", json={"action": "update"})
        assert response.status_code == 409
    finally:
        runner.tasks.pop("active")
    monkeypatch.setattr(adapter_actions, "command_for", lambda *args: [sys.executable, "-c", "print('ok')"])
    response = await client.post("/api/settings/adapters/codex/actions", json={"action": "install"})
    assert response.status_code == 202, response.text
    job_id = response.json()["id"]
    await client.app.state.adapter_actions.jobs[job_id].task
    value = (await client.get(f"/api/settings/adapter-actions/{job_id}")).json()
    assert value["status"] == "completed"
    assert (await client.get("/api/settings/adapter-actions")).json()["id"] == job_id
    token = client.headers.pop("Authorization")
    try:
        assert (await client.get("/api/settings/adapter-actions")).status_code == 401
        assert (
            await client.post("/api/settings/adapters/codex/actions", json={"action": "login"})
        ).status_code == 401
    finally:
        client.headers["Authorization"] = token
