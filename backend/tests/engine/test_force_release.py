import asyncio

from app.db.models import Ticket, User
from tests.engine.conftest import settled
from tests.engine.test_engine import make_ticket


async def test_force_release_all_changes_without_leader_approval(engine_client):
    client = engine_client
    ticket, _ = await make_ticket(client, auto=True)
    tid = ticket["id"]
    await settled(client, tid, "WAITING_USER_CONFIRM")
    (client.workspace / "other.txt").write_text("other ticket code")
    (client.workspace / ".env").write_text("SECRET=hidden")
    client.git("add", "other.txt")
    response = await client.post(f"/api/tickets/{tid}/force-release")
    assert response.status_code == 202, response.text
    state = await settled(client, tid, "COMPLETED")
    assert set(state["result"]["files"]) == {"app.txt", "other.txt"}
    assert (
        client.git("rev-parse", "HEAD").strip()
        == client.git("--git-dir", str(client.remote), "rev-parse", "main").strip()
    )
    assert not client.factory.prompts["@devops"]
    head = client.git("rev-parse", "HEAD")
    assert (await client.post(f"/api/tickets/{tid}/force-release")).status_code == 202
    assert client.git("rev-parse", "HEAD") == head
    assert tid not in client.app.state.ticket_runner.owned


async def test_force_release_push_failure_retry_existing_commit(engine_client):
    client = engine_client
    ticket, _ = await make_ticket(client)
    tid = ticket["id"]
    (client.workspace / "app.txt").write_text("updated")
    remote = client.git("remote", "get-url", "origin").strip()
    client.git("remote", "set-url", "origin", str(client.workspace / "missing.git"))
    assert (await client.post(f"/api/tickets/{tid}/force-release")).status_code == 202
    state = await settled(client, tid, "FAILED")
    head = client.git("rev-parse", "HEAD").strip()
    assert state["result"]["pending_release"]["commit_hash_full"] == head
    client.git("remote", "set-url", "origin", remote)
    assert (await client.post(f"/api/tickets/{tid}/force-release")).status_code == 202
    await settled(client, tid, "COMPLETED")
    assert client.git("rev-parse", "HEAD").strip() == head
    assert client.git("--git-dir", str(client.remote), "rev-parse", "main").strip() == head


async def test_force_release_stops_running_agent_and_deduplicates(engine_client):
    client = engine_client
    client.factory.blocked.add("@ba")
    ticket, _ = await make_ticket(client, auto=True)
    await asyncio.wait_for(client.factory.entered.wait(), 10)
    tid = ticket["id"]
    (client.workspace / "app.txt").write_text("manual repair")
    results = await asyncio.gather(*[client.post(f"/api/tickets/{tid}/force-release") for _ in range(2)])
    assert all(response.status_code == 202 for response in results)
    await settled(client, tid, "COMPLETED")
    assert client.git("rev-list", "--count", "HEAD").strip() == "2"
    assert all(not session.alive for session in client.factory.sessions)


async def test_force_release_requires_maintainer(engine_client):
    client = engine_client
    ticket, _ = await make_ticket(client)
    async with client.app.state.db_session() as db:
        owner = await db.get(User, client.owner["id"])
        owner.system_role = "MEMBER"
        # Remove ownership as well: ordinary members must not release.
        from app.db.models import Project

        project = await db.get(Project, ticket["project_id"])
        other = User(
            email="other@example.com", display_name="Other", password_hash="unused", avatar_initials="OT"
        )
        db.add(other)
        await db.flush()
        project.owner_id = other.id
        await db.commit()
    response = await client.post(f"/api/tickets/{ticket['id']}/force-release")
    assert response.status_code == 403
    async with client.app.state.db_session() as db:
        assert (await db.get(Ticket, ticket["id"])).status == "OPEN"
