from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import Field, field_validator

from app.schemas.common import Input, Name, Record

Prefix = str


class Node(Input):
    id: str = Field(min_length=1, max_length=100)
    type: Literal["start", "end", "agent", "condition", "human_input", "human_confirm", "git_release"]
    position: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0})
    data: dict[str, Any] = Field(default_factory=dict)


class Edge(Input):
    id: str = Field(min_length=1, max_length=100)
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None


class OrchestratorConfig(Input):
    coordinator_agent_id: UUID
    instructions: str = Field(min_length=1, max_length=20000)
    max_rounds: int = Field(default=20, ge=1, le=40)

    @field_validator("instructions")
    @classmethod
    def nonempty_instructions(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Nhập instruction cho Orchestrator")
        return value.strip()


class Graph(Input):
    nodes: list[Node] = Field(default_factory=list, max_length=300)
    edges: list[Edge] = Field(default_factory=list, max_length=1500)
    viewport: dict[str, float] = Field(default_factory=lambda: {"x": 0.0, "y": 0.0, "zoom": 1.0})
    orchestrator: OrchestratorConfig | None = None


class WorkflowCreate(Input):
    name: Name
    ticket_prefix: str = Field(pattern=r"^[A-Z]{2,10}$")
    description: str = ""
    template: Literal["blank", "bugfix_default", "bugfix_with_security_review", "add_feature"] = "blank"
    icon: str = Field(default="🐛", max_length=8)
    color: str = Field(default="sky", max_length=20)
    orchestrator: OrchestratorConfig | None = None


class WorkflowPatch(Input):
    name: Name | None = None
    ticket_prefix: str | None = Field(default=None, pattern=r"^[A-Z]{2,10}$")
    description: str | None = None
    icon: str | None = Field(default=None, max_length=8)
    color: str | None = Field(default=None, max_length=20)
    position: int | None = Field(default=None, ge=0)


class WorkflowDuplicate(Input):
    name: Name
    ticket_prefix: str = Field(pattern=r"^[A-Z]{2,10}$")


class WorkflowOut(Record):
    project_id: UUID
    name: str
    description: str
    ticket_prefix: str
    icon: str
    color: str
    status: str
    current_version: int
    published_version: int | None
    graph: Graph
    is_valid: bool
    validation_errors: list[str]
    position: int
    ticket_counts: dict[str, int] = Field(default_factory=dict)


class ValidationOut(Input):
    is_valid: bool
    errors: list[str]
    current_version: int | None = None


class WorkflowVersionOut(Record):
    workflow_id: UUID
    version: int
    graph: Graph
    published_by: UUID
    published_at: datetime
