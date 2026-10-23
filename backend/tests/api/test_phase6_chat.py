from uuid import uuid4

from tests.api.conftest import ticket


async def test_idempotent_message_and_terminal_read_only(client):
    item = await ticket(client)
    tid = item["id"]
    client_id = str(uuid4())
    body = {"text": "Hello", "client_msg_id": client_id}
    first = await client.post(f"/api/tickets/{tid}/messages", json=body)
    second = await client.post(f"/api/tickets/{tid}/messages", json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["seq"] == second.json()["seq"]
    rows = (await client.get(f"/api/tickets/{tid}/messages")).json()
    assert len(rows) == 2 and rows[0]["metadata"]["initial"]
    config = (await client.get(f"/api/tickets/{tid}/chat-config")).json()
    assert config == {"can_report": True, "can_confirm": True, "max_files": 5, "max_mb": 10}
    await client.post(f"/api/tickets/{tid}/cancel")
    assert (await client.post(f"/api/tickets/{tid}/messages", json={"text": "closed"})).status_code == 409


async def test_remove_pending_attachment_frees_slot(client):
    item = await ticket(client)
    tid = item["id"]
    files = []
    for i in range(5):
        response = await client.post(
            f"/api/tickets/{tid}/attachments", files={"file": (f"file{i}.txt", b"hello", "text/plain")}
        )
        assert response.status_code == 201, response.text
        files.append(response.json())
    assert (
        await client.post(f"/api/tickets/{tid}/attachments", files={"file": ("extra.txt", b"hello")})
    ).status_code == 422
    assert (await client.delete(f"/api/attachments/{files[0]['id']}")).status_code == 204
    assert (
        await client.post(f"/api/tickets/{tid}/attachments", files={"file": ("extra.txt", b"hello")})
    ).status_code == 201
    sent = await client.post(f"/api/tickets/{tid}/messages", json={"attachment_ids": [files[1]["id"]]})
    assert sent.status_code == 201
    assert sent.json()["metadata"]["attachments"][0]["url"].startswith("/api/attachments/")
    assert (await client.delete(f"/api/attachments/{files[1]['id']}")).status_code == 409
