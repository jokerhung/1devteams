from copy import deepcopy

import pytest

from tests.api.conftest import project


@pytest.mark.parametrize("limit", [0, -1, 1001, True, 1.5, "3"])
async def test_invalid_iteration_override_cannot_publish(client, limit):
    entity = await project(client, seeded=True)
    graph = deepcopy(entity["workflow"]["graph"])
    next(node for node in graph["nodes"] if node["id"] == "n_dev")["data"]["max_iterations"] = limit
    path = f"/api/workflows/{entity['workflow']['id']}"
    response = await client.put(f"{path}/graph", json=graph)
    assert response.status_code == 200 and not response.json()["is_valid"]
    assert any("max_iterations" in error for error in response.json()["errors"])
    assert (await client.post(f"{path}/publish")).status_code == 400


async def test_blank_and_security_templates(client):
    entity = await project(client, seeded=True)
    security = (
        await client.post(
            "/api/agents",
            json={"handle": "@security_checker", "display_name": "Security", "role_key": "SECURITY"},
        )
    ).json()
    await client.post(
        f"/api/projects/{entity['id']}/members",
        json={"member_type": "AGENT", "member_id": security["id"]},
    )
    for template, prefix in [("blank", "BLANK"), ("bugfix_with_security_review", "SEC")]:
        response = await client.post(
            f"/api/projects/{entity['id']}/workflows",
            json={"name": template, "ticket_prefix": prefix, "template": template},
        )
        assert response.status_code == 201, response.text
        workflow = response.json()
        assert workflow["is_valid"], workflow["validation_errors"]
        graph = workflow["graph"]
        if template == "blank":
            assert [node["type"] for node in graph["nodes"]] == ["start", "end"]
            assert len(graph["edges"]) == 1
        else:
            links = {(edge["source"], edge["target"], edge.get("sourceHandle")) for edge in graph["edges"]}
            assert ("n_dev", "n_security", None) in links
            assert ("n_security", "n_test", "pass") in links
            assert ("n_security", "n_dev", "fail") in links
