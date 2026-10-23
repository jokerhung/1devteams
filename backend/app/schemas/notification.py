from datetime import datetime
from uuid import UUID

from app.schemas.common import Input, Record


class EntityReference(Input):
    id: UUID
    name: str


class TicketReference(Input):
    id: UUID
    code: str
    title: str


class NotificationOut(Record):
    user_id: UUID
    project_id: UUID
    workflow_id: UUID
    ticket_id: UUID
    type: str
    title: str
    body: str
    gate_key: str
    is_read: bool
    resolved_at: datetime | None
    outcome: str | None
    project: EntityReference
    workflow: EntityReference
    ticket: TicketReference
