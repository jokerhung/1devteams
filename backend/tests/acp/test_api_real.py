import os

import pytest
from dotenv import dotenv_values

from app.acp.api_session import ApiAgentSession
from app.acp.types import AgentRuntimeConfig
from app.core.config import BACKEND_ROOT

pytestmark = pytest.mark.real_api


async def test_live_api(tmp_path):
    env = dotenv_values(BACKEND_ROOT / ".env") | os.environ
    names = ["AITEAMS_REAL_API_BASE_URL", "AITEAMS_REAL_API_MODEL", "AITEAMS_REAL_API_KEY"]
    if not all(env.get(name) for name in names):
        pytest.skip("Configure the three AITEAMS_REAL_API_* values in backend/.env")
    cfg = AgentRuntimeConfig(
        agent_id="real-api",
        handle="@custom",
        runtime="openai-api",
        base_url=env[names[0]],
        model=env[names[1]],
        api_key=env[names[2]],
        system_prompt="Reply concisely.",
    )
    session = ApiAgentSession(cfg, tmp_path, timeout=60)
    try:
        await session.start()
        events = [event async for event in session.prompt("Reply exactly AITEAMS_API_OK")]
        assert events[-1].event_type == "completed"
        assert "AITEAMS_API_OK" in events[-1].metadata["full_text"]
    finally:
        await session.close()
