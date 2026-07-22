from __future__ import annotations

from dataclasses import dataclass

from .types_enum import EventCategory, EventType


@dataclass(frozen=True)
class EventTypeMeta:
    event_type: EventType
    domain: str
    description: str
    emitter_implemented: bool
    category: EventCategory
