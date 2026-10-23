"""Concurrent NDJSON RPC: agent requests never block response dispatch."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any

from app.acp.types import Json

logger = logging.getLogger(__name__)
Handler = Callable[[str, Json], Awaitable[Json]]
Notification = Callable[[str, Json], Awaitable[None]]


class ACPProcessExited(RuntimeError):
    pass


class RPCError(RuntimeError):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


class JsonRpcConnection:
    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        on_request: Handler,
        on_notification: Notification,
    ) -> None:
        self.reader, self.writer = reader, writer
        self.on_request, self.on_notification = on_request, on_notification
        self.pending: dict[int, asyncio.Future[Json]] = {}
        self._next_id = 0
        self._write_lock = asyncio.Lock()
        self._handlers: set[asyncio.Task[None]] = set()
        self.closed = False
        self._reader = asyncio.create_task(self._read_loop())

    async def _send(self, message: Json) -> None:
        async with self._write_lock:
            if self.closed:
                raise ACPProcessExited("ACP connection is closed")
            self.writer.write((json.dumps(message, ensure_ascii=False) + "\n").encode())
            await self.writer.drain()

    async def request(self, method: str, params: Json, timeout: float = 90) -> Json:
        self._next_id += 1
        request_id = self._next_id
        future: asyncio.Future[Json] = asyncio.get_running_loop().create_future()
        self.pending[request_id] = future
        try:
            await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
            return await asyncio.wait_for(future, timeout)
        finally:
            self.pending.pop(request_id, None)

    async def notify(self, method: str, params: Json) -> None:
        await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    async def respond(self, request_id: Any, result: Json | None = None, error: Json | None = None) -> None:
        await self._send(
            {"jsonrpc": "2.0", "id": request_id, **({"error": error} if error else {"result": result or {}})}
        )

    async def _handle(self, message: Json) -> None:
        result: Json | None = None
        failure: Json | None = None
        try:
            result = await self.on_request(message["method"], message.get("params", {}))
        except RPCError as error:
            failure = {"code": error.code, "message": str(error)}
        except Exception:
            # Do not leak arbitrary handler exception strings (commands, paths or credentials) onto the wire.
            failure = {"code": -32603, "message": "Client handler failed"}
        with suppress(ACPProcessExited, ConnectionError):
            await self.respond(message["id"], result=result, error=failure)

    async def _read_loop(self) -> None:
        try:
            while line := await self.reader.readline():
                try:
                    message = json.loads(line)
                    if not isinstance(message, dict):
                        raise ValueError("Invalid RPC object")
                    if "method" in message and (
                        not isinstance(message["method"], str)
                        or not isinstance(message.get("params", {}), dict)
                    ):
                        raise ValueError("Invalid RPC method/params")
                    if "id" in message and not isinstance(message["id"], (str, int)):
                        raise ValueError("Invalid RPC id")
                    if "result" in message and not isinstance(message["result"], dict):
                        raise ValueError("Invalid ACP result")
                    if "error" in message and not isinstance(message["error"], dict):
                        raise ValueError("Invalid RPC error")
                except (ValueError, UnicodeError):
                    logger.warning("Ignoring malformed ACP stdout line")
                    continue
                if "method" in message:
                    if "id" in message:
                        task = asyncio.create_task(self._handle(message))
                        self._handlers.add(task)
                        task.add_done_callback(self._handlers.discard)
                    else:
                        await self.on_notification(message["method"], message.get("params", {}))
                elif "id" in message:
                    future = self.pending.get(message["id"])
                    if future is not None and not future.done():
                        if "error" in message:
                            error = message["error"]
                            future.set_exception(
                                RPCError(error.get("code", -32603), error.get("message", "RPC error"))
                            )
                        else:
                            future.set_result(message.get("result", {}))
        except (Exception, asyncio.CancelledError):
            logger.debug("ACP reader stopped")
        finally:
            self.closed = True
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(ACPProcessExited("ACP stdout closed"))

    async def close(self) -> None:
        self.closed = True
        self._reader.cancel()
        tasks = list(self._handlers)
        for task in tasks:
            task.cancel()
        await asyncio.gather(self._reader, *tasks, return_exceptions=True)
        self.writer.close()
        try:
            await self.writer.wait_closed()
        except (BrokenPipeError, ConnectionError):
            pass
