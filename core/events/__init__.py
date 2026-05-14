"""Event handling module for dream-studio.

Unified event system (2026-05-07):
- emitter: Event emission functions
- types: Event type constants
- canonical: Canonical event models (migrated from projections)
- models: Claude Code hook payload models
"""

from .emitter import emit_event
from .types import EventType
from .canonical import CanonicalEvent, ActivityLog, HookExecution, SecurityFinding

__all__ = [
    "emit_event",
    "EventType",
    "CanonicalEvent",
    "ActivityLog",
    "HookExecution",
    "SecurityFinding",
]
