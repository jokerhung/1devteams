import json
import sys
from pathlib import Path

import pytest

from app.acp.client import ACPSession
from app.acp.types import AgentRuntimeConfig, PermissionProfile


@pytest.fixture
def cfg():
    return AgentRuntimeConfig(
        agent_id="custom-id",
        handle="@custom",
        runtime="codex",
        model="model-a",
        system_prompt="A custom role",
        permission_profile=PermissionProfile(allow_write=True, allow_terminal=True),
    )


@pytest.fixture
def make_session(tmp_path, cfg):
    def make(steps, config=None, **kwargs):
        scenario = tmp_path / "scenario.json"
        scenario.write_text(json.dumps(steps), encoding="utf-8")
        return ACPSession(
            config or cfg,
            tmp_path,
            lambda _: [sys.executable, str(Path(__file__).with_name("fake_agent.py")), str(scenario)],
            client_tools_only=True,
            **kwargs,
        )

    return make


@pytest.fixture
def handshake():
    return [
        {"expect": "initialize", "reply": {"protocolVersion": 1, "agentCapabilities": {}}},
        {
            "expect": "session/new",
            "reply": {"sessionId": "session-1", "models": {"currentModelId": "default"}},
        },
        {"expect": "session/set_model", "reply": {}},
    ]
