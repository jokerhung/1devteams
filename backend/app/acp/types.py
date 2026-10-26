"""Shared runtime contracts; secrets never participate in repr or serialized events."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

RuntimeType = Literal["claude-code", "codex", "openai-api"]
Json = dict[str, Any]
ACPEventType = Literal[
    "message_chunk",
    "thought_chunk",
    "tool_call",
    "tool_call_update",
    "file_edit",
    "terminal_output",
    "permission",
    "plan",
    "completed",
    "error",
    "log",
]


class PermissionProfile(BaseModel):
    allow_read: bool = True
    allow_write: bool = False
    allow_terminal: bool = False
    allow_fetch: bool = False
    allow_browser: bool = False
    allowed_commands: list[str] = Field(default_factory=list)
    blocked_commands: list[str] = Field(
        default_factory=lambda: [
            "git commit",
            "git push",
            "git reset --hard",
            "rm -rf",
        ]
    )
    can_git_release: bool = False


class APIParams(BaseModel):
    model_config = ConfigDict(extra="forbid")
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    reasoning_format: Literal["reasoning_effort", "reasoning"] | None = None
    extra_headers: dict[str, SecretStr] = Field(default_factory=dict, repr=False, exclude=True)


class AgentRuntimeConfig(BaseModel):
    agent_id: str
    handle: str
    runtime: RuntimeType
    model: str | None = None
    reasoning_effort: str | None = None
    fallback_model: str | None = None
    fallback_runtime: RuntimeType | None = None
    fallback_agent_id: str | None = None
    system_prompt: str = ""
    permission_profile: PermissionProfile = Field(default_factory=PermissionProfile)
    env: dict[str, str] = Field(default_factory=dict, repr=False, exclude=True)
    config_version: int = Field(default=1, ge=1)
    base_url: str | None = None
    api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    api_params: APIParams = Field(default_factory=APIParams)

    @model_validator(mode="after")
    def validate_api(self) -> AgentRuntimeConfig:
        if self.runtime == "openai-api":
            if not self.base_url or not self.model or not self.api_key:
                raise ValueError("API runtime requires base_url, model and api_key")
            p = self.permission_profile
            if p.allow_write or p.allow_terminal or p.can_git_release:
                raise ValueError(
                    "API runtime is text-only and cannot have write/terminal/release permissions"
                )
        return self


class ACPStreamEvent(BaseModel):
    agent_handle: str
    event_type: ACPEventType
    content: str = ""
    metadata: Json = Field(default_factory=dict)


class PromptResult(BaseModel):
    stop_reason: str
    full_text: str
    modified_files: list[str] = Field(default_factory=list)


class AgentSession(Protocol):
    cfg: AgentRuntimeConfig
    workspace: Path
    config_version: int
    modified_files: set[str]
    turn_interrupted: bool
    busy: bool
    last_used: float

    @property
    def alive(self) -> bool: ...
    async def start(self) -> None: ...
    def prompt(self, text: str) -> AsyncIterator[ACPStreamEvent]: ...
    async def cancel(self) -> None: ...
    async def close(self) -> None: ...
