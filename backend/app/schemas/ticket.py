from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field, model_validator

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


class HistoryOut(Input):
    groups: list[dict[str, Any]]
    before_seq: int | None
    has_more: bool
    last_seq: int


class LogOut(Input):
    seq: int
    run_id: UUID | None
    agent: str
    kind: str
    text: str
    at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class AttachmentOut(Input):
    id: UUID
    filename: str
    mime: str
    size: int
    url: str
    thumbnail_url: str | None


class Reply(Input):
    text: str = Field(min_length=1, max_length=100000)
    client_msg_id: UUID | None = None
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)


class Confirm(Input):
    approved: bool = Field(strict=True)
    feedback: str | None = Field(default=None, max_length=100000)


class ChatMessage(Input):
    client_msg_id: UUID | None = None
    text: str = Field(default="", max_length=100000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def nonempty(self):
        if not self.text.strip() and not self.attachment_ids:
            raise ValueError("Tin nhắn cần nội dung hoặc tệp đính kèm")
        return self
