import json
from collections import deque

from tests.api.conftest import project
from tests.engine.conftest import settled
from tests.engine.test_engine import make_ticket


async def test_feature_documents_system_test_loop_and_approved_release(engine_client):
    client = engine_client
    entity = await project(client, seeded=True)
    response = await client.post(
        f"/api/projects/{entity['id']}/workflows",
        json={"name": "Add feature", "ticket_prefix": "FEAT", "template": "add_feature"},
    )
    assert response.status_code == 201, response.text
    workflow = response.json()
    published = await client.post(f"/api/workflows/{workflow['id']}/publish")
    assert published.status_code == 200, published.text
    client.factory.scripts["@leader"] = deque(["Feature scope ready\n@@ROUTE: ready"])
    client.factory.scripts["@ba"] = deque(["# Requirements\nAcceptance criteria\n@@ROUTE: ready"])
    client.factory.scripts["@designer"] = deque(["# Design\nScreen wireframe"])
    client.factory.scripts["@planner"] = deque(["# Implementation plan\nUpdate app.txt"])
    client.factory.scripts["@tester"] = deque(
        [
            "# System test cases\nST-01: verify feature through UI",
            "# System test report\nST-01 BLOCKED\n@@ROUTE: fail",
            "# System test report\nST-01 PASS\n@@ROUTE: pass",
        ]
    )
    initial = client.git("rev-parse", "HEAD").strip()
    ticket, _ = await make_ticket(client, workflow, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_CONFIRM")
    assert len(client.factory.prompts["@developer"]) == 2
    assert not client.factory.prompts["@devops"]
    assert client.git("rev-parse", "HEAD").strip() == initial
    folder = client.workspace / "docs" / "tickets" / tid
    documents = sorted(path.name for path in folder.glob("*.md"))
    assert documents == [
        "design.md",
        "implementation-plan.md",
        "requirements.md",
        "system-test-cases.md",
        "system-test-report.md",
    ]
    assert "ST-01 PASS" in (folder / "system-test-report.md").read_text(encoding="utf-8")
    assert "# Requirements" in client.factory.prompts["@planner"][0][0]
    assert "system-test-cases.md" in client.factory.prompts["@developer"][0][0]
    files = ["app.txt"] + [f"docs/tickets/{tid}/{name}" for name in documents]
    client.factory.scripts["@devops"].append(
        "@@RELEASE\n"
        + json.dumps(
            {"approve": True, "files": files, "commit_message": "feat: deliver feature", "concerns": []}
        )
        + "\n@@END"
    )
    approval = await client.post(f"/api/tickets/{tid}/confirm", json={"approved": True})
    assert approval.status_code == 200, approval.text
    await settled(client, tid, "COMPLETED")
    assert set(client.git("diff", "--name-only", "HEAD~1", "HEAD").splitlines()) == set(files)
    assert (
        client.git("rev-parse", "HEAD").strip()
        == client.git("--git-dir", str(client.remote), "rev-parse", "main").strip()
    )
