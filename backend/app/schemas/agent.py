from datetime import datetime
from typing import Literal

from pydantic import Field, SecretStr, field_validator

from app.acp.types import PermissionProfile, RuntimeType
from app.schemas.common import Input, Name, Record

Profile = PermissionProfile | Literal["read_only", "developer", "tester", "leader", "custom"]


class APIParameters(Input):
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    reasoning_format: Literal["reasoning_effort", "reasoning"] | None = None
    extra_headers: dict[str, SecretStr] = Field(default_factory=dict, repr=False)


class AgentCreate(Input):
    handle: str = Field(pattern=r"^@[a-z0-9_\-]{2,49}$", max_length=50)
    display_name: Name
    role_key: str = Field(default="CUSTOM", min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_]+$")
    description: str | None = None
    system_prompt: str = ""
    runtime: RuntimeType = "claude-code"
    base_url: str | None = Field(default=None, max_length=300)
    api_key: SecretStr | None = Field(default=None, repr=False)
    api_params: APIParameters = Field(default_factory=APIParameters)
    model: str | None = Field(default=None, max_length=100)
    reasoning_effort: str | None = Field(default=None, max_length=100)
    fallback_model: str | None = Field(default=None, max_length=100)
    fallback_runtime: RuntimeType | None = None
    fallback_agent_id: str | None = Field(default=None, pattern=r"^[0-9a-fA-F-]{36}$")
    permission_profile: Profile = "read_only"
    icon: str = Field(default="🤖", max_length=8)
    logo_url: str | None = Field(default=None, max_length=300, pattern=r"^/api/assets/logos/[a-f0-9-]+\.png$")
    color: str = Field(default="stone", max_length=20)
    is_active: bool = True

    @field_validator("handle", mode="before")
    @classmethod
    def lower_handle(cls, value: str) -> str:
        return value.lower() if isinstance(value, str) else value


class AgentPatch(Input):
    display_name: Name | None = None
    role_key: str | None = Field(default=None, min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_]+$")
    description: str | None = None
    system_prompt: str | None = None
    runtime: RuntimeType | None = None
    base_url: str | None = Field(default=None, max_length=300)
    api_key: SecretStr | None = Field(default=None, repr=False)
    api_params: APIParameters | None = None
    model: str | None = Field(default=None, max_length=100)
    reasoning_effort: str | None = Field(default=None, max_length=100)
    fallback_model: str | None = Field(default=None, max_length=100)
    fallback_runtime: RuntimeType | None = None
    fallback_agent_id: str | None = Field(default=None, pattern=r"^[0-9a-fA-F-]{36}$")
    permission_profile: Profile | None = None
    icon: str | None = Field(default=None, max_length=8)
    logo_url: str | None = Field(default=None, max_length=300, pattern=r"^/api/assets/logos/[a-f0-9-]+\.png$")
    color: str | None = Field(default=None, max_length=20)
    is_active: bool | None = None


class AgentOut(Record):
    handle: str
    display_name: str
    role_key: str
    description: str | None
    system_prompt: str
    runtime: RuntimeType
    base_url: str | None
    has_key: bool
    api_key_last4: str | None
    api_params: dict
    model: str | None
    reasoning_effort: str | None = None
    fallback_model: str | None
    fallback_runtime: RuntimeType | None = None
    fallback_agent_id: str | None = None
    permission_profile: PermissionProfile
    icon: str
    logo_url: str | None
    color: str
    is_builtin: bool
    is_active: bool
    config_version: int
    restarted_at: datetime | None


class AgentEditOut(Input):
    agent: AgentOut
    restart: bool


class AgentDuplicate(Input):
    handle: str = Field(pattern=r"^@[a-z0-9_\-]{2,49}$")
    display_name: Name | None = None


class ConnectionDraft(Input):
    base_url: str = Field(max_length=300)
    api_key: SecretStr
    model: str = Field(min_length=1, max_length=100)
    extra_headers: dict[str, SecretStr] = Field(default_factory=dict, repr=False)


class NativeOptionsDraft(Input):
    runtime: Literal["claude-code", "codex"]
    model: str | None = Field(default=None, max_length=100)
    reasoning_effort: str | None = Field(default=None, max_length=100)


class APIOptionsDraft(Input):
    base_url: str = Field(max_length=300)
    api_key: SecretStr | None = Field(default=None, repr=False)
    agent_id: str | None = Field(default=None, pattern=r"^[0-9a-fA-F-]{36}$")


class ConnectionOut(Input):
    ok: bool
    status: int | None = None
    latency_ms: int
    models: list[dict] = Field(default_factory=list)
    runtime_version: str | None = None
    error: str | None = None
