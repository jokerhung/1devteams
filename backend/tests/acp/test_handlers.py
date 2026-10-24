import asyncio
import sys

import pytest

from app.acp.guard import Decision, DynamicPermissionGuard
from app.acp.handlers import ClientRequestHandlers
from app.acp.jsonrpc import RPCError
from app.acp.types import PermissionProfile


class PythonHarnessGuard(DynamicPermissionGuard):
    """Permit only these trusted subprocess fixtures to exercise terminal I/O.

    Production profiles now reject interpreter wrappers; their denial is covered
    by test_phase7_guard.py. These tests verify byte limits and child cleanup.
    """

    def check_command(self, command, args=None):
        assert command == sys.executable
        assert args in (["-c", "print('é' * 20)"], ["-c", "import time; time.sleep(30)"])
        return Decision(allowed=True, reason="Trusted terminal I/O fixture")


async def test_write_diff_and_read_range(tmp_path):
    events = []

    async def emit(event):
        events.append(event)

    handlers = ClientRequestHandlers(
        DynamicPermissionGuard(PermissionProfile(allow_write=True), tmp_path), emit
    )
    await handlers.handle("fs/write_text_file", {"path": "src/a.txt", "content": "a\nb\nc\n"})
    assert (tmp_path / "src/a.txt").read_text() == "a\nb\nc\n"
    assert "+b" in events[0].metadata["unified_diff"]
    assert await handlers.handle("fs/read_text_file", {"path": "src/a.txt", "line": 2, "limit": 1}) == {
        "content": "b\n"
    }
    await handlers.close()


async def test_denied_write_and_session_mismatch(tmp_path):
    events = []

    async def emit(event):
        events.append(event)

    handlers = ClientRequestHandlers(DynamicPermissionGuard(PermissionProfile(), tmp_path), emit)
    with pytest.raises(RPCError) as error:
        await handlers.handle("fs/write_text_file", {"path": "a", "content": "x"})
    assert error.value.code == -32001 and events[0].metadata["allowed"] is False
    handlers.session_id = "mine"
    with pytest.raises(RPCError):
        await handlers.handle("fs/read_text_file", {"sessionId": "other", "path": "a"})


@pytest.mark.parametrize("limit", [0, 7])
async def test_terminal_byte_limit_and_release(tmp_path, limit):
    events = []

    async def emit(event):
        events.append(event)

    handlers = ClientRequestHandlers(
        PythonHarnessGuard(PermissionProfile(allow_terminal=True), tmp_path), emit
    )
    result = await handlers.handle(
        "terminal/create",
        {"command": sys.executable, "args": ["-c", "print('é' * 20)"], "outputByteLimit": limit},
    )
    terminal_id = result["terminalId"]
    await handlers.handle("terminal/wait_for_exit", {"terminalId": terminal_id})
    output = await handlers.handle("terminal/output", {"terminalId": terminal_id})
    assert len(output["output"].encode()) <= limit and output["truncated"]
    assert output["exitStatus"]["exitCode"] == 0
    await handlers.handle("terminal/release", {"terminalId": terminal_id})
    assert not handlers.terminals
    await handlers.close()


async def test_terminal_close_kills_child(tmp_path):
    async def emit(event):
        pass

    handlers = ClientRequestHandlers(
        PythonHarnessGuard(PermissionProfile(allow_terminal=True), tmp_path), emit
    )
    result = await handlers.handle(
        "terminal/create", {"command": sys.executable, "args": ["-c", "import time; time.sleep(30)"]}
    )
    process = handlers.terminals[result["terminalId"]].process
    await asyncio.wait_for(handlers.close(), 8)
    assert process.returncode is not None
