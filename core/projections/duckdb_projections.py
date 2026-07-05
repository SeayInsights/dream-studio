"""DuckDB projection classes — mirror analytics events into DuckDB analytics store.

These are NOT subclasses of the SQLite Projection ABC. They receive the same
event dicts dispatched by ProjectionEngine._apply_v2() but write to DuckDB
tables via the analytics_conn (duckdb.DuckDBPyConnection).

INSERT OR REPLACE INTO provides idempotency by primary key. No source_event_id
tracking needed (unlike the SQLite projections).

Authority boundary: DuckDB tables are NEVER-AUTHORITY.
Business entity state (projects, milestones, work_orders, tasks, design_briefs)
stays in studio.db (Store 3 authority) — never in DuckDB.
"""

from __future__ import annotations

import logging
from datetime import datetime, UTC
from typing import Any

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


class DuckDBExecutionEventProjection:
    name = "duckdb_execution_event_projection"
    consumed_event_types = [
        "execution.started",
        "execution.completed",
        "execution.failed",
    ]

    def handle(self, event: dict[str, Any], conn: Any) -> int:
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event.get("event_timestamp") or _now()
        trace = event.get("trace") or {}
        payload = event.get("payload") or {}

        conn.execute(
            """INSERT OR REPLACE INTO duckdb_execution_events
               (event_id, event_type, event_name, project_id, milestone_id, task_id,
                session_id, skill_id, workflow_id, agent_id, hook_id, tool_id,
                model_id, adapter_id, outcome_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event_id,
                event_type,
                payload.get("event_name"),
                trace.get("project_id") or event.get("project_id"),
                trace.get("milestone_id"),
                trace.get("task_id"),
                event.get("session_id"),
                trace.get("skill_id"),
                trace.get("workflow_id"),
                trace.get("agent_id"),
                trace.get("hook_id"),
                trace.get("tool_id"),
                trace.get("model_id"),
                trace.get("adapter_id"),
                payload.get("outcome_status"),
                ts,
            ),
        )
        return 1


# ── Routing registry ──────────────────────────────────────────────────────────

_PROJECTIONS: list[Any] = [
    DuckDBExecutionEventProjection(),
]

_EVENT_TYPE_MAP: dict[str, list] = {}
for _p in _PROJECTIONS:
    for _et in _p.consumed_event_types:
        _EVENT_TYPE_MAP.setdefault(_et, []).append(_p)


def dispatch_to_duckdb(event: dict[str, Any], conn: Any) -> int:
    """Route one canonical event to all matching DuckDB projections.

    Fail-open: individual projection errors are logged, not propagated.
    Returns total rows written.
    """
    event_type = event.get("event_type", "")
    total = 0
    for handler in _EVENT_TYPE_MAP.get(event_type, []):
        try:
            total += handler.handle(event, conn)
        except Exception as exc:
            logger.warning(
                "DuckDB projection %s failed for %s (%s): %s",
                handler.name,
                event.get("event_id"),
                event_type,
                exc,
            )
    return total


def register_duckdb_projection(proj: Any) -> None:
    """Register an additional DuckDB projection."""
    _PROJECTIONS.append(proj)
    for et in getattr(proj, "consumed_event_types", []):
        _EVENT_TYPE_MAP.setdefault(et, []).append(proj)
