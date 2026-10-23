from collections import deque
from copy import deepcopy

from tests.api.conftest import project
from tests.engine.conftest import settled
from tests.engine.test_engine import make_ticket


async def test_node_iteration_override_interrupts_before_next_agent_turn(engine_client):
    client = engine_client
    entity = await project(client, seeded=True)
    wid = entity["workflow"]["id"]
    graph = deepcopy(entity["workflow"]["graph"])
    next(node for node in graph["nodes"] if node["id"] == "n_dev")["data"]["max_iterations"] = 1
    assert (await client.put(f"/api/workflows/{wid}/graph", json=graph)).json()["is_valid"]
    workflow = (await client.post(f"/api/workflows/{wid}/publish")).json()
    client.factory.scripts["@tester"] = deque(["Fail\n@@ROUTE: fail", "Pass\n@@ROUTE: pass"])
    ticket, _ = await make_ticket(client, workflow=workflow, auto=True)
    state = await settled(client, ticket["id"], "WAITING_USER_INPUT")
    assert "lặp quá 1 lần ở n_dev" in state["waiting"]["payload"]["question"]
    assert len(client.factory.prompts["@developer"]) == 1
    assert (
        await client.post(f"/api/tickets/{ticket['id']}/reply", json={"text": "Continue"})
    ).status_code == 200
    await settled(client, ticket["id"], "WAITING_USER_CONFIRM")
    assert len(client.factory.prompts["@developer"]) == 2
