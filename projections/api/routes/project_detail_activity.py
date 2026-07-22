"""Project activity timeline endpoint.

WO-GF-API-ROUTES: split out of project_detail.py.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Query

from projections.api.lib.project_helpers import get_db_connection, _empty_project_source_status
from projections.api.routes.sqlite_schema import object_exists

from .project_detail_router import router

logger = logging.getLogger(__name__)


@router.get("/{project_id}/activity")
async def get_project_activity(
    project_id: str, limit: int = Query(20, ge=1, le=100)
) -> dict[str, Any]:
    """
    Get recent activity timeline for a specific project.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if object_exists(conn, "execution_events"):
            rows = cursor.execute(
                """
                SELECT
                    event_type,
                    event_name,
                    created_at,
                    outcome_status
                FROM execution_events
                WHERE project_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
            activities = [
                {
                    "activity_type": row["event_type"],
                    "timestamp": row["created_at"],
                    "message": row["event_name"] or row["event_type"],
                    "status": row["outcome_status"],
                }
                for row in rows
            ]
            return {
                "project_id": project_id,
                "activities": activities,
                "count": len(activities),
                "source_status": {
                    "classification": "fresh",
                    "reason": "Project activity is read from current execution_events authority.",
                    "source_tables": ["execution_events"],
                    "derived_view": True,
                    "primary_authority": False,
                },
            }

        if object_exists(conn, "process_runs"):
            rows = cursor.execute(
                """
                SELECT
                    run_type,
                    started_at,
                    status,
                    summary
                FROM process_runs
                WHERE project_id = ?
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
            activities = [
                {
                    "activity_type": row["run_type"],
                    "timestamp": row["started_at"],
                    "message": row["summary"] or row["run_type"],
                    "status": row["status"],
                }
                for row in rows
            ]
            return {
                "project_id": project_id,
                "activities": activities,
                "count": len(activities),
                "source_status": {
                    "classification": "fresh",
                    "reason": "Project activity is read from current process_runs authority.",
                    "source_tables": ["process_runs"],
                    "derived_view": True,
                    "primary_authority": False,
                },
            }

        if not object_exists(conn, "pi_analysis_runs"):
            return {
                "project_id": project_id,
                "activities": [],
                "count": 0,
                "source_status": _empty_project_source_status(
                    ["pi_analysis_runs"],
                    reason="Project activity analysis-run table is not present in this DB snapshot.",
                ),
            }

        # Get analysis runs
        runs_query = """
        SELECT
            'analysis_run' as activity_type,
            started_at as timestamp,
            'Completed ' || run_type || ' analysis - Found ' ||
            violations_found || ' violations, ' || bugs_found || ' bugs' as message
        FROM pi_analysis_runs
        WHERE project_id = ? AND status = 'completed'
        ORDER BY started_at DESC
        LIMIT ?
        """

        rows = cursor.execute(runs_query, (project_id, limit)).fetchall()
        activities = [dict(row) for row in rows]

        return {"project_id": project_id, "activities": activities, "count": len(activities)}

    except Exception as e:
        logger.error(f"Error getting project activity: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
