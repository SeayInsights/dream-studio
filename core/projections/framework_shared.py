"""Shared dataclasses, literals, and logger for the projection framework.

WO-GF-PROJECTION-ENGINE: split from ``core/projections/framework.py``. The logger
name is hardcoded (not ``__name__``) because tests assert on the exact dotted
logger name ``core.projections.framework`` via ``caplog.at_level(...,
logger="core.projections.framework")`` — every sibling that logs imports this
same logger object rather than creating its own.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC
from typing import Literal

logger = logging.getLogger("core.projections.framework")

# ── Canonical source literals ─────────────────────────────────────────────────

CanonicalSource = Literal["business", "ai", "both"]

_TABLE_FOR_SOURCE: dict[str, str] = {
    "business": "business_canonical_events",
    "ai": "ai_canonical_events",
}


# ── RetryPolicy ───────────────────────────────────────────────────────────────


@dataclass
class RetryPolicy:
    """Exponential backoff retry configuration for a projection.

    Default schedule: 1 s → 2 s → 4 s (3 retries, then dead-letter).
    Override per projection class to tune for expected failure profiles.
    """

    max_retries: int = 3
    base_delay_seconds: float = 1.0
    backoff_factor: float = 2.0  # delay = base * backoff_factor^attempt

    def delay_for(self, attempt: int) -> float:
        """Return delay in seconds for the given attempt number (0-indexed)."""
        return self.base_delay_seconds * (self.backoff_factor**attempt)

    def next_retry_at(self, attempt: int) -> str:
        """Return ISO-format UTC timestamp for the next retry."""
        delay = self.delay_for(attempt)
        ts = datetime.now(UTC) + timedelta(seconds=delay)
        return ts.isoformat()


# ── Backward-compat dataclasses ───────────────────────────────────────────────


@dataclass
class ProjectionCheckpoint:
    """Legacy checkpoint record — kept for backward compat with pre-v2 code."""

    projection_name: str
    last_event_id: str
    last_timestamp: str
    events_processed: int
    last_rebuilt: str


@dataclass
class ProjectionResult:
    """Summary of a single projection run (batch of events)."""

    projection_name: str
    events_processed: int
    rows_written: int
    errors: list[str] = field(default_factory=list)
    duration_ms: float = 0.0
