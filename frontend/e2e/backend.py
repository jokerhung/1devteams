"""Isolated real backend for management browser verification; never uses local .env or DB."""
import os
import json
from contextlib import asynccontextmanager
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "backend"))
os.environ.setdefault("JWT_SECRET", "phase4-isolated-import-only")
from app.core.config import Settings
from app.main import create_app
import uvicorn

data = root / "frontend" / ".e2e-data"
workspace = data / "workspace"
workspace.mkdir(parents=True, exist_ok=True)
if not (workspace / ".git").exists():
    subprocess.run(["git", "init", "-b", "develop", str(workspace)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(workspace), "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "--allow-empty", "-m", "chore: initialize test workspace"], check=True, capture_output=True)
settings = Settings(
    _env_file=None,
    database_url="sqlite+aiosqlite:///" + (data / f"management-{uuid4().hex}.db").as_posix(),
    checkpoint_db=str(data / f"checkpoints-{uuid4().hex}.db"),
    checkpoint_postgres_url=None,
    jwt_secret="phase4-isolated-browser-tests-only",
    app_secret_key="phase4-isolated-browser-tests-only",
    bootstrap_admin_email="owner@example.com",
    bootstrap_admin_password="test-password-123",
    data_dir=data / "blobs",
    allowed_workspace_roots=str(data),
    cors_origins="http://127.0.0.1:3062",
)
app = create_app(settings)
if os.environ.get("ACP_FAKE_SCENARIO") == "bugfix_happy_path":
    from fake_acp import factory

    chat = data / f"chat-workspace-{uuid4().hex}"
    chat.mkdir()
    remote = data / f"chat-remote-{uuid4().hex}.git"
    def git(*args):
        subprocess.run(["git", *args], cwd=chat, check=True, capture_output=True)
    git("init", "-b", "develop")
    git("config", "user.email", "browser@example.com")
    git("config", "user.name", "Browser Test")
    (chat / "app.txt").write_text("Excel export broken\n")
    git("add", "app.txt")
    git("commit", "-m", "chore: browser fixture")
    git("init", "--bare", str(remote))
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "develop")
    (data / "runtime.json").write_text(json.dumps({"workspace": str(chat), "remote": str(remote)}))
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(instance):
        async with original(instance):
            instance.state.acp_pool.factory = factory
            yield

    app.router.lifespan_context = lifespan
uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("E2E_BACKEND_PORT", "8062")))
