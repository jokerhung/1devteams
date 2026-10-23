import os
import subprocess
import sys
from uuid import uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def workspace(tmp_path):
    folder = tmp_path / "workspace"
    folder.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(folder)], check=True, capture_output=True)
    return folder


@pytest.fixture
async def client(tmp_path, workspace):
    admin_engine = None
    database_name = None
    checkpoint_url = None
    url = f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"
    if os.environ.get("AITEAMS_TEST_POSTGRES_URL"):
        source = make_url(os.environ["AITEAMS_TEST_POSTGRES_URL"])
        admin_engine = create_async_engine(source, isolation_level="AUTOCOMMIT")
        database_name = "aiteams_test_" + uuid4().hex
        async with admin_engine.connect() as connection:
            await connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
            await connection.exec_driver_sql(f'CREATE DATABASE "{database_name}_cp"')
        url = source.set(database=database_name).render_as_string(hide_password=False)
        if sys.platform != "win32":
            checkpoint_url = source.set(
                drivername="postgresql", database=database_name + "_cp"
            ).render_as_string(hide_password=False)
    settings = Settings(
        jwt_secret="api-test-secret",
        database_url=url,
        checkpoint_db=str(tmp_path / "checkpoints.db"),
        checkpoint_postgres_url=checkpoint_url,
        data_dir=tmp_path / "data",
        allowed_workspace_roots=str(tmp_path),
        app_secret_key=Fernet.generate_key().decode(),
        bootstrap_admin_email="owner@example.com",
        bootstrap_admin_password="OwnerPassword123!",
        cors_origins="http://localhost:3060",
        api_allowed_http_hosts="localhost,127.0.0.1",
        api_allowed_private_hosts="localhost,127.0.0.1",
    )
    app = create_app(settings)
    try:
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as api:
                login = await api.post(
                    "/api/auth/login", json={"email": "owner@example.com", "password": "OwnerPassword123!"}
                )
                assert login.status_code == 200, login.text
                api.headers["Authorization"] = "Bearer " + login.json()["access_token"]
                api.app = app
                api.owner = login.json()["user"]
                api.workspace = workspace
                yield api
    finally:
        if admin_engine:
            async with admin_engine.connect() as connection:
                await connection.exec_driver_sql(f'DROP DATABASE "{database_name}" WITH (FORCE)')
                await connection.exec_driver_sql(f'DROP DATABASE "{database_name}_cp" WITH (FORCE)')
            await admin_engine.dispose()


async def project(client, name="Project", seeded=False):
    response = await client.post(
        "/api/projects",
        json={"name": name, "workspace_path": str(client.workspace), "default_branch": "main"},
    )
    assert response.status_code == 201, response.text
    entity = response.json()
    if seeded:
        seed = await client.post(f"/api/projects/{entity['id']}/seed-default")
        assert seed.status_code == 200, seed.text
        entity["workflow"] = seed.json()["workflow"]
    return entity


async def ticket(client):
    entity = await project(client, seeded=True)
    result = await client.post(
        f"/api/workflows/{entity['workflow']['id']}/tickets",
        json={"title": "Đơ nút Xuất Excel báo cáo", "description": "Details", "auto_start": False},
    )
    assert result.status_code == 201, result.text
    return result.json()["ticket"]
