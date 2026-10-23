"""Isolated real backend for management browser verification; never uses local .env or DB."""
import os
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
uvicorn.run(create_app(settings), host="127.0.0.1", port=int(os.environ.get("E2E_BACKEND_PORT", "8062")))
