from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@pytest.mark.parametrize("claude,codex", [(True, True), (True, False), (False, True), (False, False)])
async def test_health_reports_binary_availability(claude: bool, codex: bool) -> None:
    settings = Settings(jwt_secret="test", claude_acp_bin="test-claude", codex_acp_bin="test-codex")
    binaries = {"test-claude": "claude.cmd" if claude else None, "test-codex": "codex.cmd" if codex else None}
    with patch("app.core.config.shutil.which", side_effect=lambda binary, **kwargs: binaries[binary]):
        async with AsyncClient(
            transport=ASGITransport(app=create_app(settings)), base_url="http://test"
        ) as client:
            response = await client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "acp": {"claude": claude, "codex": codex}}
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
