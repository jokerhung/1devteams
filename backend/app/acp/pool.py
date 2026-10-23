"""Ticket-scoped sessions with separate ACP/API capacity and restart notifications."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from pathlib import Path

from app.acp.api_session import ApiAgentSession
from app.acp.client import ACPSession, default_resolver
from app.acp.types import AgentRuntimeConfig, AgentSession
from app.acp.url_policy import URLPolicy
from app.core.config import Settings, get_settings
from app.core.events import EventBus

SessionFactory = Callable[[AgentRuntimeConfig, Path], AgentSession]


def create_session(
    cfg: AgentRuntimeConfig, workspace: Path, settings: Settings | None = None
) -> AgentSession:
    settings = settings or get_settings()
    if cfg.runtime == "openai-api":
        return ApiAgentSession(
            cfg,
            workspace,
            timeout=settings.acp_prompt_timeout_sec,
            context_chars=settings.api_max_context_chars,
            policy=URLPolicy(
                set(settings.api_allowed_http_hosts.split(",")),
                set(settings.api_allowed_private_hosts.split(",")),
            ),
        )
    return ACPSession(
        cfg,
        workspace,
        bin_resolver=lambda runtime: default_resolver(runtime, settings),
        timeout=settings.acp_prompt_timeout_sec,
    )


class ACPProcessPool:
    def __init__(
        self,
        *,
        factory: SessionFactory = create_session,
        event_bus: EventBus | None = None,
        max_acp: int | None = None,
        max_api: int | None = None,
        idle_timeout: float = 1800,
    ) -> None:
        settings = get_settings()
        self.max_acp = max_acp if max_acp is not None else settings.max_acp_processes
        self.max_api = max_api if max_api is not None else settings.max_api_concurrency
        if min(self.max_acp, self.max_api) < 1 or idle_timeout <= 0:
            raise ValueError("Pool limits and idle timeout must be positive")
        self.factory, self.events = factory, event_bus or EventBus()
        self.idle_timeout = idle_timeout
        self.sessions: dict[tuple[str, str], AgentSession] = {}
        self._starting: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._condition = asyncio.Condition()
        self._closed = False
        self._reaper: asyncio.Task[None] | None = None

    async def get_or_start(self, cfg: AgentRuntimeConfig, workspace: Path, ticket_id: str) -> AgentSession:
        workspace = await asyncio.to_thread(workspace.resolve)
        key = (ticket_id, cfg.agent_id)
        async with self._condition:
            if not self._reaper:
                self._reaper = asyncio.create_task(self._reap())
            while True:
                if self._closed:
                    raise RuntimeError("Session pool is closed")
                previous = self.sessions.get(key)
                if previous:
                    if previous.config_version > cfg.config_version:
                        raise ValueError("Stale agent config version")
                    if key in self._starting and previous.config_version == cfg.config_version:
                        if previous.workspace != workspace:
                            raise ValueError("Ticket session workspace cannot change")
                        startup = self._starting[key]
                        session = previous
                        break
                    if previous.alive and previous.config_version == cfg.config_version:
                        if previous.workspace != workspace:
                            raise ValueError("Ticket session workspace cannot change")
                        previous.last_used = time.monotonic()
                        return previous
                    await self._remove(key, restart_version=cfg.config_version)
                api = cfg.runtime == "openai-api"
                count = sum(
                    (session.cfg.runtime == "openai-api") == api for session in self.sessions.values()
                )
                if count < (self.max_api if api else self.max_acp):
                    session = self.factory(cfg, workspace)
                    self.sessions[key] = session
                    startup = asyncio.create_task(session.start())
                    self._starting[key] = startup
                    break
                await self._condition.wait()
        # Startup can involve slow CLI handshakes or DNS. Reserve capacity above, but
        # let unrelated tickets start and shutdown/restart cancel a pending handshake.
        try:
            await asyncio.shield(startup)
        except BaseException:
            async with self._condition:
                if self.sessions.get(key) is session:
                    await self._remove(key)
            raise
        async with self._condition:
            if self._closed or self.sessions.get(key) is not session:
                raise RuntimeError("Session was closed during startup")
            self._starting.pop(key, None)
            return session

    async def _remove(self, key: tuple[str, str], restart_version: int | None = None) -> None:
        session = self.sessions.pop(key)
        if startup := self._starting.pop(key, None):
            startup.cancel()
            await asyncio.gather(startup, return_exceptions=True)
        if session.busy:
            session.turn_interrupted = True
            await session.cancel()
        await session.close()
        if restart_version is not None:
            event = {
                "event_type": "agent_restarted",
                "agent_id": key[1],
                "config_version": restart_version,
                "ticket_id": key[0],
                "content": f"↻ {session.cfg.handle} khởi động lại với cấu hình mới",
            }
            await self.events.publish("users", event)
            await self.events.publish(f"tickets/{key[0]}", event)
        self._condition.notify_all()

    async def restart_agent(self, agent_id: str, config_version: int | None = None) -> None:
        async with self._condition:
            for key in list(self.sessions):
                if key[1] == agent_id:
                    version = (
                        config_version
                        if config_version is not None
                        else self.sessions[key].config_version + 1
                    )
                    await self._remove(key, restart_version=version)

    async def close_ticket(self, ticket_id: str) -> None:
        async with self._condition:
            for key in list(self.sessions):
                if key[0] == ticket_id:
                    await self._remove(key)

    async def discard_session(self, ticket_id: str, agent_id: str) -> None:
        async with self._condition:
            key = (ticket_id, agent_id)
            if key in self.sessions:
                await self._remove(key)

    async def _reap(self) -> None:
        while True:
            await asyncio.sleep(min(60, self.idle_timeout / 2))
            async with self._condition:
                for key, session in list(self.sessions.items()):
                    if (
                        key not in self._starting
                        and not session.busy
                        and time.monotonic() - session.last_used >= self.idle_timeout
                    ):
                        await self._remove(key)

    async def close_all(self) -> None:
        async with self._condition:
            self._closed = True
            for key in list(self.sessions):
                await self._remove(key)
            self._condition.notify_all()
        if self._reaper:
            self._reaper.cancel()
            await asyncio.gather(self._reaper, return_exceptions=True)
