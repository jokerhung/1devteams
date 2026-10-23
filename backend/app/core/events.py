"""In-process event bus. User and ticket websocket consumers can subscribe in later phases."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}

    async def publish(self, channel: str, event: dict[str, Any]) -> None:
        for queue in tuple(self._subscribers.get(channel, ())):
            await queue.put(event.copy())

    @asynccontextmanager
    async def subscribe(self, channel: str) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        subscribers = self._subscribers.setdefault(channel, set())
        subscribers.add(queue)
        try:
            yield queue
        finally:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(channel, None)
