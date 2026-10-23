from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import Input, Record


class TicketCreate(Input):
    title: str = Field(min_length=1, max_length=200)
    description: str = ""
    auto_start: bool = True


class TicketPatch(Input):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None


class TicketOut(Record):
    project_id: UUID
    workflow_id: UUID
    workflow_version: int
    number: int
    code: str
    channel_slug: str
    title: str
    description: str
    status: str
    reporter_id: UUID
    thread_id: str
    current_node_id: str | None
    result: dict[str, Any]


class TicketCreated(Input):
    ticket: TicketOut
    chat_url: str
    auto_start_pending: bool = False


class MessageOut(Record):
    ticket_id: UUID
    run_id: UUID | None
    node_id: str | None
    sender_type: str
    sender_id: UUID | None
    sender_name: str
    event_type: str
    content: str
    metadata: dict[str, Any]
    seq: int


class LogOut(Input):
    seq: int
    run_id: UUID | None
    agent: str
    kind: str
    text: str
    at: datetime


class AttachmentOut(Input):
    id: UUID
    filename: str
    mime: str
    size: int
    url: str
    thumbnail_url: str | None
