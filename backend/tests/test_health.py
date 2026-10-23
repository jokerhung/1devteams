from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.parametrize("claude,codex", [(True, True), (True, False), (False, True), (False, False)])
async def test_health_reports_binary_availability(claude: bool, codex: bool) -> None:
    settings = Settings(
        jwt_secret="test",
        claude_acp_bin="test-claude",
        codex_acp_bin="test-codex",
        cors_origins="http://localhost:3060",
    )
    binaries = {"test-claude": "claude.cmd" if claude else None, "test-codex": "codex.cmd" if codex else None}
    with patch("app.core.config.shutil.which", side_effect=lambda binary, **kwargs: binaries[binary]):
        async with AsyncClient(
            transport=ASGITransport(app=create_app(settings)), base_url="http://test"
        ) as client:
            response = await client.get("/api/health", headers={"Origin": "http://localhost:3060"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "acp": {"claude": claude, "codex": codex}}
    assert response.headers["access-control-allow-origin"] == "http://localhost:3060"


async def test_lifespan_owns_pool_and_closes_on_shutdown(tmp_path):
    app = create_app(
        Settings(
            jwt_secret="test",
            max_acp_processes=2,
            max_api_concurrency=3,
            database_url=f"sqlite+aiosqlite:///{tmp_path / 'health.db'}",
            checkpoint_db=str(tmp_path / "checkpoints.db"),
            data_dir=tmp_path / "data",
        )
    )
    async with app.router.lifespan_context(app):
        pool = app.state.acp_pool
        assert pool.events is app.state.event_bus
        assert pool.max_acp == 2 and pool.max_api == 3
    assert pool._closed
