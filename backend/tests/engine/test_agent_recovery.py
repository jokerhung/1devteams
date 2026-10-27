from collections import deque

import pytest

from tests.engine.conftest import settled
from tests.engine.test_engine import make_ticket


@pytest.mark.parametrize("handle", ["@ba", "@developer", "@tester"])
async def test_mention_failed_agent_resumes_workflow_and_hands_off(engine_client, handle):
    client = engine_client
    client.factory.scripts[handle] = deque(["ERROR"] * 4)
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "FAILED")
    # A second failed attempt must not poison the later successful result.
    response = await client.post(f"/api/tickets/{tid}/messages", json={"text": f"{handle} thử lại"})
    assert response.status_code == 201, response.text
    await settled(client, tid, "FAILED")
    response = await client.post(
        f"/api/tickets/{tid}/messages", json={"text": f"{handle} đã đủ thông tin, chốt và chạy tiếp"}
    )
    assert response.status_code == 201, response.text
    state = await settled(client, tid, "WAITING_USER_CONFIRM")
    runner = client.app.state.ticket_runner
    graph, ctx, _ = await runner.load(tid)
    snapshot = await graph.aget_state(runner.config(tid, ctx))
    assert snapshot.values["error"] is None
    assert state["current_node_id"] == "g_conf"
    assert client.factory.prompts["@developer"]
    assert client.factory.prompts["@tester"]
    assert "chốt và chạy tiếp" in client.factory.prompts[handle][-1][0]
    response = await client.post(f"/api/tickets/{tid}/confirm", json={"approved": True})
    assert response.status_code == 200, response.text
    await settled(client, tid, "COMPLETED")


async def test_unrelated_agent_does_not_skip_failed_node(engine_client):
    client = engine_client
    client.factory.scripts["@developer"] = deque(["ERROR", "ERROR"])
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "FAILED")
    response = await client.post(f"/api/tickets/{tid}/messages", json={"text": "@ba xem lại STR"})
    assert response.status_code == 201, response.text
    runner = client.app.state.ticket_runner
    await runner.adhoc_tasks[tid]
    state = (await client.get(f"/api/tickets/{tid}/state")).json()
    assert state["status"] == "FAILED"
    assert state["current_node_id"] == "n_dev"
    assert not client.factory.prompts["@tester"]
