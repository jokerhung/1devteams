"""Environment settings. Relative .env paths are anchored to backend/, not the shell cwd."""

import os
import shutil
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite+aiosqlite:///./aiteams.db"
    checkpoint_db: str = "./checkpoints.db"
    jwt_secret: SecretStr = Field(min_length=1)
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
