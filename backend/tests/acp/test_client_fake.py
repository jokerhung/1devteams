import asyncio
import json
from pathlib import Path

import pytest

from app.acp.client import ACPSession, RuntimePolicyError
from app.acp.types import ACPStreamEvent


def update(update_type, **kwargs):
    return {
        "notify": "session/update",
        "params": {"sessionId": "session-1", "update": {"sessionUpdate": update_type, **kwargs}},
    }


async def test_full_turn(make_session, handshake, tmp_path):
    steps = [
        *handshake,
        {
            "expect": "session/prompt",
            "junk": True,
            "assert_prompt_prefix": "[SYSTEM ROLE]\nA custom role\n\n",
            "then": [
                update("agent_message_chunk", content={"type": "text", "text": "Working"}),
                update("agent_thought_chunk", content={"type": "text", "text": "Thinking"}),
                update("plan", entries=[]),
                update(
                    "tool_call",
                    toolCallId="t",
                    kind="edit",
                    title="Edit",
                    locations=[{"path": str(tmp_path / "a.txt")}],
                ),
                {
                    "request": "fs/write_text_file",
                    "params": {"sessionId": "session-1", "path": "a.txt", "content": "x"},
                },
                update(
                    "tool_call_update",
                    toolCallId="t",
                    content=[{"type": "diff", "path": "a.txt", "oldText": "", "newText": "x"}],
                ),
            ],
            "reply": {"stopReason": "end_turn"},
        },
        {"expect": "session/prompt", "assert_no_role": True, "reply": {"stopReason": "end_turn"}},
    ]
    session = make_session(steps)
    try:
        await session.start()
        events = [event async for event in session.prompt("Go")]
        assert {event.event_type for event in events} >= {
            "message_chunk",
            "thought_chunk",
            "plan",
            "tool_call",
            "file_edit",
            "completed",
        }
        assert events[-1].metadata["full_text"] == "Working"
        assert str(tmp_path / "a.txt") in events[-1].metadata["modified_files"]
        assert events[-1].metadata["model_effective"] == "model-a"
        second = [event async for event in session.prompt("Again")]
        assert second[-1].event_type == "completed" and second[-1].metadata["modified_files"] == []
    finally:
        await session.close()


async def test_developer_commit_blocked(make_session, handshake):
    permission = {
        "request": "session/request_permission",
        "params": {
            "sessionId": "session-1",
            "toolCall": {"kind": "execute", "rawInput": {"command": "git -c user.name=a commit -m x"}},
            "options": [{"kind": "allow_once", "optionId": "a"}, {"kind": "reject_once", "optionId": "r"}],
        },
        "assert_option": "r",
    }
    session = make_session(
        [*handshake, {"expect": "session/prompt", "then": [permission], "reply": {"stopReason": "end_turn"}}]
    )
    try:
        await session.start()
        events = [event async for event in session.prompt("Commit")]
        assert events[0].event_type == "permission" and events[0].metadata["allowed"] is False
        assert events[-1].event_type == "completed"
    finally:
        await session.close()


async def test_timeout_cancel(make_session, handshake, tmp_path):
    marker = tmp_path / "cancel.txt"
    session = make_session(
        [
            *handshake,
            {
                "expect": "session/prompt",
                "wait_for_cancel": True,
                "cancel_marker": str(marker),
                "reply": {"stopReason": "cancelled"},
            },
        ],
        timeout=0.2,
    )
    try:
        await session.start()
        events = await asyncio.wait_for(collect(session), 5)
        assert events[-1].event_type == "error" and "timed out" in events[-1].content
        assert not session.alive
        assert marker.exists()
    finally:
        await session.close()


async def collect(session):
    return [event async for event in session.prompt("Go")]


async def test_crash_with_redacted_stderr(make_session, handshake, cfg):
    cfg.env = {"TEST_KEY": "private-value"}
    session = make_session(
        [*handshake, {"expect": "session/prompt", "stderr": "failed private-value", "exit": True}], cfg
    )
    try:
        await session.start()
        events = await collect(session)
        assert events[-1].event_type == "error"
        assert "private-value" not in json.dumps([event.model_dump() for event in events])
    finally:
        await session.close()


