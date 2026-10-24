"""Explicit overload classification; configuration errors never retry."""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any


class RuntimeFailure(RuntimeError):
    def __init__(self, message: str, metadata: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.metadata = metadata or {}


def overloaded(error: RuntimeFailure, patterns: str) -> bool:
    status = error.metadata.get("status_code")
    if status in {401, 403, 404}:
        return False
    if status in {429, 529}:
        return True
    return any(p.strip().lower() in str(error).lower() for p in patterns.split(",") if p.strip())


def retry_after(value: Any) -> float:
    if not value:
        return 0
    try:
        seconds = float(value)
        return max(0, seconds) if math.isfinite(seconds) else 0
    except (TypeError, ValueError):
        try:
            return max(0, (parsedate_to_datetime(str(value)) - datetime.now(UTC)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 0


async def wait_for_retry(seconds: float) -> None:
    await asyncio.sleep(seconds)
