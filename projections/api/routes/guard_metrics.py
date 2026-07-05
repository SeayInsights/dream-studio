"""Guard metrics API route for LLM Guard dashboard surfacing."""

from typing import Any

from fastapi import APIRouter, Query

from core.config.database import get_connection
from projections.api.routes.sqlite_schema import object_exists

router = APIRouter()


@router.get("/metrics", summary="Guard activity metrics across all projects")
async def get_guard_metrics(
    project_id: str | None = Query(None, description="Filter by project"),
    limit: int = Query(10, ge=1, le=100),
) -> dict[str, Any]:
    """Guard activity metrics: findings by severity, memory skips, delta blocks, top rules."""
    # When called directly (e.g. in tests, outside FastAPI DI), limit may be a Query object
    if not isinstance(limit, int):
        limit = 10
    conn = get_connection()
    try:
        if not object_exists(conn, "guard_events"):
            return _guard_empty()

        where_clause = "WHERE project_id = ?" if project_id else ""
        params = [project_id] if project_id else []

        # Total findings by event_type and severity
        rows = conn.execute(
            f"""SELECT event_type, severity, COUNT(*) as cnt
                FROM guard_events
                {where_clause}
                GROUP BY event_type, severity""",
            params,
        ).fetchall()

        by_type: dict[str, dict] = {}
        for row in rows:
            et = row[0] or "unknown"
            sev = row[1] or "unknown"
            cnt = row[2]
            if et not in by_type:
                by_type[et] = {}
            by_type[et][sev] = cnt

        # Top firing rules
        rule_rows = conn.execute(
            f"""SELECT rule_id, COUNT(*) as cnt
                FROM guard_events
                WHERE rule_id IS NOT NULL {"AND project_id = ?" if project_id else ""}
                GROUP BY rule_id ORDER BY cnt DESC LIMIT ?""",
            ([project_id] if project_id else []) + [limit],
        ).fetchall()
        top_rules = [{"rule_id": r[0], "count": r[1]} for r in rule_rows]

        # Counts by action
        action_rows = conn.execute(
            f"""SELECT action, COUNT(*) as cnt FROM guard_events
                {where_clause} GROUP BY action""",
            params,
        ).fetchall()
        by_action = {r[0]: r[1] for r in action_rows}

        total = sum(by_action.values())

        return {
            "total_events": total,
            "by_action": by_action,
            "guard_findings_logged": by_action.get("logged", 0),
            "memory_skips": by_action.get("skipped", 0),
            "delta_blocks": by_type.get("delta_adjudication_blocked", {}).get("critical", 0),
            "by_severity": {
                "critical": sum(by_type.get(et, {}).get("critical", 0) for et in by_type),
                "high": sum(by_type.get(et, {}).get("high", 0) for et in by_type),
                "medium": sum(by_type.get(et, {}).get("medium", 0) for et in by_type),
            },
            "top_firing_rules": top_rules,
            "by_event_type": by_type,
            "source_status": {
                "classification": "fresh" if total > 0 else "empty",
                "derived_view": True,
                "primary_authority": False,
            },
        }
    finally:
        conn.close()


@router.get("/metrics/{project_id}", summary="Guard metrics for a specific project")
async def get_project_guard_metrics(project_id: str) -> dict[str, Any]:
    """Guard activity for a specific project."""
    return await get_guard_metrics(project_id=project_id)


def _guard_empty() -> dict[str, Any]:
    return {
        "total_events": 0,
        "by_action": {},
        "guard_findings_logged": 0,
        "memory_skips": 0,
        "delta_blocks": 0,
        "by_severity": {"critical": 0, "high": 0, "medium": 0},
        "top_firing_rules": [],
        "by_event_type": {},
        "source_status": {
            "classification": "empty by design",
            "reason": "guard_events table not found or no events recorded",
            "derived_view": True,
            "primary_authority": False,
        },
    }
