"""ACP sessions with per-turn event streams and bounded subprocess lifetime."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from pathlib import Path

from app.acp.guard import DynamicPermissionGuard
from app.acp.handlers import ClientRequestHandlers
from app.acp.jsonrpc import ACPProcessExited, JsonRpcConnection, RPCError
from app.acp.process import stop_process
from app.acp.security import scrub, scrub_data
from app.acp.types import ACPEventType, ACPStreamEvent, AgentRuntimeConfig, Json, PromptResult, RuntimeType
from app.core.config import Settings, get_settings, resolve_binary

logger = logging.getLogger(__name__)
BinResolver = Callable[[RuntimeType], list[str]]


def is_provider_variable(name: str) -> bool:
    return name.upper().startswith(("ANTHROPIC_", "OPENAI_")) or name.upper() in {
        "CODEX_API_KEY",
        "CODEX_CONFIG",
        "MODEL_PROVIDER",
        "DEFAULT_AUTH_REQUEST",
    }


class RuntimePolicyError(RuntimeError):
    pass


def default_resolver(runtime: RuntimeType, settings: Settings | None = None) -> list[str]:
    settings = settings or get_settings()
    name = settings.claude_acp_bin if runtime == "claude-code" else settings.codex_acp_bin
    binary = resolve_binary(name)
    if binary is None:
        raise FileNotFoundError(f"ACP binary not found for {runtime}")
    if sys.platform == "win32" and Path(binary).suffix.lower() in (".cmd", ".bat"):
        return [os.environ.get("COMSPEC", "cmd.exe"), "/d", "/c", binary]
    return [binary]


class ACPSession:
    def __init__(
        self,
        cfg: AgentRuntimeConfig,
        workspace: Path,
        bin_resolver: BinResolver = default_resolver,
        *,
        timeout: float | None = None,
        client_tools_only: bool = False,
        diagnostic: bool = False,
        trusted_native: bool = False,
        inherit_provider_env: bool = True,
        provider_env: dict[str, str] | None = None,
    ) -> None:
        self.cfg = cfg.model_copy(deep=True)
        self.workspace = workspace.resolve()
        self.config_version = cfg.config_version
        self.bin_resolver = bin_resolver
        self.timeout = timeout if timeout is not None else get_settings().acp_prompt_timeout_sec
        # An operator must establish client-only tool routing for their adapter. Capabilities alone
        # are not evidence. The diagnostic escape hatch is for disposable real-ACP tests only.
        self.client_tools_only, self.diagnostic = client_tools_only, diagnostic
        # Explicit host-operator opt-in. This is not evidence of guard coverage or a sandbox.
        self.trusted_native = trusted_native
        self.inherit_provider_env = inherit_provider_env
        self.provider_env = dict(provider_env or {})
        self._scrub_cfg = self.cfg.model_copy(deep=True)
        self._scrub_cfg.env.update(self.provider_env)
        self.process: asyncio.subprocess.Process | None = None
        self.rpc: JsonRpcConnection | None = None
        self.session_id: str | None = None
        self.model_effective: str | None = None
        self.runtime_version: str | None = None
        self.available_models: list[Json] = []
        self.agent_capabilities: Json = {}
        self.modified_files: set[str] = set()
        self.turn_interrupted = False
        self.busy = False
        self.last_used = time.monotonic()
        self._queue: asyncio.Queue[ACPStreamEvent] = asyncio.Queue()
        self._stderr: deque[str] = deque(maxlen=50)
        self._stderr_task: asyncio.Task[None] | None = None
        self._turn: asyncio.Task[None] | None = None
        self._closed = False
        self._first_prompt = True
        self.handlers = ClientRequestHandlers(
            DynamicPermissionGuard(
                cfg.permission_profile, self.workspace, cfg.handle, trusted_native=trusted_native
            ),
            self._emit,
        )

    @property
    def alive(self) -> bool:
        return (
            not self._closed
            and self.process is not None
            and self.process.returncode is None
            and bool(self.rpc and not self.rpc.closed)
        )

    async def start(self) -> None:
        if self.alive:
            return
        if self._closed:
            raise RuntimeError("Session has been closed")
        if not self.client_tools_only and not self.diagnostic and not self.trusted_native:
            raise RuntimePolicyError(
                "Native adapter tool approval coverage is unverified; require client-only routing or an "
                "external sandbox. Diagnostic mode is restricted to disposable workspaces."
            )
        if self.trusted_native:
            logger.warning(
                "Trusted native ACP enabled for agent=%s: native tools may bypass the client guard",
                self.cfg.handle,
            )
        env = (
            {
                key: value
                for key, value in os.environ.items()
                if self.inherit_provider_env or not is_provider_variable(key)
            }
            | self.provider_env
            | self.cfg.env
        )
        self._scrub_cfg.env.update(
            {
                key: value
                for key, value in env.items()
                if is_provider_variable(key) and any(part in key.upper() for part in ("KEY", "TOKEN", "AUTH"))
            }
        )
        if self.cfg.runtime == "codex":
            env["INITIAL_AGENT_MODE"] = "read-only"
        options = {"creationflags": 512} if sys.platform == "win32" else {"start_new_session": True}
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.bin_resolver(self.cfg.runtime),
                cwd=self.workspace,
                env=env,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=16 * 1024 * 1024,
                **options,
            )
            assert self.process.stdout and self.process.stdin
            self._stderr_task = asyncio.create_task(self._drain_stderr())
            self.rpc = JsonRpcConnection(
                self.process.stdout, self.process.stdin, self.handlers.handle, self._notification
            )
            initialized = await self.rpc.request(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {
                        "fs": {"readTextFile": True, "writeTextFile": True},
                        "terminal": True,
                    },
                    "clientInfo": {"name": "aiteams", "version": "0.1.0"},
                },
            )
            if initialized.get("protocolVersion") != 1:
                raise RPCError(-32602, "Unsupported ACP protocol version")
            self.runtime_version = initialized.get("agentInfo", {}).get("version")
            self.agent_capabilities = initialized.get("agentCapabilities", {})
            params: Json = {"cwd": str(self.workspace), "mcpServers": []}
            if self.cfg.runtime == "claude-code":
                params["_meta"] = {"systemPrompt": {"append": self.cfg.system_prompt}}
            session = await self.rpc.request("session/new", params)
            self.session_id = session["sessionId"]
            self.handlers.session_id = self.session_id
            # Pin a conservative permission mode; it does NOT prove complete native tool mediation.
            modes = {mode["id"] for mode in session.get("modes", {}).get("availableModes", [])}
            desired = "default" if self.cfg.runtime == "claude-code" else "read-only"
            if desired in modes:
                await self.rpc.request("session/set_mode", {"sessionId": self.session_id, "modeId": desired})
            config: Json = next(
                (item for item in session.get("configOptions", []) if item.get("id") == "model"), {}
            )
            self.model_effective = session.get("models", {}).get("currentModelId") or config.get(
                "currentValue"
            )
            self.available_models = session.get("models", {}).get("availableModels", []) or config.get(
                "options", []
            )
            if self.cfg.model:
                try:
                    if config and self.cfg.runtime == "claude-code":
                        await self.rpc.request(
                            "session/set_config_option",
                            {
                                "sessionId": self.session_id,
                                "configId": "model",
                                "value": self.cfg.model,
                            },
                        )
                    else:
                        await self.rpc.request(
                            "session/set_model",
                            {
                                "sessionId": self.session_id,
                                "modelId": self.cfg.model,
                            },
                        )
                    self.model_effective = self.cfg.model
                except (RPCError, TimeoutError):
                    logger.warning(
                        "Model selection unavailable for agent=%s; retaining adapter default", self.cfg.handle
                    )
        except BaseException:
            await self.close()
            raise

    async def _emit(self, event: ACPStreamEvent) -> None:
        safe = ACPStreamEvent.model_validate(scrub_data(event.model_dump(), self._scrub_cfg))
        await self._queue.put(safe)

    async def _drain_stderr(self) -> None:
        assert self.process and self.process.stderr
        buffer = b""
        dropping = False
        while chunk := await self.process.stderr.read(8192):
            pieces = (buffer + chunk).split(b"\n")
            buffer = pieces.pop()
            for line in pieces:
                if not dropping:
                    self._record_stderr(line)
                dropping = False
            if len(buffer) > 65536:
                # Keep draining oversized lines without retaining/logging partial secrets.
                buffer = b""
                dropping = True
        if buffer and not dropping:
            self._record_stderr(buffer)

    def _record_stderr(self, line: bytes) -> None:
        safe = scrub(line.decode("utf-8", errors="replace").rstrip(), self._scrub_cfg)
        self._stderr.append(safe)
        logger.debug("ACP stderr agent=%s %s", self.cfg.handle, safe)

    async def _notification(self, method: str, params: Json) -> None:
        if method != "session/update" or not self.busy or params.get("sessionId") != self.session_id:
            return
        update = params.get("update", {})
        kind = update.get("sessionUpdate")
        mapping: dict[str, ACPEventType] = {
            "agent_message_chunk": "message_chunk",
            "agent_thought_chunk": "thought_chunk",
            "tool_call": "tool_call",
            "tool_call_update": "tool_call_update",
            "plan": "plan",
        }
        if kind in mapping:
            content = update.get("content", {})
            text = content.get("text", "") if isinstance(content, dict) else ""
            await self._emit(
                ACPStreamEvent(
                    agent_handle=self.cfg.handle, event_type=mapping[kind], content=text, metadata=update
                )
            )
            if kind in ("tool_call", "tool_call_update"):
                if update.get("kind") == "edit":
                    self.modified_files.update(
                        item["path"] for item in update.get("locations", []) if "path" in item
                    )
                for item in content if isinstance(content, list) else []:
                    if item.get("type") == "diff":
                        self.modified_files.add(item["path"])
                        await self._emit(
                            ACPStreamEvent(
                                agent_handle=self.cfg.handle,
                                event_type="file_edit",
                                metadata={
                                    "path": item["path"],
                                    "old_text": item.get("oldText"),
                                    "new_text": item.get("newText"),
                                },
                            )
                        )
            meta = update.get("_meta", {})
            if delta := meta.get("terminal_output_delta"):
                await self._emit(
                    ACPStreamEvent(
                        agent_handle=self.cfg.handle,
                        event_type="terminal_output",
                        content=delta.get("data", ""),
                        metadata=delta,
                    )
                )
        else:
            logger.debug("Ignored ACP update type=%s", kind)

    async def prompt(self, text: str, *, images: list[Json] | None = None) -> AsyncIterator[ACPStreamEvent]:
        if images and not self.agent_capabilities.get("promptCapabilities", {}).get("image"):
            raise ValueError("Adapter does not advertise image prompts")
        if self.busy:
            raise RuntimeError("Concurrent prompts on one session are not supported")
        if not self.alive:
            raise ACPProcessExited("Session is not alive")
        self.busy = True
        self.turn_interrupted = False
        self.last_used = time.monotonic()
        self._queue = asyncio.Queue()
        if self.trusted_native:
            await self._emit(
                ACPStreamEvent(
                    agent_handle=self.cfg.handle,
                    event_type="log",
                    content=(
                        "Chế độ native tin cậy đang bật trên máy chủ. Công cụ native có thể chạy "
                        "trực tiếp với quyền tài khoản hệ điều hành; permission profile chưa bảo đảm "
                        "kiểm soát toàn bộ công cụ của adapter."
                    ),
                    metadata={"runtime_policy": "trusted_native", "guard_coverage_verified": False},
                )
            )
        self.modified_files.clear()
        self.handlers.modified_files.clear()
        prefix = (
            f"[SYSTEM ROLE]\n{self.cfg.system_prompt}\n\n"
            if self._first_prompt and self.cfg.runtime == "codex"
            else ""
        )
        self._first_prompt = False

        async def run() -> None:
            assert self.rpc
            try:
                result = await self.rpc.request(
                    "session/prompt",
                    {
                        "sessionId": self.session_id,
                        "prompt": [{"type": "text", "text": prefix + text}, *(images or [])],
                    },
                    self.timeout,
                )
                await self._emit(
                    ACPStreamEvent(
                        agent_handle=self.cfg.handle,
                        event_type="completed",
                        metadata={"stop_reason": result.get("stopReason", "unknown")},
                    )
                )
            except TimeoutError:
                await self.cancel()
                await self._emit(
                    ACPStreamEvent(
                        agent_handle=self.cfg.handle, event_type="error", content="ACP prompt timed out"
                    )
                )
                # A late response must never be mistaken for the next turn.
                self._closed = True
            except asyncio.CancelledError:
                await self._emit(
                    ACPStreamEvent(
                        agent_handle=self.cfg.handle,
                        event_type="error",
                        content="Turn interrupted",
                        metadata={"turn_interrupted": self.turn_interrupted},
                    )
                )
            except Exception as error:
                await asyncio.sleep(0)  # Allow the stderr drainer to observe a process's final lines.
                await self._emit(
                    ACPStreamEvent(
                        agent_handle=self.cfg.handle,
                        event_type="error",
                        content=scrub(str(error), self._scrub_cfg),
                        metadata={"stderr": list(self._stderr)},
                    )
                )

        self._turn = asyncio.create_task(run())
        full_text = ""
        try:
            while True:
                event = await self._queue.get()
                if event.event_type == "message_chunk":
                    full_text += event.content
                if event.event_type == "completed":
                    self.modified_files.update(self.handlers.modified_files)
                    event.metadata.update(
                        PromptResult(
                            stop_reason=event.metadata["stop_reason"],
                            full_text=full_text,
                            modified_files=sorted(self.modified_files),
                        ).model_dump()
                    )
                    event.metadata.update(
                        model_effective=self.model_effective, turn_interrupted=self.turn_interrupted
                    )
                yield event
                if event.event_type in ("completed", "error"):
                    break
        finally:
            if self._turn and not self._turn.done():
                await self.cancel()
                self._turn.cancel()
                # Cancellation has no protocol acknowledgement. Never reuse this session with
                # possible late notifications from the abandoned turn.
                self._closed = True
            if self._turn:
                await asyncio.gather(self._turn, return_exceptions=True)
            self.busy = False
            self.last_used = time.monotonic()
            if self._closed:
                await self.close()

    async def cancel(self) -> None:
        if self.rpc and not self.rpc.closed and self.session_id:
            try:
                await asyncio.wait_for(self.rpc.notify("session/cancel", {"sessionId": self.session_id}), 5)
            except (TimeoutError, ConnectionError, ACPProcessExited):
                pass

    async def close(self) -> None:
        self._closed = True
        await self.cancel()
        if self._turn and not self._turn.done() and self._turn is not asyncio.current_task():
            self._turn.cancel()
            await asyncio.gather(self._turn, return_exceptions=True)
        if self.rpc:
            await self.rpc.close()
        await self.handlers.close()
        if self.process:
            await stop_process(self.process)
        if self._stderr_task:
            await asyncio.gather(self._stderr_task, return_exceptions=True)
