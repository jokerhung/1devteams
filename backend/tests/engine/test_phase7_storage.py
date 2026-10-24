import json
import sqlite3

from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import select

from app.core.security import decrypt, encrypt
from app.db.models import Agent
from scripts import rotate_key
from scripts.backup import backup_sqlite
from tests.engine.test_engine import make_ticket


async def test_event_limits_scrub_and_attachment_deletion(engine_client):
    client = engine_client
    ticket, _ = await make_ticket(client)
    tid = ticket["id"]
    client.app.state.settings.max_event_chars = 1024
    await client.app.state.event_bus.publish(
        f"tickets/{tid}",
        {
            "event_type": "file_edit",
            "content": "sk-thisisatestsecret " + "x" * 3000,
            "metadata": {"many": ["x" * 500] * 100},
        },
    )
    events = (await client.get(f"/api/tickets/{tid}/messages")).json()
    event = events[-1]
    assert len(event["content"]) < 1024 and event["metadata"]["truncated"]
    full = await client.get(event["metadata"]["full_output_url"])
    assert full.status_code == 200 and "sk-thisisatestsecret" not in full.text
    assert len(full.json()["metadata"]["many"]) == 100
    client.app.state.settings.attach_quota_mb = 1
    upload = await client.post(
        f"/api/tickets/{tid}/attachments", files={"file": ("note.txt", b"notes", "text/plain")}
    )
    assert upload.status_code == 201, upload.text
    paths = list(client.app.state.settings.data_dir.rglob("*"))
    client.app.state.settings.attach_quota_mb = 0
    assert (
        await client.post(
            f"/api/tickets/{tid}/attachments", files={"file": ("note.txt", b"notes", "text/plain")}
        )
    ).status_code == 413
    assert (await client.post(f"/api/tickets/{tid}/cancel")).status_code == 200
    assert (await client.delete(f"/api/tickets/{tid}")).status_code == 200
    assert not any(p.is_file() for p in paths)


async def test_rotation_includes_encrypted_headers(engine_client, monkeypatch):
    client = engine_client
    settings = client.app.state.settings
    async with client.app.state.db_session() as db:
        agent = await db.scalar(select(Agent).where(Agent.handle == "@ba"))
        agent.api_key_enc = encrypt("arbitrary-private-key", settings)
        agent.api_params = {
            "extra_headers_enc": encrypt(json.dumps({"X-Private": "header-secret"}), settings)
        }
        aid = agent.id
        await db.commit()
    new_key = Fernet.generate_key().decode()
    monkeypatch.setenv("NEW_APP_SECRET_KEY", new_key)
    monkeypatch.setattr(rotate_key, "Settings", lambda: settings)
    await rotate_key.rotate()
    rotated = settings.model_copy(update={"app_secret_key": SecretStr(new_key)})
    async with client.app.state.db_session() as db:
        agent = await db.get(Agent, aid)
        assert decrypt(agent.api_key_enc, rotated) == "arbitrary-private-key"
        assert json.loads(decrypt(agent.api_params["extra_headers_enc"], rotated)) == {
            "X-Private": "header-secret"
        }


def test_backup_includes_wal(tmp_path):
    source, target = tmp_path / "source.db", tmp_path / "backup.db"
    with sqlite3.connect(source) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE example(value TEXT)")
        db.execute("INSERT INTO example VALUES ('saved')")
        db.commit()
        backup_sqlite(source, target)
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT value FROM example").fetchone()[0] == "saved"
