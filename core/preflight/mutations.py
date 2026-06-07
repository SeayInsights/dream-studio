"""Preflight findings layer — emit-only mutations (AD-6).

create_preflight() and set_preflight_status() write to the preflight_events
spine only.  They never write to business_work_order_preflights — that is
PreflightProjection's job.

Valid finding_type values:  blast_radius | impact | risk | spec_reference | dependency
Valid severity values:      critical | high | medium | low | info
Valid status values (for status_changed events):
    open | acknowledged | mitigated | accepted_risk | resolved
"""

from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

_FINDING_TYPES = frozenset({"blast_radius", "impact", "risk", "spec_reference", "dependency"})
_SEVERITIES = frozenset({"critical", "high", "medium", "low", "info"})
_STATUSES = frozenset({"open", "acknowledged", "mitigated", "accepted_risk", "resolved"})


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _get_conn(db_path: Optional[Path]) -> tuple[sqlite3.Connection, bool]:
    """Return (conn, owned) where owned=True means we created the connection."""
    if db_path is not None:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        return conn, True
    try:
        from core.config.database import get_connection

        return get_connection(), False
    except Exception:
        from core.event_store.studio_db import _connect as _studio_connect
        from core.config.paths import state_dir

        conn = _studio_connect(state_dir() / "studio.db")
        return conn, True


def create_preflight(
    *,
    work_order_id: str,
    finding_type: str,
    source: str,
    severity: str,
    summary: str,
    body: Optional[str] = None,
    author_type: str = "system",
    correlation_id: Optional[str] = None,
    parent_event_id: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> str:
    """Emit a preflight.created event to the preflight_events spine.

    Returns the new event_id.
    Raises ValueError for invalid finding_type or severity.
    """
    if finding_type not in _FINDING_TYPES:
        raise ValueError(f"Invalid finding_type {finding_type!r}; valid: {sorted(_FINDING_TYPES)}")
    if severity not in _SEVERITIES:
        raise ValueError(f"Invalid severity {severity!r}; valid: {sorted(_SEVERITIES)}")

    event_id = str(uuid.uuid4())
    ts = _now()

    conn, owned = _get_conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO preflight_events (
                event_id, parent_event_id, work_order_id, correlation_id,
                event_kind, finding_type, source, severity, summary, body,
                author_type, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                parent_event_id,
                work_order_id,
                correlation_id,
                "preflight.created",
                finding_type,
                source,
                severity,
                summary,
                body,
                author_type,
                "open",
                ts,
            ),
        )
        conn.commit()
    finally:
        if owned:
            conn.close()

    return event_id


def set_preflight_status(
    *,
    finding_event_id: str,
    work_order_id: str,
    new_status: str,
    source: Optional[str] = None,
    author_type: str = "system",
    db_path: Optional[Path] = None,
) -> str:
    """Emit a preflight.status_changed event to the preflight_events spine.

    finding_event_id: the event_id of the original preflight.created event.
    Returns the new status-change event_id.
    Raises ValueError for invalid status.
    """
    if new_status not in _STATUSES:
        raise ValueError(f"Invalid status {new_status!r}; valid: {sorted(_STATUSES)}")

    event_id = str(uuid.uuid4())
    ts = _now()

    conn, owned = _get_conn(db_path)
    try:
        conn.execute(
            """
            INSERT INTO preflight_events (
                event_id, parent_event_id, work_order_id,
                event_kind, source, author_type, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                finding_event_id,
                work_order_id,
                "preflight.status_changed",
                source,
                author_type,
                new_status,
                ts,
            ),
        )
        conn.commit()
    finally:
        if owned:
            conn.close()

    return event_id
