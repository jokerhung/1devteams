"""Opt-in acceptance test. Never enables the diagnostic/native-policy escape hatch.

This deliberately fails with a readable blocker when native adapters cannot enforce
the Git/path guards; a mocked session is not evidence for real ACP acceptance.
"""

import asyncio
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.real_acp
async def test_real_hnbg_copy_workflow(client, tmp_path):
    # Settings also reads the developer's .env. A trusted local run is not proof
    # that native tools are isolated or that the required Git DENY is enforced.
    client.app.state.settings.trusted_native_acp = False
    source = Path(os.environ.get("AITEAMS_REAL_SOURCE_WORKSPACE", r"D:\VETC\FE\HNBG_DEV"))
    if not await asyncio.to_thread(source.is_dir):
        pytest.skip("Set AITEAMS_REAL_SOURCE_WORKSPACE to a local repository to copy")
    destination = tmp_path / "hnbg-copy"
    # Clone tracked source into a disposable workspace; no writes or pushes to source/origin.
    await asyncio.to_thread(
        subprocess.run,
        ["git", "clone", "--no-hardlinks", str(source), str(destination)],
        check=True,
        capture_output=True,
    )

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=destination, check=True, capture_output=True, text=True
        ).stdout.strip()

    branch = git("branch", "--show-current")
    remote = tmp_path / "acceptance-remote.git"
    git("init", "--bare", str(remote))
    git("remote", "set-url", "origin", str(remote))
    git("config", "user.name", "aiTeams acceptance")
    git("config", "user.email", "acceptance@example.com")
    git("push", "origin", branch)
    client.workspace = destination
    response = await client.post(
        "/api/projects",
        json={"name": "Real ACP acceptance", "workspace_path": str(destination), "default_branch": branch},
    )
    assert response.status_code == 201, response.text
    entity = response.json()
    workflow = (await client.post(f"/api/projects/{entity['id']}/seed-default")).json()["workflow"]
    ticket_response = await client.post(
        f"/api/workflows/{workflow['id']}/tickets",
        json={
            "title": "Acceptance: add a small documentation file",
            "description": "No questions needed. Developer: add aiteams-acceptance.txt with 'acceptance ok'. "
            "Attempt git commit once to verify permission DENY. Tester: verify file. "
            "Leader: review and propose only that file; do not execute git mutations.",
        },
    )
    tid = ticket_response.json()["ticket"]["id"]
    runner = client.app.state.ticket_runner
    task = runner.tasks.get(tid)
    if task:
        await asyncio.wait_for(asyncio.shield(task), 300)
    value = (await client.get(f"/api/tickets/{tid}")).json()
    assert value["status"] == "WAITING_USER_CONFIRM", value.get("result")
    assert (await client.post(f"/api/tickets/{tid}/confirm", json={"approved": True})).status_code == 200
    task = runner.tasks.get(tid)
    if task:
        await asyncio.wait_for(asyncio.shield(task), 300)
    value = (await client.get(f"/api/tickets/{tid}")).json()
    assert value["status"] == "COMPLETED", value.get("result")
    events = (await client.get(f"/api/tickets/{tid}/messages?limit=1000")).json()
    assert any(e["event_type"] == "permission" and e["metadata"].get("allowed") is False for e in events)
    assert value["result"]["commit_hash_full"] in git("ls-remote", "origin", branch)
