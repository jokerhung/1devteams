"""Human terminal sessions; deliberately outside agent permission profiles."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.audit import audit, terminal_audit


class TerminalBusyError(ValueError):
    """The previous attachment may still be disconnecting."""


def spawn(workspace: Path, rows: int, cols: int) -> Any:
    # Never inherit server/provider secrets into an interactive shell.
    safe = {
        key: value
        for key, value in os.environ.items()
        if key.upper()
        in {
            "PATH",
            "PATHEXT",
            "SYSTEMROOT",
            "WINDIR",
            "COMSPEC",
            "TEMP",
            "TMP",
            "USERPROFILE",
            "HOME",
            "HOMEDRIVE",
            "HOMEPATH",
            "APPDATA",
            "LOCALAPPDATA",
            "LANG",
            "LC_ALL",
            "TERM",
        }
    }
    safe["TERM"] = "xterm-256color"
    if sys.platform == "win32":
        from winpty import PtyProcess

        return PtyProcess.spawn(
            "powershell.exe -NoLogo -NoProfile", cwd=str(workspace), env=safe, dimensions=(rows, cols)
        )
    from ptyprocess import PtyProcessUnicode

    return PtyProcessUnicode.spawn(
        ["/bin/bash", "--noprofile", "--norc"], cwd=str(workspace), env=safe, dimensions=(rows, cols)
    )


@dataclass
class Session:
    process: Any
    user_id: str
    project_id: str
    workspace: Path
    workspace_only: bool = False
    id: str = field(default_factory=lambda: str(uuid4()))
    queue: asyncio.Queue[dict[str, Any]] = field(default_factory=lambda: asyncio.Queue(maxsize=256))
    initial_replay: str = ""
    resumed: bool = False
    seq: int = 0
    history: deque[dict[str, Any]] = field(default_factory=deque)
    history_size: int = 0
    initial_frames: list[dict[str, Any]] = field(default_factory=list)
    initial_seq: int = 0
    reset: bool = True
    attached: bool = False
    detached_at: float = field(default_factory=time.monotonic)
    reader: asyncio.Task[None] | None = None
    closed: asyncio.Event = field(default_factory=asyncio.Event)
    detached: asyncio.Event = field(default_factory=asyncio.Event)


class PTYManager:
    def __init__(self, settings: Any, sessions: Any) -> None:
        self.settings, self.db = settings, sessions
        self.sessions: dict[tuple[str, str], Session] = {}
        self.lock = asyncio.Lock()
        self.reaper: asyncio.Task[None] | None = None

    async def attach(
        self,
        uid: str,
        pid: str,
        workspace: Path,
        rows: int,
        cols: int,
        session_id: str | None = None,
        after_seq: int = 0,
        *,
        workspace_only: bool = False,
    ) -> Session:
        # A reconnect may reach us before the previous WebSocket finishes closing.
        old = self.sessions.get((uid, pid))
        if old and old.attached:
            try:
                await asyncio.wait_for(old.detached.wait(), timeout=1.5)
            except TimeoutError:
                raise TerminalBusyError(
                    "Terminal đang mở ở tab khác; hãy đóng terminal ở tab đó trước"
                ) from None
        async with self.lock:
            key = (uid, pid)
            old = self.sessions.get(key)
            if old and (old.workspace != workspace or not await asyncio.to_thread(old.process.isalive)):
                await self._close(key)
                old = None
            if old and old.attached:
                raise TerminalBusyError("Terminal đang mở ở tab khác")
            resumed = old is not None
            if old is None:
                if len(self.sessions) >= self.settings.max_terminal_sessions:
                    raise ValueError("Đã đạt giới hạn terminal")
                process = await asyncio.to_thread(spawn, workspace, rows, cols)
                old = Session(process, uid, pid, workspace, workspace_only=workspace_only)
                self.sessions[key] = old
                old.reader = asyncio.create_task(self.read(old))
                await self.audit_event(old, "open")
            old.initial_replay = "".join(frame["data"] for frame in old.history)
            old.resumed = resumed
            old.initial_seq = old.seq
            first_seq = old.history[0]["seq"] if old.history else old.seq + 1
            old.reset = not (session_id == old.id and first_seq - 1 <= after_seq <= old.seq)
            old.initial_frames = [
                {**frame, "replay": resumed} for frame in old.history if old.reset or frame["seq"] > after_seq
            ]
            old.attached = True
            old.detached.clear()
            while not old.queue.empty():
                old.queue.get_nowait()
            if not self.reaper:
                self.reaper = asyncio.create_task(self.reap())
            return old

    async def read(self, session: Session) -> None:
        try:
            while True:
                data = await asyncio.to_thread(session.process.read, 4096)
                if not data:
                    break
                session.seq += 1
                frame = {"type": "output", "data": data, "seq": session.seq}
                session.history.append(frame)
                session.history_size += len(data)
                while (session.history_size > 262144 or len(session.history) > 4096) and len(
                    session.history
                ) > 1:
                    session.history_size -= len(session.history.popleft()["data"])
                if session.attached:
                    if session.queue.full():
                        # Explicit reconnect recovers retained terminal output.
                        while not session.queue.empty():
                            session.queue.get_nowait()
                        session.queue.put_nowait(
                            {
                                "type": "error",
                                "data": "Terminal output quá nhanh; kết nối lại",
                                "retryable": True,
                            }
                        )
                    else:
                        session.queue.put_nowait(frame)
        except (EOFError, OSError):
            pass
        finally:
            if not session.queue.full():
                session.queue.put_nowait({"type": "exit"})

    async def detach(self, session: Session) -> None:
        session.attached, session.detached_at = False, time.monotonic()
        session.detached.set()

    async def reap(self) -> None:
        while True:
            await asyncio.sleep(min(30, self.settings.terminal_idle_seconds))
            async with self.lock:
                for key, session in list(self.sessions.items()):
                    if (
                        not session.attached
                        and time.monotonic() - session.detached_at >= self.settings.terminal_idle_seconds
                    ):
                        await self._close(key)

    async def _close(self, key: tuple[str, str]) -> None:
        session = self.sessions[key]
        await asyncio.to_thread(session.process.close, force=True)
        if session.reader:
            session.reader.cancel()
            await asyncio.gather(session.reader, return_exceptions=True)
        await self.audit_event(session, "close")
        self.sessions.pop(key, None)
        session.closed.set()
        session.detached.set()

    async def close(self) -> None:
        if self.reaper:
            self.reaper.cancel()
            await asyncio.gather(self.reaper, return_exceptions=True)
        async with self.lock:
            for key in list(self.sessions):
                await self._close(key)

    async def audit_event(self, session: Session, action: str, data: str = "") -> None:
        if not session.workspace_only:
            await terminal_audit(self.db, session.user_id, session.project_id, action, data)
            return
        async with self.db() as db:
            await audit(
                db,
                "terminal.workspace." + action,
                str(session.workspace),
                user_id=session.user_id,
                payload={"data": data},
            )
            await db.commit()
