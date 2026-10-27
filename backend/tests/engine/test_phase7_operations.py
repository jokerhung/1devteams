import asyncio
import re
import sys

import pytest

from app.acp.security import scrub_data
from tests.api.conftest import project


async def test_windows_pty_resize_reconnect_and_expiry(engine_client):
    if sys.platform != "win32":
        pytest.skip("Windows PTY integration")
    client = engine_client
    entity = await project(client)
    manager = client.app.state.pty_manager
    manager.settings.terminal_idle_seconds = 1
    session = await manager.attach(client.owner["id"], entity["id"], client.workspace, 30, 120)
    assert not session.resumed
    try:
        await asyncio.to_thread(session.process.setwinsize, 40, 140)
        await asyncio.to_thread(
            session.process.write, "Write-Output ('PTY_'+'VERIFIED'); git status --short\r"
        )
        output = ""
        async with asyncio.timeout(15):
            while "PTY_VERIFIED" not in re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output):
                frame = await session.queue.get()
                assert frame["type"] == "output", frame
                output += frame["data"]
        with pytest.raises(ValueError):
            await manager.attach(client.owner["id"], entity["id"], client.workspace, 30, 120)
        pending_reconnect = asyncio.create_task(
            manager.attach(client.owner["id"], entity["id"], client.workspace, 30, 120)
        )
        await asyncio.sleep(0.05)
        assert not pending_reconnect.done()
        await manager.detach(session)
        resumed = await asyncio.wait_for(pending_reconnect, 2)
        assert resumed.id == session.id and "PTY_VERIFIED" in resumed.initial_replay
        assert resumed.resumed
        await manager.detach(resumed)
        # Output produced while disconnected is delivered as a delta, in order.
        after_seq = session.seq
        await asyncio.to_thread(session.process.write, "Write-Output ('DELTA_'+'VERIFIED')\r")
        async with asyncio.timeout(15):
            # Detached output has no queue notification; poll its bounded history.
            while "DELTA_VERIFIED" not in "".join(f["data"] for f in session.history):  # noqa: ASYNC110
                await asyncio.sleep(0.02)
        resumed = await manager.attach(
            client.owner["id"], entity["id"], client.workspace, 30, 120, session.id, after_seq
        )
        assert not resumed.reset
        assert [f["seq"] for f in resumed.initial_frames] == list(
            range(after_seq + 1, resumed.initial_seq + 1)
        )
        assert all(f["replay"] for f in resumed.initial_frames)
        await manager.detach(resumed)
        # A different session ID cannot apply a delta to an unrelated screen.
        resumed = await manager.attach(
            client.owner["id"], entity["id"], client.workspace, 30, 120, "stale-session", after_seq
        )
        assert resumed.reset
        assert "PTY_VERIFIED" in "".join(f["data"] for f in resumed.initial_frames)
        await manager.detach(resumed)
        await asyncio.wait_for(session.closed.wait(), 5)
        assert not await asyncio.to_thread(session.process.isalive)
    finally:
        await manager.close()
    events = (await client.get("/api/audit")).json()
    assert {e["action"] for e in events} >= {"terminal.open", "terminal.close"}


async def test_terminal_disabled_audit_metrics(engine_client):
    client = engine_client
    client.app.state.settings.enable_remote_terminal = False
    entity = await project(client)
    assert (await client.get(f"/api/projects/{entity['id']}/terminal")).json() == {"enabled": False}
    assert (
        await client.post(
            f"/api/projects/{entity['id']}/terminal/input", json={"type": "input", "data": "git status"}
        )
    ).status_code == 403
    assert (await client.get("/api/metrics")).status_code == 200
    assert (await client.get("/api/settings/adapters")).status_code == 200
    token = client.headers.pop("Authorization")
    try:
        assert (await client.get("/api/audit")).status_code == 401
    finally:
        client.headers["Authorization"] = token


def test_scrub_preserves_usage():
    value = scrub_data(
        {
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
            "api_key": "secret",
            "content": "Bearer abcdefgh sk-testsecret ghp_testsecret xoxb-testsecret",
        }
    )
    assert value["usage"] == {"prompt_tokens": 4, "completion_tokens": 2}
    assert "testsecret" not in str(value) and "abcdefgh" not in str(value)
