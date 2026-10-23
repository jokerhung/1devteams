import asyncio

from tests.api.conftest import project


async def test_ticket_order_versions_numbering_tree(client):
    entity = await project(client)
    pid = entity["id"]
    draft = (
        await client.post(f"/api/projects/{pid}/workflows", json={"name": "Draft", "ticket_prefix": "FEAT"})
    ).json()
    assert (
        await client.post(f"/api/workflows/{draft['id']}/tickets", json={"title": "No"})
    ).status_code == 400
    seeded = (await client.post(f"/api/projects/{pid}/seed-default")).json()["workflow"]
    created = await client.post(
        f"/api/workflows/{seeded['id']}/tickets",
        json={"title": "Đơ nút Xuất Excel báo cáo", "auto_start": False},
    )
    assert created.status_code == 201, created.text
    ticket = created.json()["ticket"]
    assert ticket["code"] == "#BUG-1" and ticket["channel_slug"] == "bug-do-nut-xuat-excel-bao-cao"
    assert not created.json()["auto_start_pending"] and ticket["status"] == "OPEN"
    assert str(ticket["id"]) in created.json()["chat_url"]
    await client.put(f"/api/workflows/{seeded['id']}/graph", json=seeded["graph"])
    await client.post(f"/api/workflows/{seeded['id']}/publish")
    assert (await client.get(f"/api/tickets/{ticket['id']}")).json()["workflow_version"] == 1
    await client.put(f"/api/workflows/{draft['id']}/graph", json=seeded["graph"])
    await client.post(f"/api/workflows/{draft['id']}/publish")
    second = (
        await client.post(
            f"/api/workflows/{draft['id']}/tickets", json={"title": "Next", "auto_start": False}
        )
    ).json()["ticket"]
    assert second["code"] == "#FEAT-2"
    assert (await client.patch(f"/api/tickets/{ticket['id']}", json={"title": "Updated"})).status_code == 200
    tree = (await client.get(f"/api/projects/{pid}/tree")).json()
    assert len(tree["workflows"]) == 2 and sum(len(item["tickets"]) for item in tree["workflows"]) == 2
    assert len((await client.get(f"/api/projects/{pid}/tickets?q=Updated")).json()) == 1


async def test_concurrent_ticket_counter_and_message_resume(client):
    entity = await project(client, seeded=True)
    wid = entity["workflow"]["id"]
    responses = await asyncio.gather(
        *(
            client.post(f"/api/workflows/{wid}/tickets", json={"title": "Same title", "auto_start": False})
            for _ in range(6)
        )
    )
    assert all(response.status_code == 201 for response in responses), [
        response.text for response in responses
    ]
    tickets = [response.json()["ticket"] for response in responses]
    assert sorted(item["number"] for item in tickets) == list(range(1, 7))
    assert len({item["channel_slug"] for item in tickets}) == 6
    from app.services.ticket_service import add_message

    async with client.app.state.db_session() as db:
        await add_message(
            db, tickets[0]["id"], content="First", sender_name="@tester", event_type="thought_chunk"
        )
        await add_message(db, tickets[0]["id"], content="Second", event_type="log")
        await db.commit()
    messages = (await client.get(f"/api/tickets/{tickets[0]['id']}/messages?after_seq=1")).json()
    assert [message["content"] for message in messages] == ["Second"]
    logs = (await client.get(f"/api/tickets/{tickets[0]['id']}/logs?agent=@tester")).json()
    assert len(logs) == 1 and logs[0]["kind"] == "thought_chunk"
