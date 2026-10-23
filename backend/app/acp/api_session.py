"""Text-only OpenAI-compatible Chat Completions streaming session."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx

from app.acp.security import scrub_data
from app.acp.types import ACPStreamEvent, AgentRuntimeConfig, Json, PromptResult
from app.acp.url_policy import PinnedTransport, URLPolicy, URLPolicyError, completion_url
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ApiAgentSession:
    def __init__(
        self,
        cfg: AgentRuntimeConfig,
        workspace: Path,
        *,
        timeout: float | None = None,
        policy: URLPolicy | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        context_chars: int | None = None,
    ) -> None:
        self.cfg = cfg.model_copy(deep=True)
        self.workspace = workspace.resolve()
        self.config_version = cfg.config_version
        settings = get_settings()
        self.timeout = timeout if timeout is not None else settings.acp_prompt_timeout_sec
        self.context_chars = context_chars if context_chars is not None else settings.api_max_context_chars
        self.policy = policy or URLPolicy(
            set(settings.api_allowed_http_hosts.split(",")),
            set(settings.api_allowed_private_hosts.split(",")),
        )
        self.transport = transport
        self.modified_files: set[str] = set()
        self.turn_interrupted = False
        self.busy = False
        self.last_used = time.monotonic()
        self.history: list[Json] = []
        self._client: httpx.AsyncClient | None = None
        self._turn: asyncio.Task[None] | None = None
        self._closed = False
        self._queue: asyncio.Queue[ACPStreamEvent] = asyncio.Queue()

    @property
    def alive(self) -> bool:
        return not self._closed and self._client is not None

    async def start(self) -> None:
        if self._closed:
            raise RuntimeError("API session is closed")
        if self._client:
            return
        assert self.cfg.base_url
        # Validate before constructing the client; agent services can reuse this policy when saving.
        await self.policy.validate(self.cfg.base_url)
        self._client = httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=False,
            trust_env=False,
            transport=self.transport or PinnedTransport(self.cfg.base_url, self.policy),
        )

    def _messages(self, text: str) -> list[Json]:
        system = {"role": "system", "content": self.cfg.system_prompt}
        budget = self.context_chars - len(self.cfg.system_prompt) - len(text)
        if budget < 0:
            raise ValueError("System and user messages exceed API context budget")
        history = list(self.history)
        while sum(len(item["content"]) for item in history) > budget:
            del history[:2]  # Preserve complete user/assistant turns.
        return [system, *history, {"role": "user", "content": text}]

    async def _event(self, kind: str, content: str = "", **metadata: object) -> None:
        event = ACPStreamEvent(
            agent_handle=self.cfg.handle, event_type=kind, content=content, metadata=metadata
        )
        await self._queue.put(ACPStreamEvent.model_validate(scrub_data(event.model_dump(), self.cfg)))

    async def _run(self, text: str) -> None:
        assert self._client and self.cfg.base_url and self.cfg.api_key
        result = ""
        try:
            messages = self._messages(text)
            url = completion_url(self.cfg.base_url)
            await self.policy.validate(url)
            headers = {"Authorization": f"Bearer {self.cfg.api_key.get_secret_value()}"}
            for key, value in self.cfg.api_params.extra_headers.items():
                if key.lower() in {"host", "content-length", "transfer-encoding", "connection"}:
                    raise URLPolicyError("Unsafe API header override")
                headers[key] = value.get_secret_value()
            params = self.cfg.api_params.model_dump(exclude_none=True)
            await self._event(
                "log", f"→ POST {httpx.URL(url).host}/chat/completions ({self.cfg.model}, stream)"
            )
            finish: str | None = None
            async with asyncio.timeout(self.timeout):
                async with self._client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json={
                        **params,
                        "model": self.cfg.model,
                        "messages": messages,
                        "stream": True,
                        "stream_options": {"include_usage": True},
                    },
                ) as response:
                    if response.status_code >= 300:
                        labels = {
                            401: "API key sai hoặc không có quyền",
                            403: "API key sai hoặc không có quyền",
                            404: "Model/URL không tồn tại",
                            429: "API rate limit",
                        }
                        label = labels.get(response.status_code, "API server error")
                        # Error bodies can reflect credentials; do not retain/log them at all.
                        await self._event(
                            "error",
                            label,
                            status_code=response.status_code,
                            retryable=response.status_code == 429 or response.status_code >= 500,
                            retry_after=response.headers.get("retry-after"),
                        )
                        return
                    data_lines: list[str] = []
                    size = 0
                    async for line in response.aiter_lines():
                        if line.startswith("data:"):
                            piece = line[5:].lstrip(" ")
                            size += len(piece)
                            if size > 1024 * 1024:
                                raise ValueError("SSE frame exceeds limit")
                            data_lines.append(piece)
                            continue
                        if line or not data_lines:
                            continue
                        data = "\n".join(data_lines)
                        data_lines, size = [], 0
                        if data == "[DONE]":
                            break
                        chunk = json.loads(data)
                        if "error" in chunk:
                            raise ValueError("API stream returned an error")
                        if usage := chunk.get("usage"):
                            await self._event(
                                "log",
                                f"tokens: prompt {usage.get('prompt_tokens', 0)} "
                                f"completion {usage.get('completion_tokens', 0)}",
                                usage=usage,
                            )
                        for choice in chunk.get("choices", []):
                            if choice.get("index", 0) != 0:
                                continue
                            delta = choice.get("delta", {})
                            if delta.get("tool_calls") or delta.get("function_call"):
                                raise ValueError("Text-only API runtime received tool calls")
                            if content := delta.get("content"):
                                result += content
                                await self._event("message_chunk", content)
                            if thought := delta.get("reasoning_content"):
                                await self._event("thought_chunk", thought)
                            if choice.get("finish_reason"):
                                finish = choice["finish_reason"]
            if finish is None:
                raise ValueError("API stream ended without finish_reason")
            self.history = [*messages[1:], {"role": "assistant", "content": result}]
            while sum(len(item["content"]) for item in self.history) > max(
                0, self.context_chars - len(self.cfg.system_prompt)
            ):
                del self.history[:2]
            await self._event(
                "log",
                f"✔ finish_reason={finish}" + (" · bị cắt do max_tokens" if finish == "length" else ""),
                warning=finish == "length",
            )
            await self._event(
                "completed",
                **PromptResult(stop_reason=finish, full_text=result).model_dump(),
                model_effective=self.cfg.model,
                turn_interrupted=self.turn_interrupted,
            )
        except asyncio.CancelledError:
            await self._event(
                "completed",
                stop_reason="cancelled",
                full_text=result,
                modified_files=[],
                turn_interrupted=self.turn_interrupted,
            )
        except (TimeoutError, httpx.TimeoutException):
            await self._event("error", "API request timed out", retryable=True)
        except Exception as error:
            # Exception strings can contain URLs/query credentials. Emit only a static class label.
            logger.warning("API session failed agent=%s error_type=%s", self.cfg.handle, type(error).__name__)
            await self._event("error", "API request failed", error_type=type(error).__name__)

    async def prompt(self, text: str) -> AsyncIterator[ACPStreamEvent]:
        if self.busy:
            raise RuntimeError("Concurrent API prompts are not supported")
        if not self.alive:
            raise RuntimeError("API session is not alive")
        self.busy = True
        self.turn_interrupted = False
        self._queue = asyncio.Queue()
        self._turn = asyncio.create_task(self._run(text))
        try:
            while True:
                event = await self._queue.get()
                yield event
                if event.event_type in ("error", "completed"):
                    break
        finally:
            await self.cancel()
            self.busy = False
            self.last_used = time.monotonic()

    async def cancel(self) -> None:
        if self._turn and not self._turn.done():
            self._turn.cancel()
        if self._turn:
            await asyncio.gather(self._turn, return_exceptions=True)

    async def close(self) -> None:
        self._closed = True
        await self.cancel()
        if self._client:
            await self._client.aclose()
        self.history.clear()
