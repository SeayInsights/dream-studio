"""Event handling module for dream-studio.

Unified event system (2026-05-07):
- types: Event type constants
- canonical: Canonical event models (migrated from projections)
- models: Claude Code hook payload models

Slice 3 (2026-05-16): emit_event() removed; use emitters.shared.spool_writer.write_envelopes()
with a canonical.events.envelope.CanonicalEventEnvelope instead.
"""

from .types import EventType
from .canonical import CanonicalEvent, ActivityLog, HookExecution, SecurityFinding

__all__ = [
    "EventType",
    "CanonicalEvent",
    "ActivityLog",
    "HookExecution",
    "SecurityFinding",
]
