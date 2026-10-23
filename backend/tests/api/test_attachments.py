import io
from datetime import timedelta

from PIL import Image
from sqlalchemy import select

from app.db.base import now
from app.db.models import Attachment
from app.services.assets import attach_to_message, cleanup_pending
from app.services.ticket_service import add_message
from tests.api.conftest import ticket


def picture():
    output = io.BytesIO()
    Image.new("RGB", (600, 400), "red").save(output, format="PNG")
    return output.getvalue()


async def test_upload_limit_thumbnail_and_garbage(client):
    item = await ticket(client)
    path = f"/api/tickets/{item['id']}/attachments"
    response = await client.post(path, files={"file": ("../../picture.png", picture(), "image/png")})
    assert response.status_code == 201, response.text
    uploaded = response.json()
    assert uploaded["filename"] == "picture.png" and uploaded["thumbnail_url"]
    thumb = await client.get(uploaded["thumbnail_url"])
    assert thumb.status_code == 200
    assert max(Image.open(io.BytesIO(thumb.content)).size) == 256
    assert (await client.post(path, files={"file": ("script.EXE", b"MZ", "text/plain")})).status_code == 422
    assert (
        await client.post(path, files={"file": ("large.txt", b"x" * (11 * 1024 * 1024), "text/plain")})
    ).status_code == 413
    for index in range(4):
        assert (
            await client.post(path, files={"file": (f"file{index}.txt", b"text", "text/plain")})
        ).status_code == 201
    assert (await client.post(path, files={"file": ("sixth.txt", b"text", "text/plain")})).status_code == 422
    async with client.app.state.db_session() as db:
        rows = list((await db.scalars(select(Attachment))).all())
        message = await add_message(db, item["id"], content="Attachment message")
        await attach_to_message(
            db, item["id"], message.id, [rows[0].id], client.owner["id"], client.app.state.settings
        )
        for row in rows:
            row.created_at = now() - timedelta(hours=25)
        await db.commit()
        assert await cleanup_pending(db, client.app.state.settings) == 4
        assert len((await db.scalars(select(Attachment))).all()) == 1


async def test_logo_sanitization_and_limit(client):
    assert (
        await client.post("/api/assets/logo", files={"file": ("large.png", b"x" * (301 * 1024), "image/png")})
    ).status_code == 413
    assert (
        await client.post("/api/assets/logo", files={"file": ("fake.png", b"not-an-image", "image/png")})
    ).status_code == 422
    # A recognizable PNG with a bad chunk checksum must return validation, not HTTP 500.
    broken = bytearray(picture())
    broken[broken.index(b"IDAT") + 4] ^= 1
    assert (
        await client.post("/api/assets/logo", files={"file": ("broken.png", bytes(broken), "image/png")})
    ).status_code == 422
    response = await client.post("/api/assets/logo", files={"file": ("logo.png", picture(), "image/png")})
    assert response.status_code == 201, response.text
    image = await client.get(response.json()["logo_url"])
    assert image.status_code == 200 and max(Image.open(io.BytesIO(image.content)).size) == 256
