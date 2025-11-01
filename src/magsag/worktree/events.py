"""Event bus utilities for Git worktree lifecycle notifications."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any, AsyncIterator


@dataclass(slots=True)
class WorktreeEvent:
    """Structured event emitted for worktree lifecycle changes."""

    name: str
    payload: dict[str, Any]
    timestamp: float


class WorktreeEventBus:
    """Lightweight pub/sub bus for worktree events."""

    def __init__(self) -> None:
        self._subscribers: set[tuple[asyncio.AbstractEventLoop, asyncio.Queue[WorktreeEvent]]] = set()
        self._lock = Lock()

    async def register(self) -> asyncio.Queue[WorktreeEvent]:
        """Register a new subscriber queue."""
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[WorktreeEvent] = asyncio.Queue()
        with self._lock:
            self._subscribers.add((loop, queue))
        return queue

    async def unregister(self, queue: asyncio.Queue[WorktreeEvent]) -> None:
        """Remove a subscriber queue."""
        with self._lock:
            self._subscribers = {item for item in self._subscribers if item[1] is not queue}

    def publish(self, event: WorktreeEvent) -> None:
        """Broadcast an event to all subscribers."""
        with self._lock:
            targets = list(self._subscribers)
        for loop, queue in targets:
            loop.call_soon_threadsafe(queue.put_nowait, event)

    async def iterate(self) -> AsyncIterator[WorktreeEvent]:
        """Yield events for the lifetime of the subscription."""
        queue = await self.register()
        try:
            while True:
                yield await queue.get()
        finally:
            await self.unregister(queue)


_BUS = WorktreeEventBus()


def get_event_bus() -> WorktreeEventBus:
    """Return the singleton worktree event bus."""
    return _BUS


def publish_event(name: str, payload: dict[str, Any]) -> None:
    """Publish an event, handling both sync and async callers."""
    event = WorktreeEvent(name=name, payload=payload, timestamp=time.time())
    get_event_bus().publish(event)
