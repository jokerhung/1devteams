"""Ticket-independent tool execution using the same verified browser loop as workflows."""

import base64
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.acp.client import ACPSession
from app.acp.security import scrub, scrub_data
from app.acp.types import AgentRuntimeConfig, AgentSession
from app.core.config import Settings
from app.db.models import Agent
from app.engine.browser import browser_turn
from app.services.agent_service import runtime_config
from app.services.browser_worker import BrowserWorkerManager


@dataclass
class ChatContext:
    settings: Settings
    sessions: Any
    browser_manager: BrowserWorkerManager | None
    completion_metadata: dict[str, Any] | None = None
    progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None

    async def agent(self, agent_id: str) -> AgentRuntimeConfig:
        async with self.sessions() as db:
            row = await db.get(Agent, agent_id)
            if row is None or not row.is_active:
                raise ValueError("Agent không còn hoạt động")
            return runtime_config(row, self.settings)

    async def emit(self, event_type: str, content: str = "", **data: Any) -> None:
        if self.progress and event_type == "tool_call_update":
            metadata = data.get("metadata", {})
            await self.progress(
                {
                    "id": metadata.get("tool_call_id", "browser"),
                    "title": content,
                    "status": metadata.get("status", "in_progress"),
                }
            )


async def respond(
    session: AgentSession, prompt: str, context: ChatContext
) -> tuple[str, list[dict[str, Any]]]:
    reports: list[dict[str, Any]] = []

    async def stream(text: str, images: list[dict[str, Any]] | None) -> tuple[str, list[str]]:
        if context.progress:
            await context.progress(
                {"id": "response", "title": "Agent đang xử lý và soạn phản hồi…", "status": "in_progress"}
            )
        chunks: list[str] = []
        size = 0
        events = (
            session.prompt(text, images=images)
            if images and isinstance(session, ACPSession)
            else session.prompt(text)
        )
        async for event in events:
            if context.progress and event.event_type in {"tool_call", "tool_call_update"}:
                kind = event.metadata.get("kind", "tool")
                if kind not in {"read", "edit", "delete", "move", "search", "execute", "fetch", "think"}:
                    kind = "tool"
                await context.progress(
                    {
                        "id": str(event.metadata.get("tool_call_id", "runtime-tool")),
                        "title": f"Công cụ: {kind}",
                        "status": event.metadata.get("status", "in_progress"),
                    }
                )
            if event.event_type == "error":
                raise RuntimeError("Agent runtime failed")
            if event.event_type == "message_chunk":
                size += len(event.content)
                if size > 200000:
                    raise RuntimeError("Agent reply too large")
                chunks.append(event.content)
        return "".join(chunks), []

    async def report_sink(report: dict[str, Any], screenshot: bytes | None) -> None:
        clean = scrub_data(report, session.cfg)
        if screenshot:
            clean["screenshot"] = "data:image/png;base64," + base64.b64encode(screenshot).decode()
        reports.append(clean)

    if session.cfg.permission_profile.allow_browser:
        text, _ = await browser_turn(context, session, prompt, "", "", None, stream, report_sink)
    else:
        text, _ = await stream(prompt, None)
    return scrub(text, session.cfg).strip(), reports
