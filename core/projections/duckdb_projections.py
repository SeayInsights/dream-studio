"""DuckDB projection classes — mirror business_* events into DuckDB analytics store.

These are NOT subclasses of the SQLite Projection ABC. They receive the same
event dicts dispatched by ProjectionEngine._apply_v2() but write to DuckDB
tables via the analytics_conn (duckdb.DuckDBPyConnection).

INSERT OR REPLACE INTO provides idempotency by primary key. No source_event_id
tracking needed (unlike the SQLite projections).

Authority boundary: DuckDB tables are NEVER-AUTHORITY.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DuckDBMilestoneProjection:
    name = "duckdb_milestone_projection"
    consumed_event_types = [
        "milestone.created",
        "milestone.completed",
        "milestone.deleted",
    ]

    def handle(self, event: Dict[str, Any], conn: Any) -> int:
        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event.get("event_timestamp") or _now()
        now = _now()

        milestone_id = event.get("milestone_id") or (event.get("trace") or {}).get("milestone_id")
        if not milestone_id:
            return 0

        project_id = event.get("project_id") or (event.get("trace") or {}).get("project_id")

        if event_type == "milestone.created":
            conn.execute(
                """INSERT OR REPLACE INTO duckdb_milestones
                   (milestone_id, project_id, title, description, status,
                    order_index, due_date, created_at, updated_at, last_event_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    milestone_id, project_id,
                    payload.get("title") or "(pending)",
                    payload.get("description"),
                    payload.get("status") or "pending",
                    payload.get("order_index") or 0,
                    payload.get("due_date"),
                    ts, now, event_id,
                ),
            )
        elif event_type == "milestone.completed":
            conn.execute(
                "UPDATE duckdb_milestones SET status='complete', updated_at=?, last_event_id=?"
                " WHERE milestone_id=?",
                (now, event_id, milestone_id),
            )
        elif event_type == "milestone.deleted":
            conn.execute(
                "UPDATE duckdb_milestones SET status='deleted', updated_at=?, last_event_id=?"
                " WHERE milestone_id=?",
                (now, event_id, milestone_id),
            )
        return 1


class DuckDBProjectProjection:
    name = "duckdb_project_projection"
    consumed_event_types = [
        "project.created",
        "project.activated",
        "project.deactivated",
        "project.deleted",
    ]

    def handle(self, event: Dict[str, Any], conn: Any) -> int:
        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event.get("event_timestamp") or _now()
        now = _now()

        project_id = (
            event.get("project_id")
            or (event.get("trace") or {}).get("project_id")
            or payload.get("project_id")
        )
        if not project_id:
            return 0

        if event_type == "project.created":
            conn.execute(
                """INSERT OR REPLACE INTO duckdb_projects
                   (project_id, name, description, status, project_path,
                    detected_stack, vision_statement, created_at, updated_at, last_event_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    project_id,
                    payload.get("name") or "(pending)",
                    payload.get("description"),
                    "active",
                    payload.get("project_path"),
                    payload.get("detected_stack"),
                    payload.get("vision_statement"),
                    ts, now, event_id,
                ),
            )
        else:
            status_map = {
                "project.activated": "active",
                "project.deactivated": "paused",
                "project.deleted": "deleted",
            }
            new_status = status_map.get(event_type)
            if new_status:
                conn.execute(
                    "UPDATE duckdb_projects SET status=?, updated_at=?, last_event_id=?"
                    " WHERE project_id=?",
                    (new_status, now, event_id, project_id),
                )
        return 1


# ── Routing registry ──────────────────────────────────────────────────────────

_PROJECTIONS: List[Any] = [
    DuckDBMilestoneProjection(),
    DuckDBProjectProjection(),
]

_EVENT_TYPE_MAP: Dict[str, list] = {}
for _p in _PROJECTIONS:
    for _et in _p.consumed_event_types:
        _EVENT_TYPE_MAP.setdefault(_et, []).append(_p)


def dispatch_to_duckdb(event: Dict[str, Any], conn: Any) -> int:
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
                handler.name, event.get("event_id"), event_type, exc,
            )
    return total


def register_duckdb_projection(proj: Any) -> None:
    """Register an additional DuckDB projection (used by Tasks 3+4)."""
    _PROJECTIONS.append(proj)
    for et in getattr(proj, "consumed_event_types", []):
        _EVENT_TYPE_MAP.setdefault(et, []).append(proj)
