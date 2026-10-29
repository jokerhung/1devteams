import json
from collections import deque

import pytest

from app.engine.orchestrator import parse_decision
from app.engine.runner import TicketRunner
from tests.api.conftest import project
from tests.engine.conftest import settled
from tests.engine.test_engine import make_ticket


@pytest.mark.parametrize(
    "text",
    [
        '{"next_worker":"unknown","task_instruction":"do"}',
        '{"next_worker":"FINISH","task_instruction":""}',
        "[]",
        "not json",
    ],
)
def test_invalid_decision_cannot_dispatch(text):
    with pytest.raises((ValueError, TypeError)):
        parse_decision(text, {"worker_0": object()})


async def create(client, max_rounds=20):
    entity = await project(client, seeded=True)
    agents = (await client.get(f"/api/projects/{entity['id']}/effective-agents")).json()
    leader = next(a for a in agents if a["handle"] == "@leader")
    response = await client.post(
        f"/api/projects/{entity['id']}/workflows",
        json={
            "name": "Orchestrator",
            "ticket_prefix": "ORCH",
            "orchestrator": {
                "coordinator_agent_id": leader["id"],
                "instructions": "Build and verify; fix FAIL then retest",
                "max_rounds": max_rounds,
            },
        },
    )
    assert response.status_code == 201, response.text
    workflow = response.json()
    assert (await client.post(f"/api/workflows/{workflow['id']}/publish")).status_code == 200
    workers = {
        node["data"].get("agent_handle"): node["id"]
        for node in workflow["graph"]["nodes"]
        if node["id"].startswith("worker_")
    }
    return workflow, workers


def decision(worker, instruction):
    return json.dumps({"next_worker": worker, "task_instruction": instruction})


async def test_dynamic_handoffs_fail_fix_pass_and_complete_with_shared_results(engine_client):
    client = engine_client
    workflow, workers = await create(client)
    client.factory.scripts["@leader"] = deque(
        [
            decision(workers["@ba"], "Write requirements"),
            decision(workers["@developer"], "Implement requirements"),
            decision(workers["@tester"], "Verify implementation"),
            decision(workers["@developer"], "Fix failing test"),
            decision(workers["@tester"], "Retest fix"),
            decision("FINISH", "Delivered with passing tests"),
        ]
    )
    client.factory.scripts["@ba"] = deque(["REQUIREMENTS_UNIQUE"])
    client.factory.scripts["@tester"] = deque(["STATUS: FAIL unique_bug", "STATUS: PASS"])
    ticket, _ = await make_ticket(client, workflow, auto=True)
    await settled(client, ticket["id"], "COMPLETED")
    assert len(client.factory.prompts["@developer"]) == 2
    assert "REQUIREMENTS_UNIQUE" in client.factory.prompts["@developer"][0][0]
    assert "unique_bug" in client.factory.prompts["@developer"][1][0]
    assert "Fix failing test" in client.factory.prompts["@developer"][1][0]
    result = (await client.get(f"/api/tickets/{ticket['id']}")).json()
    assert result["result"]["summary"] == "Delivered with passing tests"


async def test_invalid_target_fails_instead_of_silently_finishing(engine_client):
    client = engine_client
    workflow, _ = await create(client)
    client.factory.scripts["@leader"] = deque([decision("arbitrary-agent", "do something")])
    ticket, _ = await make_ticket(client, workflow, auto=True)
    await settled(client, ticket["id"], "FAILED")


async def test_round_limit_waits_for_user_instead_of_looping(engine_client):
    client = engine_client
    workflow, workers = await create(client, max_rounds=1)
    client.factory.scripts["@leader"] = deque([decision(workers["@ba"], "requirements")])
    client.factory.scripts["@ba"] = deque(["Requirements ready"])
    ticket, _ = await make_ticket(client, workflow, auto=True)
    await settled(client, ticket["id"], "WAITING_USER_INPUT")
    assert len(client.factory.prompts["@leader"]) == 1
    old = client.app.state.ticket_runner
    await old.close()
    runner = TicketRunner(old.sessions, old.pool, old.events, old.settings, old.checkpointer)
    client.app.state.ticket_runner = runner
    await runner.recover()
    client.factory.scripts["@leader"].append(decision("FINISH", "User accepted"))
    response = await client.post(f"/api/tickets/{ticket['id']}/reply", json={"text": "Tiếp tục tổng kết"})
    assert response.status_code == 200, response.text
    await settled(client, ticket["id"], "COMPLETED")


