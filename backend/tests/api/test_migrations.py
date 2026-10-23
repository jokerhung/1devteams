from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect

from alembic import command
from app.core.config import BACKEND_ROOT
from app.db.base import Base
from app.db.session import database, migrate


async def test_sqlite_migration_roundtrip(tmp_path):
    import asyncio

    url = f"sqlite+aiosqlite:///{tmp_path / 'migration.db'}"
    await asyncio.to_thread(migrate, url)
    engine, _ = database(url)
    try:
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
            differences = await connection.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
            )
        assert set(Base.metadata.tables) <= set(tables)
        assert not differences
    finally:
        await engine.dispose()
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await asyncio.to_thread(command.upgrade, cfg, "head")


async def test_openapi_contract(client):
    response = await client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert len(schema["paths"]) >= 45
    assert schema["paths"]["/api/workflows/{wid}/tickets"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["schema"]["$ref"].endswith("TicketCreated")
    assert "api_key_enc" not in schema["components"]["schemas"]["AgentOut"]["properties"]
    for path, operations in schema["paths"].items():
        if path.startswith("/api/") and path not in {"/api/health", "/api/auth/login"}:
            for operation in operations.values():
                assert operation.get("security"), path


async def test_configured_database_schema_and_downgrade(client):
    import asyncio

    url = client.app.state.settings.database_url
    engine, _ = database(url)
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync), Base.metadata)
            )
        assert not differences
    finally:
        await engine.dispose()
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await asyncio.to_thread(command.upgrade, cfg, "head")
