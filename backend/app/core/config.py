"""Environment settings. Relative .env paths are anchored to backend/, not the shell cwd."""

import os
import shutil
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite+aiosqlite:///./aiteams.db"
    checkpoint_db: str = "./checkpoints.db"
    checkpoint_postgres_url: SecretStr | None = None
    max_node_iterations: int = Field(default=5, gt=0)
    api_context_diff_chars: int = Field(default=40000, gt=0)
    jwt_secret: SecretStr = Field(min_length=1)
    jwt_expire_minutes: int = Field(default=480, gt=0)
    app_secret_key: SecretStr | None = None
    bootstrap_admin_email: str | None = None
    bootstrap_admin_password: SecretStr | None = None
    data_dir: Path = BACKEND_ROOT / "data"
    attach_max_files: int = Field(default=5, gt=0)
    attach_max_mb: int = Field(default=10, gt=0)
    attach_allow_scripts: bool = False
    attach_quota_mb: int = Field(default=200, gt=0)
    enable_remote_terminal: bool = False
    trusted_native_acp: bool = False
    acp_inherit_provider_env: bool = True
    terminal_idle_seconds: int = Field(default=600, ge=1)
    terminal_audit_input: bool = False
    max_terminal_sessions: int = Field(default=8, gt=0)
    max_concurrent_tickets: int = Field(default=4, gt=0)
    browser_max_sessions: int = Field(default=4, ge=1, le=16)
    browser_max_actions: int = Field(default=100, ge=1, le=500)
    browser_max_rounds: int = Field(default=30, ge=1, le=100)
    browser_action_timeout_ms: int = Field(default=15000, ge=1000, le=60000)
    browser_run_timeout_sec: int = Field(default=900, ge=30, le=3600)
    max_event_chars: int = Field(default=100000, ge=1024)
    overload_patterns: str = "capacity,overloaded,429,529,rate limit"
    model_retry_delays: str = "30,60"
    claude_acp_bin: str = "claude-agent-acp"
    codex_acp_bin: str = "codex-acp"
    allowed_workspace_roots: str = r"D:\VETC"
    acp_prompt_timeout_sec: int = Field(default=1800, gt=0)
    max_acp_processes: int = Field(default=6, gt=0)
    max_api_concurrency: int = Field(default=8, gt=0)
    api_max_context_chars: int = Field(default=100_000, gt=0)
    api_allowed_http_hosts: str = "localhost,127.0.0.1"
    api_allowed_private_hosts: str = ""
    cors_origins: str = "http://localhost:3060"

    @field_validator("model_retry_delays")
    @classmethod
    def retry_delays(cls, value: str) -> str:
        import math

        delays = [float(part.strip()) for part in value.split(",")]
        if len(delays) > 2 or any(not math.isfinite(delay) or delay < 0 for delay in delays):
            raise ValueError("Use at most two finite, nonnegative retry delays")
        return value

    @property
    def workspace_roots(self) -> list[Path]:
        return [
            Path(root.strip()).resolve() for root in self.allowed_workspace_roots.split(";") if root.strip()
        ]

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


def resolve_binary(binary: str) -> str | None:
    # Prefer the pinned, repo-local adapters, while supporting a configured absolute path/global install.
    search_path = os.pathsep.join([str(REPO_ROOT / "node_modules" / ".bin"), os.environ.get("PATH", "")])
    return shutil.which(binary, path=search_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()
