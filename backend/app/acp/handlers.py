from __future__ import annotations

import asyncio
import difflib
import os
import sys
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.acp.guard import Decision, DynamicPermissionGuard, pick_option
from app.acp.jsonrpc import RPCError
from app.acp.process import stop_process
from app.acp.types import ACPStreamEvent, Json

Emit = Callable[[ACPStreamEvent], Awaitable[None]]


@dataclass
class Terminal:
    process: asyncio.subprocess.Process
    command: str
    limit: int
    data: bytes = b""
    truncated: bool = False
    pump: asyncio.Task[None] | None = field(default=None)

    async def collect(self) -> None:
        assert self.process.stdout
        while chunk := await self.process.stdout.read(8192):
            self.data += chunk
            if len(self.data) > self.limit:
                self.data = self.data[-self.limit :] if self.limit else b""
                self.truncated = True

    def output(self) -> str:
        return self.data.decode("utf-8", errors="ignore")


class ClientRequestHandlers:
    def __init__(self, guard: DynamicPermissionGuard, emit: Emit) -> None:
        self.guard, self.emit = guard, emit
        self.terminals: dict[str, Terminal] = {}
        self.modified_files: set[str] = set()
        self.session_id: str | None = None
        self._closed = False

    async def event(self, kind: str, content: str = "", **metadata: object) -> None:
        await self.emit(
            ACPStreamEvent(
                agent_handle=self.guard.agent_handle,
                event_type=kind,
                content=content,
                metadata=metadata,
            )
        )

    async def enforce(self, decision: Decision) -> None:
        if not decision.allowed:
            await self.event("permission", decision.reason, allowed=False, reason=decision.reason)
            raise RPCError(-32001, f"Permission denied: {decision.reason}")

    async def handle(self, method: str, params: Json) -> Json:
        if self._closed:
            raise RPCError(-32001, "Session closed")
        if self.session_id is not None and params.get("sessionId") != self.session_id:
            raise RPCError(-32001, "Invalid session ID")
        if method == "session/request_permission":
            decision = self.guard.evaluate_permission_request(params)
            await self.event(
                "permission",
                decision.reason,
                allowed=decision.allowed,
                reason=decision.reason,
                tool_call_id=params.get("toolCall", {}).get("toolCallId"),
            )
            return pick_option(params.get("options", []), decision.allowed)
        if method == "fs/read_text_file":
            await self.enforce(self.guard.check_read(params["path"]))
            path = self.guard.resolve_path(params["path"])
            content = await asyncio.to_thread(path.read_text, encoding="utf-8", errors="replace")
            start = int(params.get("line") or 1) - 1
            limit = params.get("limit")
            if start < 0 or (limit is not None and int(limit) < 0):
                raise RPCError(-32602, "Invalid line range")
            lines = content.splitlines(keepends=True)
            return {"content": "".join(lines[start : None if limit is None else start + int(limit)])}
        if method == "fs/write_text_file":
            await self.enforce(self.guard.check_write(params["path"]))
            path = self.guard.resolve_path(params["path"])
            old = await asyncio.to_thread(self._write, path, params["content"])
            self.modified_files.add(str(path))
            diff = "".join(
                difflib.unified_diff(
                    old.splitlines(True),
                    params["content"].splitlines(True),
                    fromfile=str(path),
                    tofile=str(path),
                )
            )
            await self.event(
                "file_edit", path=str(path), old_text=old, new_text=params["content"], unified_diff=diff
            )
            return {}
        if method == "terminal/create":
            await self.enforce(self.guard.check_command(params["command"], params.get("args")))
            cwd = self.guard.resolve_path(params.get("cwd") or str(self.guard.workspace))
            limit = int(params.get("outputByteLimit", 1024 * 1024))
            if limit < 0:
                raise RPCError(-32602, "Invalid output byte limit")
            # Cap retained output even if an untrusted adapter asks for an enormous buffer.
            limit = min(limit, 16 * 1024 * 1024)
            env = os.environ | {item["name"]: item["value"] for item in params.get("env", [])}
            # Disallow injected interpreter/git startup configuration at this execution boundary.
            if params.get("env"):
                raise RPCError(-32001, "Terminal environment overrides require an external sandbox")
            options = {"creationflags": 512} if sys.platform == "win32" else {"start_new_session": True}
            if params.get("args") is not None:
                command = [params["command"], *params["args"]]
            elif sys.platform == "win32":
                command = [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", params["command"]]
            else:
                command = ["/bin/sh", "-c", params["command"]]
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=cwd,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                **options,
            )
            terminal = Terminal(process, params["command"], limit)
            terminal.pump = asyncio.create_task(terminal.collect())
            terminal_id = str(uuid.uuid4())
            self.terminals[terminal_id] = terminal
            return {"terminalId": terminal_id}
        if method.startswith("terminal/"):
            terminal_id = params.get("terminalId", "")
            if terminal_id not in self.terminals:
                raise RPCError(-32602, "Unknown terminal ID")
            terminal = self.terminals[terminal_id]
            if method == "terminal/output":
                result: Json = {"output": terminal.output(), "truncated": terminal.truncated}
                if terminal.process.returncode is not None:
                    result["exitStatus"] = self._exit(terminal.process.returncode)
                return result
            if method == "terminal/wait_for_exit":
                code = await terminal.process.wait()
                if terminal.pump:
                    await terminal.pump
                await self.event(
                    "terminal_output", terminal.output(), command=terminal.command, exit_code=code
                )
                return self._exit(code)
            if method in ("terminal/kill", "terminal/release"):
                await self._stop(terminal)
                if method == "terminal/release":
                    self.terminals.pop(terminal_id, None)
                return {}
        raise RPCError(-32601, "Unsupported client method")

    @staticmethod
    def _write(path: Path, content: str) -> str:
        old = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return old

    @staticmethod
    def _exit(code: int) -> Json:
        return {"signal": str(-code)} if code < 0 else {"exitCode": code}

    async def _stop(self, terminal: Terminal) -> None:
        await stop_process(terminal.process)
        if terminal.pump:
            await terminal.pump

    async def close(self) -> None:
        self._closed = True
        await asyncio.gather(*(self._stop(item) for item in self.terminals.values()), return_exceptions=True)
        self.terminals.clear()
