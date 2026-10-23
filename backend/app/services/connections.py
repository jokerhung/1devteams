import asyncio
import tempfile
import time
from collections import defaultdict, deque
from pathlib import Path

import httpx

from app.acp.client import ACPSession
from app.acp.types import AgentRuntimeConfig
from app.acp.url_policy import PinnedTransport, completion_url
from app.core.deps import fail
from app.services.agent_service import policy


class ConnectionLimiter:
    def __init__(self):
        self.calls: dict[str, deque] = defaultdict(deque)

    def check(self, user_id: str) -> None:
        now = time.monotonic()
        calls = self.calls[user_id]
        while calls and now - calls[0] >= 60:
            calls.popleft()
        if len(calls) >= 10:
            fail(429, "Tối đa 10 lần kiểm tra kết nối/phút", "rate_limited")
        calls.append(now)


async def test_api(body, settings, transport=None) -> dict:
    started = time.monotonic()
    status = None
    try:
        url_policy = policy(settings)
        await url_policy.validate(body.base_url)
        headers = {"Authorization": f"Bearer {body.api_key.get_secret_value()}"}
        for name, value in body.extra_headers.items():
            if name.lower() in {"host", "content-length", "transfer-encoding", "connection"}:
                raise ValueError("Unsafe header")
            headers[name] = value.get_secret_value()
        base = httpx.URL(body.base_url)
        models_url = base.copy_with(path=base.path.rstrip("/") + "/models")
        async with asyncio.timeout(30):
            async with httpx.AsyncClient(
                transport=transport or PinnedTransport(body.base_url, url_policy),
                timeout=10,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                async with client.stream("GET", models_url, headers=headers) as response:
                    status = response.status_code
                    payload = bytearray()
                    if status == 200:
                        async for chunk in response.aiter_bytes():
                            payload.extend(chunk)
                            if len(payload) > 1024 * 1024:
                                raise ValueError("Response too large")
                if status in {404, 405}:
                    async with client.stream(
                        "POST",
                        completion_url(body.base_url),
                        headers=headers,
                        json={
                            "model": body.model,
                            "messages": [{"role": "user", "content": "Hi"}],
                            "max_tokens": 1,
                            "stream": False,
                        },
                    ) as response:
                        status = response.status_code
                    models = []
                elif status == 200:
                    import json

                    data = json.loads(payload)
                    # Only return model ids. Never relay arbitrary provider fields or error bodies.
                    models = [{"id": str(item["id"])} for item in data.get("data", []) if "id" in item]
                    secrets = [
                        body.api_key.get_secret_value(),
                        *(v.get_secret_value() for v in body.extra_headers.values()),
                    ]
                    models = [
                        item
                        for item in models
                        if not any(secret and secret in item["id"] for secret in secrets)
                    ]
                    models = [{"id": item["id"][:100]} for item in models]
                else:
                    models = []
        return {
            "ok": status == 200,
            "status": status,
            "models": models,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "error": None if status == 200 else "Endpoint từ chối yêu cầu",
        }
    except Exception:
        return {
            "ok": False,
            "status": status,
            "latency_ms": int((time.monotonic() - started) * 1000),
            "error": "Không kết nối được endpoint hoặc URL không được phép",
        }


async def test_native(cfg: AgentRuntimeConfig, catalog) -> dict:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aiteams-connection-") as workspace:
        session = ACPSession(cfg, Path(workspace), diagnostic=True)
        try:
            async with asyncio.timeout(30):
                await session.start()
            catalog.observe(cfg.runtime, session.available_models)
            return {
                "ok": True,
                "runtime_version": session.runtime_version,
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        except Exception:
            return {
                "ok": False,
                "error": "Không khởi tạo được ACP; kiểm tra binary và đăng nhập CLI",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
        finally:
            await session.close()
