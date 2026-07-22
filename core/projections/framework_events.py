"""Row/event conversion helpers for the projection framework.

WO-GF-PROJECTION-ENGINE: split from ``core/projections/framework.py``.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Any


def _build_type_filter(event_types: list[str]) -> tuple[str, list]:
    """Build a SQL WHERE clause fragment for event type matching.

    Returns (clause, params) where clause is something like:
        "(event_type LIKE ? OR event_type = ? OR event_type LIKE ?)"
    and params are the corresponding values.
    """
    clauses = []
    params: list = []
    for et in event_types:
        if "%" in et:
            clauses.append("event_type LIKE ?")
        else:
            clauses.append("event_type = ?")
        params.append(et)
    return "(" + " OR ".join(clauses) + ")", params


# ── Row → event dict conversion ───────────────────────────────────────────────


def _row_to_event(row: sqlite3.Row, source: str) -> dict[str, Any]:
    """Convert a sqlite3.Row from a canonical table to a normalized event dict.

    Works with both business_canonical_events and ai_canonical_events.
    The _source key indicates which canonical the event came from.
    """
    event: dict[str, Any] = {
        "event_id": row["event_id"],
        "event_type": row["event_type"],
        "event_timestamp": row["event_timestamp"],
        "trace": _parse_json(row["trace"]),
        "payload": _parse_json(row["payload"]),
        "correlation_id": row["correlation_id"] if "correlation_id" in row.keys() else None,
        "_source": source,
    }
    # Denormalized SDLC context — present on business_canonical_events.
    for col in ("project_id", "milestone_id", "work_order_id", "task_id"):
        if col in row.keys():
            event[col] = row[col]
    # Denormalized AI execution context — present on ai_canonical_events.
    for col in ("session_id", "skill_id", "workflow_id", "agent_id", "hook_id", "model_id"):
        if col in row.keys():
            event[col] = row[col]
    return event


def _parse_json(value: Any) -> Any:
    """Parse JSON string to dict/list, or return value as-is if already parsed."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value or {}


# ── Legacy canonical_events row format ────────────────────────────────────────


def _legacy_row_to_event(row: Any) -> dict[str, Any]:
    """Convert a row from the legacy canonical_events table to an event dict.

    Preserved exactly as in pre-v2 for consumers.py backward compat.
    The _source key is set to "legacy" to distinguish from v2 events.
    """

    def _get(row: Any, idx: int, key: str) -> Any:
        return row[idx] if isinstance(row, tuple) else row[key]

    event: dict[str, Any] = {
        "event_id": _get(row, 0, "event_id"),
        "event_type": _get(row, 1, "event_type"),
        "timestamp": _get(row, 2, "timestamp"),
        "trace": _parse_json(_get(row, 3, "trace")),
        "severity": _get(row, 4, "severity"),
        "payload": _parse_json(_get(row, 5, "payload")),
        "_source": "legacy",
    }
    actor = _get(row, 6, "actor") if len(row) > 6 else None
    if actor:
        event["actor"] = _parse_json(actor) if isinstance(actor, str) else actor
    cs = _get(row, 7, "confidence_score") if len(row) > 7 else None
    if cs is not None:
        event["confidence_score"] = cs
    st = _get(row, 8, "source_type") if len(row) > 8 else None
    if st:
        event["source_type"] = st
    return event
