"""Project analysis-run history endpoints.

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


@router.get("/{project_id}/history")
async def get_project_history(
    project_id: str, limit: int = Query(20, ge=1, le=100)
) -> dict[str, Any]:
    """
    Get analysis run history for a project.

    Returns recent analysis runs with health score trends.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "pi_analysis_runs"):
            return {
                "project_id": project_id,
                "runs": [],
                "total_runs": 0,
                "source_status": _empty_project_source_status(
                    ["pi_analysis_runs"],
                    reason="Analysis run history table is not present in this DB snapshot.",
                ),
            }

        query = """
        SELECT
            run_id,
            run_type,
            started_at,
            completed_at,
            duration_seconds,
            status,
            violations_found,
            bugs_found,
            improvements_suggested
        FROM pi_analysis_runs
        WHERE project_id = ?
        ORDER BY started_at DESC
        LIMIT ?
        """

        rows = cursor.execute(query, (project_id, limit)).fetchall()
        runs = [dict(row) for row in rows]

        return {"project_id": project_id, "runs": runs, "total_runs": len(runs)}

    except Exception as e:
        logger.error(f"Error getting project history: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/analysis-runs/{run_id}")
async def get_analysis_run(run_id: str) -> dict[str, Any]:
    """
    Get detailed information about a specific analysis run.

    Returns full run details including progress and findings.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "pi_analysis_runs"):
            raise HTTPException(status_code=404, detail=f"Analysis run {run_id} not found")

        query = """
        SELECT
            run_id,
            project_id,
            run_type,
            started_at,
            completed_at,
            duration_seconds,
            discovery_completed,
            research_completed,
            audit_completed,
            bug_analysis_completed,
            synthesis_completed,
            status,
            violations_found,
            bugs_found,
            improvements_suggested,
            error_message
        FROM pi_analysis_runs
        WHERE run_id = ?
        """

        row = cursor.execute(query, (run_id,)).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail=f"Analysis run {run_id} not found")

        run = dict(row)

        # Calculate progress percentage
        phases = [
            run["discovery_completed"],
            run["research_completed"],
            run["audit_completed"],
            run["bug_analysis_completed"],
            run["synthesis_completed"],
        ]
        completed_phases = sum(1 for p in phases if p)
        progress = (completed_phases / len(phases)) * 100 if phases else 0

        run["progress_percent"] = progress
        run["phases_complete"] = completed_phases
        run["phases_total"] = len(phases)

        return run

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting analysis run: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
