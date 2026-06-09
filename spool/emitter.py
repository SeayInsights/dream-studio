"""Convenience emit() function for hooks that write to the canonical event spool.

Hooks that need to emit a single event without constructing a full
CanonicalEventEnvelope should use this module. It wraps the spool_writer
pattern so callers never raise on failure — hooks must be non-blocking.

Usage:
    from spool.emitter import emit
    success = emit("ds_session_harvest", {"session_id": sid, "pct": 75.0})
"""

from __future__ import annotations

from typing import Any

from canonical.events.envelope import CanonicalEventEnvelope
from emitters.shared.spool_writer import write_envelopes


def emit(
    event_type: str,
    payload: dict[str, Any],
    session_id: str | None = None,
    severity: str = "info",
) -> bool:
    """Write a single canonical event to the spool.

    Returns True on success, False if the write fails for any reason.
    Never raises — callers (hooks) must not be interrupted by telemetry failures.
    """
    try:
        envelope = CanonicalEventEnvelope(
            event_type=event_type,
            session_id=session_id,
            payload=payload,
            severity=severity,
        )
        write_envelopes([envelope])
        return True
    except Exception:
        return False
