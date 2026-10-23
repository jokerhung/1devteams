from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Entity, Timestamps, now


class User(Entity, Base):
    __tablename__ = "users"
    email: Mapped[str] = mapped_column(String(255), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    system_role: Mapped[str] = mapped_column(String(20), default="MEMBER")
    avatar_initials: Mapped[str] = mapped_column(String(4))


class Agent(Entity, Base):
    __tablename__ = "agents"
    handle: Mapped[str] = mapped_column(String(50), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    role_key: Mapped[str] = mapped_column(String(50), default="CUSTOM")
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    runtime: Mapped[str] = mapped_column(String(20))
    base_url: Mapped[str | None] = mapped_column(String(300))
    api_key_enc: Mapped[str | None] = mapped_column(Text)
    api_key_last4: Mapped[str | None] = mapped_column(String(4))
    api_params: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    model: Mapped[str | None] = mapped_column(String(100))
    fallback_model: Mapped[str | None] = mapped_column(String(100))
    permission_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    icon: Mapped[str] = mapped_column(String(8), default="🤖")
    logo_url: Mapped[str | None] = mapped_column(String(300))
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    restarted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    color: Mapped[str] = mapped_column(String(20), default="stone")
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Team(Entity, Base):
    __tablename__ = "teams"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(8), default="🤖")
    logo_url: Mapped[str | None] = mapped_column(String(300))


class TeamAgent(Timestamps, Base):
    __tablename__ = "team_agents"
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True)
    agent_id: Mapped[str] = mapped_column(ForeignKey("agents.id", ondelete="RESTRICT"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer)


class Project(Entity, Base):
    __tablename__ = "projects"
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    workspace_path: Mapped[str] = mapped_column(String(500))
    default_branch: Mapped[str] = mapped_column(String(200))
    git_remote: Mapped[str] = mapped_column(String(100), default="origin")
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    next_ticket_number: Mapped[int] = mapped_column(Integer, default=1)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProjectMember(Entity, Base):
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("project_id", "member_type", "member_id"),)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    member_type: Mapped[str] = mapped_column(String(10))
    member_id: Mapped[str] = mapped_column(Uuid(as_uuid=False))
    project_role: Mapped[str | None] = mapped_column(String(20))


class Workflow(Entity, Base):
    __tablename__ = "workflows"
    __table_args__ = (UniqueConstraint("project_id", "name"), UniqueConstraint("project_id", "ticket_prefix"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(Text, default="")
    ticket_prefix: Mapped[str] = mapped_column(String(10))
    icon: Mapped[str] = mapped_column(String(8), default="🐛")
    color: Mapped[str] = mapped_column(String(20), default="sky")
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    current_version: Mapped[int] = mapped_column(Integer, default=1)
    published_version: Mapped[int | None] = mapped_column(Integer)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    validation_errors: Mapped[list[str]] = mapped_column(JSON, default=list)
    position: Mapped[int] = mapped_column(Integer, default=0)


class WorkflowVersion(Entity, Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (UniqueConstraint("workflow_id", "version"),)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    graph: Mapped[dict[str, Any]] = mapped_column(JSON)
    published_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Ticket(Entity, Base):
    __tablename__ = "tickets"
    __table_args__ = (
        UniqueConstraint("project_id", "number"),
        UniqueConstraint("project_id", "channel_slug"),
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="RESTRICT"), index=True)
    workflow_version: Mapped[int] = mapped_column(Integer)
    number: Mapped[int] = mapped_column(Integer)
    channel_slug: Mapped[str] = mapped_column(String(80))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="OPEN")
    reporter_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    thread_id: Mapped[str] = mapped_column(String(100))
    current_node_id: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    next_message_seq: Mapped[int] = mapped_column(BigInteger, default=1)


class TicketMessage(Entity, Base):
    __tablename__ = "ticket_messages"
    __table_args__ = (
        UniqueConstraint("ticket_id", "seq"),
        Index("ix_message_ticket_seq", "ticket_id", "seq"),
    )
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    run_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    node_id: Mapped[str | None] = mapped_column(String(100))
    sender_type: Mapped[str] = mapped_column(String(10))
    sender_id: Mapped[str | None] = mapped_column(Uuid(as_uuid=False))
    sender_name: Mapped[str] = mapped_column(String(100))
    event_type: Mapped[str] = mapped_column(String(30))
    content: Mapped[str] = mapped_column(Text, default="")
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    seq: Mapped[int] = mapped_column(BigInteger)


class Attachment(Entity, Base):
    __tablename__ = "attachments"
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("ticket_messages.id", ondelete="SET NULL"))
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    filename: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    size: Mapped[int] = mapped_column(BigInteger)
    storage_path: Mapped[str] = mapped_column(String(500))
    thumbnail_path: Mapped[str | None] = mapped_column(String(500))


class Notification(Entity, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "gate_key"),
        Index("ix_notification_inbox", "user_id", "resolved_at", "created_at"),
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id", ondelete="CASCADE"))
    ticket_id: Mapped[str] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(10))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500), default="")
    gate_key: Mapped[str] = mapped_column(String(100))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str | None] = mapped_column(String(20))


class UserPreference(Timestamps, Base):
    __tablename__ = "user_preferences"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
