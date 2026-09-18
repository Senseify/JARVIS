"""Asynchronous in-process event bus with persistence integration."""

import asyncio
import logging
from typing import Callable, Coroutine, Optional, Set

from core.models.events import AgentEvent
from core.persistence.database import Database

logger = logging.getLogger(__name__)

EventCallback = Callable[[AgentEvent], Coroutine[None, None, None]]


class EventBus:
    """Pub/Sub event bus for internal event distribution and persistence."""

    def __init__(self, database: Optional[Database] = None):
        self.database = database
        self._subscribers: Set[EventCallback] = set()
        self._lock = asyncio.Lock()

    def subscribe(self, callback: EventCallback) -> None:
        """Register an async callback for incoming events."""
        self._subscribers.add(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        """Remove a previously registered callback."""
        self._subscribers.discard(callback)

    async def publish(self, event: AgentEvent) -> None:
        """Publish an event to all subscribers and persist to database if available."""
        # 1. Persist event
        if self.database is not None:
            try:
                await self.database.save_event(event)
            except Exception as e:
                logger.error(f"Failed to persist event {event.id}: {e}")

        # 2. Dispatch to subscribers concurrently
        if not self._subscribers:
            return

        tasks = []
        for callback in list(self._subscribers):
            tasks.append(self._safe_dispatch(callback, event))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _safe_dispatch(self, callback: EventCallback, event: AgentEvent) -> None:
        try:
            await callback(event)
        except Exception as e:
            logger.warning(f"Error dispatching event to subscriber: {e}")
