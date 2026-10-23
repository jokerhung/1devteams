import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.acp.pool import ACPProcessPool  # noqa: E402
from app.core.config import Settings, get_settings, resolve_binary  # noqa: E402
from app.core.events import EventBus  # noqa: E402


class HealthResponse(BaseModel):
    status: str = "ok"
    acp: dict[str, bool]


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        bus = EventBus()
        pool = ACPProcessPool(
            event_bus=bus, max_acp=config.max_acp_processes, max_api=config.max_api_concurrency
        )
        app.state.event_bus, app.state.acp_pool = bus, pool
        try:
            yield
        finally:
            await pool.close_all()

    app = FastAPI(title="aiTeams", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.origins,
        allow_methods=["GET"],
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
