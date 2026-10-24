"""Offline credential rotation. Stop the app and back up first.

Set NEW_APP_SECRET_KEY in the process environment (never as a CLI argument).
On success update APP_SECRET_KEY in backend/.env before restarting.
"""

import asyncio
import os

from cryptography.fernet import Fernet
from sqlalchemy import select

from app.core.config import Settings
from app.core.security import decrypt
from app.db.models import Agent
from app.db.session import database


async def rotate() -> None:
    settings = Settings()
    new_key = Fernet(os.environ["NEW_APP_SECRET_KEY"].encode())
    engine, sessions = database(settings.database_url)
    try:
        async with sessions() as db, db.begin():
            agents = (await db.scalars(select(Agent))).all()
            # Decrypt all values before modifying anything; transaction rolls back on error.
            values = [
                (
                    row,
                    decrypt(row.api_key_enc, settings) if row.api_key_enc else None,
                    decrypt(row.api_params["extra_headers_enc"], settings)
                    if row.api_params.get("extra_headers_enc")
                    else None,
                )
                for row in agents
            ]
            for row, plaintext, headers in values:
                if plaintext is not None:
                    row.api_key_enc = new_key.encrypt(plaintext.encode()).decode()
                if headers is not None:
                    row.api_params = {
                        **row.api_params,
                        "extra_headers_enc": new_key.encrypt(headers.encode()).decode(),
                    }
        print(f"Rotated {len(values)} credentials. Update APP_SECRET_KEY before restarting.")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(rotate())
