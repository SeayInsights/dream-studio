"""Typed event bus — pub/sub dispatch with handler contracts.

Replaces the sequential on-*-dispatch.py pattern with a decoupled bus.
Handlers subscribe to event topics. The bus dispatches in dependency order
with typed payloads and error isolation.

Usage:
    from core.dispatch.bus import EventBus, Handler, HandlerResult

    class MyHandler(Handler):
        topic = "prompt.submitted"
        def handle(self, payload: dict) -> HandlerResult:
            ...
            return HandlerResult(success=True)

    bus = EventBus()
    bus.subscribe(MyHandler())
    results = bus.publish("prompt.submitted", payload)
"""

import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


@dataclass
class HandlerResult:
    handler_name: str = ""
    success: bool = True
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    skipped: bool = False


class Handler(ABC):
    """Typed handler contract.

    Subclasses must define:
    - topic: event topic this handler subscribes to
    - handle(): process the event payload
    """

    @property
    @abstractmethod
    def topic(self) -> str: ...

    @property
    def name(self) -> str:
        return self.__class__.__name__

    @property
    def priority(self) -> int:
        """Lower = runs first. Default 100."""
        return 100

    @property
    def required(self) -> bool:
        """If True, failure stops subsequent handlers."""
        return False

    @abstractmethod
    def handle(self, payload: Dict[str, Any]) -> HandlerResult: ...

    def should_run(self, payload: Dict[str, Any]) -> bool:
        """Optional gate — return False to skip this handler."""
        return True


class EventBus:
    """Pub/sub event bus with error isolation and priority ordering."""

    def __init__(self) -> None:
        self._handlers: Dict[str, List[Handler]] = {}
        self._middleware: List[Callable] = []

    def subscribe(self, handler: Handler) -> None:
        topic = handler.topic
        if topic not in self._handlers:
            self._handlers[topic] = []
        self._handlers[topic].append(handler)
        self._handlers[topic].sort(key=lambda h: h.priority)
        logger.debug(f"Subscribed {handler.name} to {topic} (priority {handler.priority})")

    def unsubscribe(self, handler_name: str, topic: Optional[str] = None) -> None:
        topics = [topic] if topic else list(self._handlers.keys())
        for t in topics:
            if t in self._handlers:
                self._handlers[t] = [h for h in self._handlers[t] if h.name != handler_name]

    def publish(self, topic: str, payload: Dict[str, Any]) -> List[HandlerResult]:
        """Publish event to all subscribers. Returns results in execution order."""
        handlers = self._handlers.get(topic, [])
        if not handlers:
            logger.debug(f"No handlers for topic: {topic}")
            return []

        results: List[HandlerResult] = []
        for handler in handlers:
            if not handler.should_run(payload):
                results.append(HandlerResult(handler_name=handler.name, skipped=True))
                continue

            start = time.monotonic()
            try:
                result = handler.handle(payload)
                result.handler_name = handler.name
                result.duration_ms = (time.monotonic() - start) * 1000
                results.append(result)

                if not result.success and handler.required:
                    logger.error(
                        f"Required handler {handler.name} failed: {result.error}. "
                        f"Stopping dispatch for topic {topic}."
                    )
                    break

            except Exception as e:
                elapsed = (time.monotonic() - start) * 1000
                logger.error(f"Handler {handler.name} raised: {e}", exc_info=True)
                result = HandlerResult(
                    handler_name=handler.name,
                    success=False,
                    error=str(e),
                    duration_ms=elapsed,
                )
                results.append(result)

                if handler.required:
                    break

        return results

    def topics(self) -> List[str]:
        return list(self._handlers.keys())

    def handlers_for(self, topic: str) -> List[str]:
        return [h.name for h in self._handlers.get(topic, [])]

    def health(self) -> Dict[str, Any]:
        return {
            "topics": len(self._handlers),
            "total_handlers": sum(len(hs) for hs in self._handlers.values()),
            "by_topic": {t: [h.name for h in hs] for t, hs in self._handlers.items()},
        }
