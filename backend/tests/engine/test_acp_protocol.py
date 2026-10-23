import io
import json
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

from app.acp.client import ACPSession
from tests.engine.conftest import settled
from tests.engine.test_engine import make_ticket


async def test_full_workflow_with_executable_acp_peer_and_image(engine_client, tmp_path):
    client = engine_client
    counts = Counter()

    def update(text):
        return {
            "notify": "session/update",
            "params": {
                "sessionId": "session-1",
                "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": text}},
            },
        }

    def factory(cfg, workspace):
        counts[cfg.handle] += 1
        actions = []
        text = "STR\n@@ROUTE: ready"
        if cfg.handle == "@ba" and counts[cfg.handle] == 1:
            text = "Attach a screenshot?\n@@ROUTE: need_info"
        if cfg.handle == "@developer":
            actions = [
                {
                    "request": "fs/write_text_file",
                    "params": {"sessionId": "session-1", "path": "app.txt", "content": "fixed through ACP\n"},
                },
                {
                    "request": "session/request_permission",
                    "params": {
                        "sessionId": "session-1",
                        "toolCall": {"kind": "execute", "rawInput": {"command": "git commit -am forbidden"}},
                        "options": [
                            {"kind": "allow_once", "optionId": "a"},
                            {"kind": "reject_once", "optionId": "r"},
                        ],
                    },
                    "assert_option": "r",
                },
            ]
            text = "Fixed app.txt"
        if cfg.handle == "@tester":
            text = "PASS\n@@ROUTE: pass"
        if cfg.handle == "@leader":
            text = (
                '@@RELEASE\n{"approve":true,"files":["app.txt"],'
                '"commit_message":"fix: ACP repair","concerns":[]}\n@@END'
            )
        prompt_step = {
            "expect": "session/prompt",
            "then": [*actions, update(text)],
            "reply": {"stopReason": "end_turn"},
        }
        if cfg.handle == "@ba" and counts[cfg.handle] == 2:
            prompt_step["assert_image_count"] = 1
        steps = [
            {
                "expect": "initialize",
                "reply": {"protocolVersion": 1, "agentCapabilities": {"promptCapabilities": {"image": True}}},
            },
            {"expect": "session/new", "reply": {"sessionId": "session-1"}},
            prompt_step,
        ]
        path = tmp_path / f"{cfg.agent_id}-{counts[cfg.handle]}.json"
        path.write_text(json.dumps(steps), encoding="utf-8")
        executable = Path(__file__).parents[1] / "acp" / "fake_agent.py"
        return ACPSession(
            cfg,
            workspace,
            lambda _: [sys.executable, str(executable), str(path)],
            client_tools_only=True,
            timeout=10,
        )

    client.app.state.acp_pool.factory = factory
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_INPUT")
    picture = io.BytesIO()
    Image.new("RGB", (2, 2)).save(picture, format="PNG")
    upload = await client.post(
        f"/api/tickets/{tid}/attachments", files={"file": ("screen.png", picture.getvalue(), "image/png")}
    )
    assert upload.status_code == 201
    response = await client.post(
        f"/api/tickets/{tid}/messages", json={"attachment_ids": [upload.json()["id"]]}
    )
    assert response.status_code == 201, response.text
    await settled(client, tid, "WAITING_USER_CONFIRM")
    assert (await client.post(f"/api/tickets/{tid}/confirm", json={"approved": True})).status_code == 200
    await settled(client, tid, "COMPLETED")
    events = (await client.get(f"/api/tickets/{tid}/messages?limit=1000")).json()
    assert any(e["event_type"] == "permission" and e["metadata"].get("allowed") is False for e in events)
    assert "fixed through ACP" in client.git("show", "HEAD:app.txt")
