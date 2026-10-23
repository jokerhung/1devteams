from alembic.config import Config
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from alembic import command
from app.core.config import BACKEND_ROOT


def normalize_url(url: str) -> str:
    if url.startswith("sqlite+aiosqlite:///./"):
        return "sqlite+aiosqlite:///" + str(BACKEND_ROOT / url.split("///./", 1)[1]).replace("\\", "/")
    return url


def database(url: str):
    engine = create_async_engine(normalize_url(url), pool_pre_ping=True, hide_parameters=True)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine.sync_engine, "connect")
        def sqlite_setup(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=10000")
            cursor.close()

    return engine, async_sessionmaker(engine, expire_on_commit=False)


def migrate(url: str) -> None:
    cfg = Config(str(BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", normalize_url(url).replace("%", "%%"))
    command.upgrade(cfg, "head")
