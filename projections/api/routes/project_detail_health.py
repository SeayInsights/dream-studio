"""Project health endpoint.

WO-GF-API-ROUTES: split out of project_detail.py.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException

from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL, security_spine_present
from core.production_readiness import production_readiness_dashboard_summary
from projections.api.lib.project_helpers import (
    get_db_connection,
    _decorate_project_for_dashboard,
    _project_surface_availability,
    _unavailable_project_surfaces,
)
from projections.api.lib.security_helpers import _security_alias_expr
from projections.api.routes.sqlite_schema import object_exists, table_columns

from .project_detail_router import router

logger = logging.getLogger(__name__)


@router.get("/{project_id}/health")
async def get_project_health(project_id: str) -> dict[str, Any]:
    """
    Get detailed health metrics for a specific project.

    Returns:
    - Current health score, security score, maintainability score
    - Violation counts by severity
    - Bug counts by severity
    - Improvement suggestions count
    - Latest analysis run info
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        # Get project details — reg_projects deleted in migration 084; use business_projects
        project_columns = table_columns(conn, "business_projects")
        stack_detected_expr = (
            "detected_stack" if "detected_stack" in project_columns else "NULL AS stack_detected"
        )
        stack_json_expr = "stack_json" if "stack_json" in project_columns else "NULL AS stack_json"
        project_type_expr = "NULL AS project_type"
        project_source_expr = "NULL AS project_source"
        status_expr = "status AS status" if "status" in project_columns else "NULL AS status"
        is_temp_expr = "0 AS is_temp"
        prd_columns = (
            table_columns(conn, "prd_documents") if object_exists(conn, "prd_documents") else set()
        )
        prd_count_expr = (
            "(SELECT COUNT(*) FROM prd_documents WHERE project_id = business_projects.project_id)"
            if object_exists(conn, "prd_documents")
            else "0"
        )
        latest_prd_status_expr = (
            "(SELECT status FROM prd_documents WHERE project_id = business_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "status" in prd_columns
            else "NULL"
        )
        latest_prd_title_expr = (
            "(SELECT title FROM prd_documents WHERE project_id = business_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "title" in prd_columns
            else "NULL"
        )
        latest_prd_file_path_expr = (
            "(SELECT file_path FROM prd_documents WHERE project_id = business_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "file_path" in prd_columns
            else "NULL"
        )
        latest_prd_created_at_expr = (
            "(SELECT created_at FROM prd_documents WHERE project_id = business_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "created_at" in prd_columns
            else "NULL"
        )
        # pi_dependencies dropped in migration 084; 0 is hardcoded in the query
        # findings_current_status dropped migration 140 (WO dff23cb0) — derive
        # from security_events at read time (core/findings/current_status.py).
        security_open_count_expr = (
            f"(SELECT COUNT(*) FROM ({FINDINGS_CURRENT_STATUS_SQL}) WHERE "
            f"{_security_alias_expr('business_projects.project_id')} "
            "AND current_status NOT IN ('resolved', 'mitigated', 'false_positive', 'closed'))"
            if security_spine_present(conn)
            else "0"
        )
        attention_open_count_expr = (
            "(SELECT COUNT(*) FROM dashboard_attention_items WHERE project_id = business_projects.project_id AND status NOT IN ('resolved', 'closed', 'dismissed'))"
            if object_exists(conn, "dashboard_attention_items")
            else "0"
        )
        validation_failed_count_expr = (
            "(SELECT COUNT(*) FROM validation_results WHERE project_id = business_projects.project_id AND status IN ('failed', 'error', 'incomplete'))"
            if object_exists(conn, "validation_results")
            else "0"
        )
        validation_passed_count_expr = (
            "(SELECT COUNT(*) FROM validation_results WHERE project_id = business_projects.project_id AND status = 'passed')"
            if object_exists(conn, "validation_results")
            else "0"
        )
        telemetry_event_count_expr = (
            "(SELECT COUNT(*) FROM execution_events WHERE project_id = business_projects.project_id)"
            if object_exists(conn, "execution_events")
            else "0"
        )
        route_blocker_count_expr = (
            "(SELECT COUNT(*) FROM route_decision_records WHERE project_id = business_projects.project_id "
            "AND (handoff_required = 1 OR operator_action_required = 1 OR prompt_required = 1 "
            "OR (recommended_next_work_order IS NOT NULL AND recommended_next_work_order != 'none')))"
            if object_exists(conn, "route_decision_records")
            else "0"
        )
        project_query = f"""
        SELECT
            project_id,
            name AS project_name,
            project_path,
            {project_type_expr},
            {project_source_expr},
            {status_expr},
            {is_temp_expr},
            {stack_detected_expr},
            {stack_json_expr},
            NULL AS health_score,
            NULL AS security_score,
            NULL AS maintainability_score,
            NULL AS total_files,
            NULL AS lines_of_code,
            NULL AS first_analyzed,
            NULL AS last_analyzed,
            COALESCE(
                {prd_count_expr},
                0
            ) as prd_count,
            {latest_prd_status_expr} as latest_prd_status,
            {latest_prd_title_expr} as latest_prd_title,
            {latest_prd_file_path_expr} as latest_prd_file_path,
            {latest_prd_created_at_expr} as latest_prd_created_at,
            0 as dependency_count,
            COALESCE({security_open_count_expr}, 0) as security_open_count,
            COALESCE({attention_open_count_expr}, 0) as attention_open_count,
            COALESCE({validation_failed_count_expr}, 0) as validation_failed_count,
            COALESCE({validation_passed_count_expr}, 0) as validation_passed_count,
            COALESCE({telemetry_event_count_expr}, 0) as telemetry_event_count,
            COALESCE({route_blocker_count_expr}, 0) as route_blocker_count
        FROM business_projects
        WHERE project_id = ?
        """

        project_row = cursor.execute(project_query, (project_id,)).fetchone()

        if not project_row:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")

        project = _decorate_project_for_dashboard(dict(project_row))

        # pi_violations, pi_bugs, pi_improvements, pi_analysis_runs dropped in migration 084
        missing_optional = []
        violations = {}
        bugs = {}
        improvements = {}

        latest_run = None
        if object_exists(conn, "pi_analysis_runs"):
            run_query = """
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
            LIMIT 1
            """
            latest_run_row = cursor.execute(run_query, (project_id,)).fetchone()
            latest_run = dict(latest_run_row) if latest_run_row else None
        availability = _project_surface_availability(conn)
        production_readiness = production_readiness_dashboard_summary(conn, project_id=project_id)

        return {
            "project": project,
            "health": {
                "overall_score": project["health_score"],
                "security_score": project["security_score"],
                "maintainability_score": project["maintainability_score"],
            },
            "readiness": production_readiness["readiness_score"],
            "production_readiness": production_readiness,
            "violations": violations,
            "bugs": bugs,
            "improvements": improvements,
            "latest_run": latest_run,
            "available_surfaces": availability,
            "removed_surfaces": _unavailable_project_surfaces(availability),
            "source_status": {
                "classification": "fresh" if not missing_optional else "empty by design",
                "reason": (
                    "Project health includes current project authority and available project intelligence tables."
                    if not missing_optional
                    else "Project authority exists, but optional project-intelligence detail tables are absent in this DB snapshot."
                ),
                "missing": missing_optional,
                "derived_view": True,
                "primary_authority": False,
            },
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project health: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