async def test_claude_config_options(make_session, cfg):
    cfg.runtime = "claude-code"
    session = make_session(
        [
            {"expect": "initialize", "reply": {"protocolVersion": 1}},
            {
                "expect": "session/new",
                "assert_params": {"_meta": {"systemPrompt": {"append": cfg.system_prompt}}},
                "reply": {
                    "sessionId": "session-1",
                    "configOptions": [{"id": "model", "currentValue": "old"}],
                },
            },
            {
                "expect": "session/set_config_option",
                "assert_params": {"configId": "model", "value": cfg.model},
            },
            {"expect": "session/prompt", "reply": {"stopReason": "end_turn"}},
        ],
        cfg,
    )
    try:
        await session.start()
        assert (await collect(session))[-1].metadata["model_effective"] == cfg.model
    finally:
        await session.close()


async def test_model_fallback(make_session, handshake):
    handshake[-1] = {"expect": "session/set_model", "error": {"code": -32601, "message": "Unsupported"}}
    session = make_session([*handshake, {"expect": "session/prompt", "reply": {"stopReason": "end_turn"}}])
    try:
        await session.start()
        assert (await collect(session))[-1].metadata["model_effective"] == "default"
    finally:
        await session.close()


async def test_native_adapter_fails_closed(cfg, tmp_path):
    session = ACPSession(cfg, tmp_path)
    with pytest.raises(RuntimePolicyError):
        await session.start()
    assert session.process is None


async def test_nested_redaction_before_json_encoding(cfg, tmp_path):
    secret = 'private-"quoted"-\\value'
    cfg.env = {"TOKEN": secret}
    session = ACPSession(cfg, tmp_path)
    await session._emit(
        ACPStreamEvent(
            agent_handle=cfg.handle,
            event_type="log",
            content=secret,
            metadata={"nested": [{"credential": secret}]},
        )
    )
    event = session._queue.get_nowait()
    assert event.content == "<redacted>"
    assert event.metadata["nested"][0]["credential"] == "<redacted>"


async def test_abandoned_turn_closes_session(make_session, handshake):
    session = make_session(
        [
            *handshake,
            {
                "expect": "session/prompt",
                "then": [update("agent_message_chunk", content={"type": "text", "text": "First"})],
                "wait_for_cancel": True,
                "reply": {"stopReason": "cancelled"},
            },
        ]
    )
    try:
        await session.start()
        stream = session.prompt("Go")
        assert (await anext(stream)).content == "First"
        await stream.aclose()
        assert not session.alive and session.process.returncode is not None
    finally:
        await session.close()


async def test_captured_codex_notifications(cfg, tmp_path):
    capture = Path(__file__).parents[1] / "fixtures" / "acp" / "codex.ndjson"
    messages = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
    session = ACPSession(cfg, tmp_path)
    session.busy = True
    for message in messages:
        if message.get("method") == "session/update":
            session.session_id = message["params"]["sessionId"]
            await session._notification(message["method"], message["params"])
    events = []
    while not session._queue.empty():
        events.append(session._queue.get_nowait())
    assert any(event.event_type == "message_chunk" for event in events)
    assert any(event.event_type == "tool_call" for event in events)


@pytest.mark.parametrize("runtime", ["codex", "claude"])
async def test_captured_handshake(runtime, cfg, make_session):
    capture = Path(__file__).parents[1] / "fixtures" / "acp" / f"{runtime}.ndjson"
    messages = [json.loads(line) for line in capture.read_text(encoding="utf-8").splitlines()]
    replies = [message["result"] for message in messages if "result" in message]
    initialized = next(reply for reply in replies if "protocolVersion" in reply)
    created = next(reply for reply in replies if "sessionId" in reply)
    cfg.runtime = "claude-code" if runtime == "claude" else "codex"
    cfg.model = None
    steps = [
        {"expect": "initialize", "reply": initialized},
        {"expect": "session/new", "reply": created},
    ]
    desired = "default" if runtime == "claude" else "read-only"
    if desired in {mode["id"] for mode in created.get("modes", {}).get("availableModes", [])}:
        steps.append({"expect": "session/set_mode", "reply": {}})
    session = make_session(steps, cfg)
    try:
        await session.start()
        assert session.alive and session.model_effective
    finally:
        await session.close()
