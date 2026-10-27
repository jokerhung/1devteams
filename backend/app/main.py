import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial
from pathlib import Path
from typing import Any

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI  # noqa: E402
from fastapi.exceptions import RequestValidationError  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from starlette.exceptions import HTTPException  # noqa: E402

from app.acp.pool import ACPProcessPool, create_session  # noqa: E402
from app.acp.pty_manager import PTYManager  # noqa: E402
from app.api import (  # noqa: E402
    agent_chat,
    agents,
    assets,
    auth,
    notifications,
    operations,
    preferences,
    projects,
    realtime,
    teams,
    tickets,
    users,
    workflows,
    workspace_settings,
)
from app.core.config import Settings, get_settings, resolve_binary  # noqa: E402
from app.core.events import EventBus  # noqa: E402
from app.core.logging import configure_logging  # noqa: E402
from app.db.session import database, migrate  # noqa: E402
from app.engine.runner import TicketRunner  # noqa: E402
from app.schemas.common import ErrorResponse  # noqa: E402
from app.services.assets import cleanup_pending  # noqa: E402
from app.services.connections import ConnectionLimiter  # noqa: E402
from app.services.models_catalog import ModelsCatalog  # noqa: E402
from app.services.seed import seed  # noqa: E402
from app.services.workspace_settings import WorkspaceSettings  # noqa: E402
from app.ws.terminal_ws import router as terminal_router  # noqa: E402
from app.ws.ticket_ws import router as workflow_socket_router  # noqa: E402


class HealthResponse(BaseModel):
    status: str = "ok"
    acp: dict[str, bool]


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        configure_logging()
        app.state.workspace_settings = WorkspaceSettings(config)
        await app.state.workspace_settings.load()
        bus = EventBus()
        bus.settings = config
        pool = ACPProcessPool(
            event_bus=bus,
            max_acp=config.max_acp_processes,
            max_api=config.max_api_concurrency,
            factory=partial(create_session, settings=config),
        )
        app.state.event_bus, app.state.acp_pool = bus, pool
        engine, sessions = database(config.database_url)
        app.state.db_session = sessions
        terminal_manager = PTYManager(config, sessions)
        app.state.pty_manager = terminal_manager
        bus.sessions = sessions
        app.state.models_catalog = ModelsCatalog()
        app.state.connection_limiter = ConnectionLimiter()
        cleanup_task = None
        stack = AsyncExitStack()
        runner = None

        async def clean_attachments():
            while True:
                await asyncio.sleep(3600)
                async with sessions() as db:
                    await cleanup_pending(db, config)

        try:
            await asyncio.to_thread(migrate, config.database_url)
            from app.services.chat_history import backfill_chat_history

            async with sessions() as db:
                await backfill_chat_history(db)
            async with sessions() as db:
                await seed(db, config)
                await cleanup_pending(db, config)
            saver: Any
            if config.checkpoint_postgres_url:
                if sys.platform == "win32":
                    raise ValueError(
                        "CHECKPOINT_POSTGRES_URL requires Linux; Windows ACP needs ProactorEventLoop. "
                        "Use CHECKPOINT_DB (SQLite) on Windows."
                    )
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

                saver = await stack.enter_async_context(
                    AsyncPostgresSaver.from_conn_string(config.checkpoint_postgres_url.get_secret_value())
                )
                await saver.setup()
            else:
                from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

                from app.core.config import BACKEND_ROOT

                checkpoint = Path(config.checkpoint_db)
                if not checkpoint.is_absolute():
                    checkpoint = BACKEND_ROOT / checkpoint
                await asyncio.to_thread(checkpoint.parent.mkdir, parents=True, exist_ok=True)
                saver = await stack.enter_async_context(AsyncSqliteSaver.from_conn_string(str(checkpoint)))
                await saver.setup()
            runner = TicketRunner(sessions, pool, bus, config, saver)
            app.state.ticket_runner = runner
            await runner.recover()
            cleanup_task = asyncio.create_task(clean_attachments())
            yield
        finally:
            if runner:
                await runner.close()
            if cleanup_task:
                cleanup_task.cancel()
                await asyncio.gather(cleanup_task, return_exceptions=True)
            await pool.close_all()
            await terminal_manager.close()
            await stack.aclose()
            await engine.dispose()

    app = FastAPI(
        title="1Teams",
        version="0.3.0",
        lifespan=lifespan,
        responses={
            status: {"model": ErrorResponse} for status in [400, 401, 403, 404, 409, 413, 422, 429, 503]
        },
    )
    app.state.settings = config
    for router in [
        auth.router,
        users.router,
        agents.router,
        agent_chat.router,
        teams.router,
        projects.router,
        workflows.router,
        tickets.router,
        notifications.router,
        preferences.router,
        assets.router,
        operations.router,
        workspace_settings.router,
    ]:
        app.include_router(router, prefix="/api")
    app.include_router(realtime.router)
    app.include_router(workflow_socket_router)
    app.include_router(terminal_router)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        body = (
            error.detail
            if isinstance(error.detail, dict)
            else {"detail": str(error.detail), "code": "http_error"}
        )
        return JSONResponse(body, status_code=error.status_code, headers=error.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        # Pydantic errors contain raw input (including passwords/API keys). Do not reflect or log it.
        return JSONResponse(
            {
                "detail": "Dữ liệu không hợp lệ",
                "code": "validation_error",
                "fields": [".".join(map(str, item["loc"])) for item in error.errors()],
            },
            status_code=422,
        )

    @app.exception_handler(IntegrityError)
    async def integrity_error(request, error):
        return JSONResponse(
            {"detail": "Dữ liệu bị trùng hoặc đang được tham chiếu", "code": "conflict"}, status_code=409
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["*"],
    )

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            acp={
                "claude": resolve_binary(config.claude_acp_bin) is not None,
                "codex": resolve_binary(config.codex_acp_bin) is not None,
            }
        )

    return app


app = create_app()