async def test_worker_retry_resumes_assignment_without_repeating_coordinator(engine_client):
    client = engine_client
    workflow, workers = await create(client)
    client.factory.scripts["@leader"] = deque(
        [
            decision(workers["@ba"], "Assigned before failure"),
            decision("FINISH", "Done"),
        ]
    )
    client.factory.scripts["@ba"] = deque(["ERROR", "ERROR", "Recovered requirements"])
    ticket, _ = await make_ticket(client, workflow, auto=True)
    await settled(client, ticket["id"], "FAILED")
    response = await client.post(f"/api/tickets/{ticket['id']}/retry")
    assert response.status_code == 200, response.text
    await settled(client, ticket["id"], "COMPLETED")
    assert len(client.factory.prompts["@leader"]) == 2
    assert "Assigned before failure" in client.factory.prompts["@ba"][-1][0]


@pytest.mark.parametrize("with_design", [True, False])
async def test_feature_template_runs_selected_workers_and_saves_markdown(engine_client, with_design):
    client = engine_client
    entity = await project(client, seeded=True)
    pid = entity["id"]
    template = (await client.get(f"/api/orchestrator-templates?project_id={pid}")).json()[0]
    workflow = (
        await client.post(
            f"/api/projects/{pid}/workflows",
            json={
                "name": "Feature",
                "ticket_prefix": "FEAT",
                "orchestrator": template["orchestrator"],
            },
        )
    ).json()
    assert (await client.post(f"/api/workflows/{workflow['id']}/publish")).status_code == 200
    workers = {
        n["data"].get("agent_handle"): n["id"]
        for n in workflow["graph"]["nodes"]
        if n["id"].startswith("worker_")
    }
    sequence = (
        ["@ba", "@planner"]
        + (["@designer"] if with_design else [])
        + ["@developer", "@tester", "@developer", "@tester"]
    )
    client.factory.scripts["@leader"] = deque(
        [decision(workers[h], f"Task for {h}") for h in sequence] + [decision("FINISH", "Feature delivered")]
    )
    for handle, content in [
        ("@ba", "# Requirements"),
        ("@planner", "# Implementation plan"),
        ("@designer", "# UI design"),
    ]:
        client.factory.scripts[handle] = deque([content])
    client.factory.scripts["@tester"] = deque(["STATUS: FAIL edge case", "STATUS: PASS"])
    ticket, _ = await make_ticket(client, workflow, auto=True)
    await settled(client, ticket["id"], "COMPLETED")
    folder = client.workspace / "docs/tickets" / ticket["id"]
    assert (folder / "requirements.md").read_text(encoding="utf-8") == "# Requirements"
    assert (folder / "implementation-plan.md").read_text(encoding="utf-8") == "# Implementation plan"
    assert (folder / "design.md").exists() is with_design
    assert (folder / "test-report.md").read_text(encoding="utf-8") == "STATUS: PASS"
    assert len(client.factory.prompts["@developer"]) == 2
    assert "edge case" in client.factory.prompts["@developer"][-1][0]
    assert len(client.factory.prompts["@designer"]) == int(with_design)


@pytest.mark.parametrize("asker", ["coordinator", "worker"])
async def test_orchestrator_question_waits_for_creator_and_resumes_after_restart(engine_client, asker):
    client = engine_client
    workflow, workers = await create(client)
    if asker == "coordinator":
        client.factory.scripts["@leader"] = deque(
            [decision("ASK_USER", "Confirm scope?"), decision("FINISH", "Done")]
        )
    else:
        client.factory.scripts["@leader"] = deque(
            [decision(workers["@ba"], "Clarify scope"), decision("FINISH", "Done")]
        )
        client.factory.scripts["@ba"] = deque(["@@ASK_USER: Confirm scope?", "Requirements confirmed"])
    ticket, _ = await make_ticket(client, workflow, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_INPUT")
    assert len(client.factory.prompts["@leader"]) == 1
    notifications = (await client.get("/api/notifications")).json()
    # The same input gate notifies the ticket creator and supports ordinary ticket replies.
    assert "Confirm scope?" in str(notifications)
    old = client.app.state.ticket_runner
    await old.close()
    runner = TicketRunner(old.sessions, old.pool, old.events, old.settings, old.checkpointer)
    client.app.state.ticket_runner = runner
    await runner.recover()
    assert (
        await client.post(f"/api/tickets/{tid}/reply", json={"text": "USER_SCOPE_CONFIRMED"})
    ).status_code == 200
    await settled(client, tid, "COMPLETED")
    handle = "@leader" if asker == "coordinator" else "@ba"
    assert "USER_SCOPE_CONFIRMED" in client.factory.prompts[handle][-1][0]
