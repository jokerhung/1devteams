"""Opt-in: no real agent ever sees the repository working tree."""

import os

import pytest

from app.acp.client import ACPSession
from app.acp.types import AgentRuntimeConfig

pytestmark = pytest.mark.real_acp


@pytest.mark.parametrize("runtime", ["codex", "claude-code"])
async def test_real_read_structure(runtime, tmp_path):
    if os.environ.get("AITEAMS_RUN_REAL_ACP") != "1":
        pytest.skip("Set AITEAMS_RUN_REAL_ACP=1 to run live CLIs")
    (tmp_path / "src").mkdir()
    (tmp_path / "src/example.py").write_text('print("hello")', encoding="utf-8")
    cfg = AgentRuntimeConfig(
        agent_id="real-spike",
        handle="@custom",
        runtime=runtime,
        system_prompt="Only inspect this disposable workspace. Never modify files.",
    )
    session = ACPSession(cfg, tmp_path, diagnostic=True, timeout=60)
    try:
        await session.start()
        events = [
            event
            async for event in session.prompt(
                "List the files under src and describe the directory structure. Do not modify files."
            )
        ]
        assert any(event.event_type == "message_chunk" and event.content for event in events)
        assert events[-1].event_type == "completed", [event.model_dump() for event in events]
        assert events[-1].metadata["stop_reason"] == "end_turn"
    finally:
        await session.close()
