"""Small async event bus used to decouple data feeds, engines, and views."""

import asyncio
import inspect
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class Event:
    topic: str
    payload: Any
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


EventHandler = Callable[[Event], Awaitable[None] | None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, topic: str, handler: EventHandler) -> Callable[[], None]:
        self._handlers[topic].append(handler)

        def unsubscribe() -> None:
            if handler in self._handlers[topic]:
                self._handlers[topic].remove(handler)

        return unsubscribe

    async def publish(self, topic: str, payload: Any) -> None:
        event = Event(topic=topic, payload=payload)
        for handler in tuple(self._handlers[topic]):
            result = handler(event)
            if inspect.isawaitable(result):
                await result

    def publish_soon(self, topic: str, payload: Any) -> asyncio.Task[None]:
        return asyncio.create_task(self.publish(topic, payload))
