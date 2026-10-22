import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from fastapi import FastAPI  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from app.core.config import Settings, get_settings, resolve_binary  # noqa: E402


class HealthResponse(BaseModel):
    status: str = "ok"
    acp: dict[str, bool]


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    app = FastAPI(title="aiTeams", version="0.1.0")
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
