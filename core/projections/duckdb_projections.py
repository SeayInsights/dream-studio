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
                    milestone_id,
                    project_id,
                    payload.get("title") or "(pending)",
                    payload.get("description"),
                    payload.get("status") or "pending",
                    payload.get("order_index") or 0,
                    payload.get("due_date"),
                    ts,
                    now,
                    event_id,
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
                    ts,
                    now,
                    event_id,
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
                handler.name,
                event.get("event_id"),
                event_type,
                exc,
            )
    return total


def register_duckdb_projection(proj: Any) -> None:
    """Register an additional DuckDB projection (used by Tasks 3+4)."""
    _PROJECTIONS.append(proj)
    for et in getattr(proj, "consumed_event_types", []):
        _EVENT_TYPE_MAP.setdefault(et, []).append(proj)


class DuckDBWorkOrderProjection:
    name = "duckdb_work_order_projection"
    consumed_event_types = [
        "work_order.created",
        "work_order.started",
        "work_order.closed",
        "work_order.deleted",
    ]

    def handle(self, event: Dict[str, Any], conn: Any) -> int:
        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event.get("event_timestamp") or _now()
        now = _now()

        work_order_id = (
            event.get("work_order_id")
            or (event.get("trace") or {}).get("work_order_id")
            or payload.get("work_order_id")
        )
        if not work_order_id:
            return 0

        project_id = event.get("project_id") or (event.get("trace") or {}).get("project_id")
        milestone_id = event.get("milestone_id") or (event.get("trace") or {}).get("milestone_id")

        if event_type == "work_order.created":
            conn.execute(
                """INSERT OR REPLACE INTO duckdb_work_orders
                   (work_order_id, project_id, milestone_id, title, description,
                    work_order_type, status, sequence_order, created_at, updated_at, last_event_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    work_order_id,
                    project_id,
                    milestone_id,
                    payload.get("title"),
                    payload.get("description"),
                    payload.get("work_order_type"),
                    "created",
                    payload.get("sequence_order"),
                    ts,
                    now,
                    event_id,
                ),
            )
        elif event_type == "work_order.started":
            conn.execute(
                "UPDATE duckdb_work_orders SET status='active', started_at=?,"
                " updated_at=?, last_event_id=? WHERE work_order_id=?",
                (ts, now, event_id, work_order_id),
            )
        elif event_type == "work_order.closed":
            conn.execute(
                "UPDATE duckdb_work_orders SET status='closed', closed_at=?,"
                " updated_at=?, last_event_id=? WHERE work_order_id=?",
                (ts, now, event_id, work_order_id),
            )
        elif event_type == "work_order.deleted":
            conn.execute(
                "UPDATE duckdb_work_orders SET status='deleted', updated_at=?, last_event_id=?"
                " WHERE work_order_id=?",
                (now, event_id, work_order_id),
            )
        return 1


class DuckDBTaskProjection:
    name = "duckdb_task_projection"
    consumed_event_types = [
        "task.created",
        "task.done",
        "task.deleted",
    ]

    def handle(self, event: Dict[str, Any], conn: Any) -> int:
        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event.get("event_timestamp") or _now()
        now = _now()

        task_id = (
            event.get("task_id")
            or (event.get("trace") or {}).get("task_id")
            or payload.get("task_id")
        )
        if not task_id:
            return 0

        work_order_id = (
            event.get("work_order_id")
            or (event.get("trace") or {}).get("work_order_id")
            or payload.get("work_order_id")
            or ""
        )
        project_id = (
            event.get("project_id")
            or (event.get("trace") or {}).get("project_id")
            or payload.get("project_id")
            or ""
        )

        if event_type == "task.created":
            conn.execute(
                """INSERT OR REPLACE INTO duckdb_tasks
                   (task_id, work_order_id, project_id, title, description,
                    status, created_at, updated_at, last_event_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    task_id,
                    work_order_id,
                    project_id,
                    payload.get("title") or "(pending)",
                    payload.get("description"),
                    "pending",
                    ts,
                    now,
                    event_id,
                ),
            )
        elif event_type == "task.done":
            conn.execute(
                "UPDATE duckdb_tasks SET status='complete', updated_at=?, last_event_id=?"
                " WHERE task_id=?",
                (now, event_id, task_id),
            )
        elif event_type == "task.deleted":
            conn.execute(
                "UPDATE duckdb_tasks SET status='deleted', updated_at=?, last_event_id=?"
                " WHERE task_id=?",
                (now, event_id, task_id),
            )
        return 1


# Register Task 3 projections into the routing table
for _p3 in [DuckDBWorkOrderProjection(), DuckDBTaskProjection()]:
    register_duckdb_projection(_p3)


class DuckDBDesignBriefProjection:
    name = "duckdb_design_brief_projection"
    consumed_event_types = [
        "design_brief.created",
        "design_brief.updated",
        "design_brief.locked",
    ]

    _UPDATABLE = frozenset(
        ["purpose", "audience", "tone", "design_system", "font_pairing", "brand_tokens"]
    )

    def handle(self, event: Dict[str, Any], conn: Any) -> int:
        payload = event.get("payload") or {}
        event_type = event["event_type"]
        event_id = event["event_id"]
        ts = event.get("event_timestamp") or _now()
        now = _now()

        brief_id = (
            event.get("brief_id")
            or (event.get("trace") or {}).get("brief_id")
            or payload.get("brief_id")
        )
        project_id = (
            event.get("project_id")
            or (event.get("trace") or {}).get("project_id")
            or payload.get("project_id")
            or ""
        )

        if not brief_id:
            return 0

        if event_type == "design_brief.created":
            conn.execute(
                """INSERT OR REPLACE INTO duckdb_design_briefs
                   (brief_id, project_id, status, purpose, audience, tone,
                    design_system, font_pairing, brand_tokens, created_at, updated_at, last_event_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    brief_id,
                    project_id,
                    "draft",
                    payload.get("purpose"),
                    payload.get("audience"),
                    payload.get("tone"),
                    payload.get("design_system"),
                    payload.get("font_pairing"),
                    payload.get("brand_tokens"),
                    ts,
                    now,
                    event_id,
                ),
            )
        elif event_type == "design_brief.updated":
            field = payload.get("field")
            value = payload.get("value")
            if field and field in self._UPDATABLE:
                conn.execute(
                    f"UPDATE duckdb_design_briefs SET {field}=?, updated_at=?, last_event_id=?"  # noqa: S608
                    " WHERE brief_id=?",
                    (value, now, event_id, brief_id),
                )
        elif event_type == "design_brief.locked":
            conn.execute(
                "UPDATE duckdb_design_briefs SET status='locked', updated_at=?, last_event_id=?"
                " WHERE brief_id=?",
                (now, event_id, brief_id),
            )
        return 1


# Register Task 4 projection
register_duckdb_projection(DuckDBDesignBriefProjection())


class DuckDBExecutionEventProjection:
    name = "duckdb_execution_event_projection"
    consumed_event_types = [
        "execution.started",
        "execution.completed",
        "execution.failed",
    ]

    def handle(self, event: Dict[str, Any], conn: Any) -> int:
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


# Register Task 7 projection
register_duckdb_projection(DuckDBExecutionEventProjection())
