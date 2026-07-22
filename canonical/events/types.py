"""Event taxonomy facade — re-exports the split modules.

WO-GF-EVENT-TAXONOMY-SPLIT: implementation moved to types_{enum,meta,
registry_core,registry_extensions}.py; this module re-exports the public
surface so existing `from canonical.events.types import X` callers are
unchanged.
"""

from __future__ import annotations

from .types_enum import EventCategory, EventType
from .types_meta import EventTypeMeta
from .types_registry_extensions import (
    ALL_EVENT_TYPES,
    EMITTER_IMPLEMENTED,
    EVENT_TYPE_REGISTRY,
)

__all__ = [
    "ALL_EVENT_TYPES",
    "EMITTER_IMPLEMENTED",
    "EVENT_TYPE_REGISTRY",
    "EventCategory",
    "EventType",
    "EventTypeMeta",
]
