from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class NodeOutput(TypedDict):
    node_id: str
    agent_handle: str
    text: str
    route: str | None
    modified_files: list[str]
    at: str


class WorkflowState(TypedDict, total=False):
    ticket_id: str
    project_id: str
    workspace_path: str
    title: str
    description: str
    number: int
    outputs: Annotated[list[NodeOutput], operator.add]
    user_inputs: Annotated[list[dict[str, Any]], operator.add]
    last_route: dict[str, str]
    modified_files: list[str]
    iteration: dict[str, int]
    gate_counts: dict[str, int]
    cursors: dict[str, dict[str, Any]]
    release: dict[str, Any] | None
    approval: bool
    wrote_files: bool
    error: str | None
    node_statuses: dict[str, str]
    orchestrator_task: str
    orchestrator_summary: str
