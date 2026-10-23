import asyncio
import json
import os
from collections import deque
from pathlib import Path
from uuid import uuid4

from tests.engine.conftest import settled
from tests.engine.test_engine import make_ticket


async def test_chat_reply_client_identity_gate_resolution_and_export(engine_client):
    client = engine_client
    client.factory.scripts["@ba"] = deque(["Question?\n@@ROUTE: need_info", "STR ready\n@@ROUTE: ready"])
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_INPUT")
    client_id = str(uuid4())
    reply = await client.post(
        f"/api/tickets/{tid}/reply", json={"text": "Chrome steps", "client_msg_id": client_id}
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["message"]["metadata"]["client_msg_id"] == client_id
    await settled(client, tid, "WAITING_USER_CONFIRM")
    assert (await client.post(f"/api/tickets/{tid}/confirm", json={"approved": True})).status_code == 200
    await settled(client, tid, "COMPLETED")
    events = (await client.get(f"/api/tickets/{tid}/messages?limit=1000")).json()
    assert events[0]["metadata"]["initial"]
    assert len([e for e in events if e["sender_type"] == "USER"]) == 2
    assert len([e for e in events if e["event_type"] == "gate_resolved"]) == 2
    assert any(e["metadata"].get("result", {}).get("commit_hash") for e in events)
    if export := os.environ.get("PHASE6_FIXTURE_PATH"):
        Path(export).parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(
            Path(export).write_text, json.dumps(events, indent=2, ensure_ascii=False), encoding="utf-8"
        )
