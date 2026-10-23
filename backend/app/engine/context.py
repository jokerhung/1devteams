"""Nonserializable dependencies stay in RunnableConfig, outside checkpoint state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.acp.pool import ACPProcessPool
from app.acp.types import AgentRuntimeConfig
from app.core.config import Settings
from app.core.events import EventBus
from app.db.models import Agent, Ticket, TicketMessage
from app.services.agent_service import runtime_config
from app.services.git_service import GitService


@dataclass
class RunContext:
    ticket_id: str
    project_id: str
    sessions: Any
    pool: ACPProcessPool
    events: EventBus
    settings: Settings
    git: GitService
    remote: str
    default_branch: str
    run_id: str | None = None
    node_id: str | None = None
    had_writer: bool = False

    async def agent(self, agent_id: str) -> AgentRuntimeConfig:
        async with self.sessions() as db:
            row = await db.get(Agent, agent_id)
            if row is None or not row.is_active:
                raise ValueError("Agent không còn hoạt động")
            return runtime_config(row, self.settings)

    async def emit(self, event_type: str, content: str = "", **data: Any) -> None:
        data.setdefault("run_id", self.run_id)
        data.setdefault("node_id", self.node_id)
        await self.events.publish(
            f"tickets/{self.ticket_id}", {"event_type": event_type, "content": content, **data}
        )

    async def status(
        self, status: str, node_id: str | None = None, result: dict[str, Any] | None = None
    ) -> None:
        async with self.sessions() as db:
            ticket = await db.get(Ticket, self.ticket_id)
            if ticket is None:
                raise ValueError("Ticket không tồn tại")
            ticket.status, ticket.current_node_id = status, node_id
            if result is not None:
                ticket.result = result
            await db.commit()
            workflow_id = ticket.workflow_id
        await self.emit(
            "ticket_status",
            metadata={
                "status": status,
                "current_node_id": node_id,
                "workflow_id": workflow_id,
                **({"result": result} if result is not None else {}),
            },
        )
        await self.events.publish(
            f"projects/{self.project_id}",
            {
                "event_type": "ticket_status",
                "ticket_id": self.ticket_id,
                "workflow_id": workflow_id,
                "status": status,
            },
        )

    async def gate_emitted(self, key: str) -> bool:
        async with self.sessions() as db:
            rows = (
                await db.scalars(
                    select(TicketMessage).where(
                        TicketMessage.ticket_id == self.ticket_id, TicketMessage.event_type == "gate_waiting"
                    )
                )
            ).all()
            return any(row.event_metadata.get("gate_key") == key for row in rows)

    async def chat_inputs(self) -> list[dict[str, Any]]:
        async with self.sessions() as db:
            rows = (
                await db.scalars(
                    select(TicketMessage)
                    .where(TicketMessage.ticket_id == self.ticket_id, TicketMessage.sender_type == "USER")
                    .order_by(TicketMessage.seq)
                )
            ).all()
            return [
                {
                    "node_id": "chat",
                    "kind": "message",
                    "text": row.content,
                    "user": {"id": row.sender_id, "display_name": row.sender_name},
                    "message_id": row.id,
                    "seq": row.seq,
                    **row.event_metadata,
                }
                for row in rows
            ]
