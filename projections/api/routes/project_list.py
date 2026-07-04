"""Project list endpoint."""

import logging
from collections import Counter
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Query

from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL, security_spine_present
from core.production_readiness import production_readiness_dashboard_summary
from projections.api.routes.sqlite_schema import object_exists, table_columns
from projections.api.lib.project_helpers import (
    get_db_connection,
    _optional_count_expr,
    _decorate_project_for_dashboard,
)
from projections.api.lib.security_helpers import (
    _security_alias_expr,
    _security_assignment_summary,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("")
async def list_projects(
    limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)
) -> Dict[str, Any]:
    """
    List all analyzed projects with their latest health scores.

    Returns projects sorted by last_analyzed (most recent first).
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "business_projects"):
            return {
                "total": 0,
                "limit": limit,
                "offset": offset,
                "projects": [],
                "source_status": {
                    "classification": "missing because live DB schema is behind repo migrations",
                    "reason": "business_projects is not available.",
                },
            }

        # Get total count of distinct projects — business_projects (UUID ids, no path dedup needed)
        project_columns = table_columns(conn, "business_projects")
        # detected_stack + stack_json live on business_projects since migration 085
        stack_detected_expr = (
            "p.detected_stack" if "detected_stack" in project_columns else "NULL AS stack_detected"
        )
        stack_json_expr = (
            "p.stack_json" if "stack_json" in project_columns else "NULL AS stack_json"
        )
        project_type_expr = "NULL AS project_type"
        project_source_expr = "NULL AS project_source"
        status_expr = "p.status AS status" if "status" in project_columns else "NULL AS status"
        is_temp_expr = "0 AS is_temp"

        # Get projects with pagination (deduplicated by path, prioritizing entries with most sessions)
        prd_columns = (
            table_columns(conn, "prd_documents") if object_exists(conn, "prd_documents") else set()
        )
        prd_count_expr = (
            "(SELECT COUNT(*) FROM prd_documents WHERE project_id = p.project_id)"
            if object_exists(conn, "prd_documents")
            else "0"
        )
        latest_prd_status_expr = (
            "(SELECT status FROM prd_documents WHERE project_id = p.project_id ORDER BY created_at DESC LIMIT 1)"
            if "status" in prd_columns
            else "NULL"
        )
        latest_prd_title_expr = (
            "(SELECT title FROM prd_documents WHERE project_id = p.project_id ORDER BY created_at DESC LIMIT 1)"
            if "title" in prd_columns
            else "NULL"
        )
        latest_prd_file_path_expr = (
            "(SELECT file_path FROM prd_documents WHERE project_id = p.project_id ORDER BY created_at DESC LIMIT 1)"
            if "file_path" in prd_columns
            else "NULL"
        )
        latest_prd_created_at_expr = (
            "(SELECT created_at FROM prd_documents WHERE project_id = p.project_id ORDER BY created_at DESC LIMIT 1)"
            if "created_at" in prd_columns
            else "NULL"
        )
        # pi_bugs, pi_violations, pi_dependencies dropped in migration 084 — return 0 constants
        # findings_current_status dropped migration 140 (WO dff23cb0) — derive
        # from security_events at read time (core/findings/current_status.py).
        security_open_count_expr = (
            _optional_count_expr(
                f"({FINDINGS_CURRENT_STATUS_SQL})",
                "project_id",
                condition="current_status NOT IN ('resolved', 'mitigated', 'false_positive', 'closed')",
            ).replace("project_id = p.project_id", _security_alias_expr("p.project_id"))
            if security_spine_present(conn)
            else "0"
        )
        attention_open_count_expr = (
            _optional_count_expr(
                "dashboard_attention_items",
                "project_id",
                condition="status NOT IN ('resolved', 'closed', 'dismissed')",
            )
            if object_exists(conn, "dashboard_attention_items")
            else "0"
        )
        validation_failed_count_expr = (
            _optional_count_expr(
                "validation_results",
                "project_id",
                condition="status IN ('failed', 'error', 'incomplete')",
            )
            if object_exists(conn, "validation_results")
            else "0"
        )
        validation_passed_count_expr = (
            _optional_count_expr("validation_results", "project_id", condition="status = 'passed'")
            if object_exists(conn, "validation_results")
            else "0"
        )
        telemetry_event_count_expr = (
            _optional_count_expr("execution_events", "project_id")
            if object_exists(conn, "execution_events")
            else "0"
        )
        route_blocker_count_expr = (
            _optional_count_expr(
                "route_decision_records",
                "project_id",
                condition=(
                    "(handoff_required = 1 OR operator_action_required = 1 OR prompt_required = 1 "
                    "OR (recommended_next_work_order IS NOT NULL AND recommended_next_work_order != 'none'))"
                ),
            )
            if object_exists(conn, "route_decision_records")
            else "0"
        )
        # business_projects has UUID ids — no path deduplication needed (no ranked_projects CTE)
        # Analysis columns (health_score, pi_* counts) removed in migration 084; return NULL/0.
        # Column mapping: reg_projects.project_name → business_projects.name
        query = """
        SELECT
            p.project_id,
            p.name AS project_name,
            p.project_path,
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
            COALESCE(p.total_sessions, 0) AS total_sessions,
            COALESCE(
                {prd_count_expr},
                0
            ) as prd_count,
            {latest_prd_status_expr} as latest_prd_status,
            {latest_prd_title_expr} as latest_prd_title,
            {latest_prd_file_path_expr} as latest_prd_file_path,
            {latest_prd_created_at_expr} as latest_prd_created_at,
            0 as bug_count,
            0 as critical_bug_count,
            0 as violation_count,
            0 as dependency_count,
            COALESCE({security_open_count_expr}, 0) as security_open_count,
            COALESCE({attention_open_count_expr}, 0) as attention_open_count,
            COALESCE({validation_failed_count_expr}, 0) as validation_failed_count,
            COALESCE({validation_passed_count_expr}, 0) as validation_passed_count,
            COALESCE({telemetry_event_count_expr}, 0) as telemetry_event_count,
            COALESCE({route_blocker_count_expr}, 0) as route_blocker_count
        FROM business_projects p
        WHERE p.status != 'deleted'
        ORDER BY COALESCE(p.last_session_at, p.updated_at) DESC
        """.format(
            project_type_expr=project_type_expr,
            project_source_expr=project_source_expr,
            status_expr=status_expr,
            is_temp_expr=is_temp_expr,
            stack_detected_expr=stack_detected_expr,
            stack_json_expr=stack_json_expr,
            prd_count_expr=prd_count_expr,
            latest_prd_status_expr=latest_prd_status_expr,
            latest_prd_title_expr=latest_prd_title_expr,
            latest_prd_file_path_expr=latest_prd_file_path_expr,
            latest_prd_created_at_expr=latest_prd_created_at_expr,
            security_open_count_expr=security_open_count_expr,
            attention_open_count_expr=attention_open_count_expr,
            validation_failed_count_expr=validation_failed_count_expr,
            validation_passed_count_expr=validation_passed_count_expr,
            telemetry_event_count_expr=telemetry_event_count_expr,
            route_blocker_count_expr=route_blocker_count_expr,
        )

        rows = cursor.execute(query).fetchall()
        candidate_projects = []
        excluded_projects = []
        for row in rows:
            project = _decorate_project_for_dashboard(dict(row))
            if not project["project_authority_status"]["include_in_default_operator_view"]:
                excluded_projects.append(project)
                continue
            project["project_readiness_status"] = production_readiness_dashboard_summary(
                conn,
                project_id=project["project_id"],
            )["readiness_score"]
            candidate_projects.append(project)
        total = len(candidate_projects)
        projects = candidate_projects[offset : offset + limit]  # noqa: E203
        excluded_summary = Counter(
            project["project_authority_status"]["retention_class"] for project in excluded_projects
        )

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "projects": projects,
            "derived_view": True,
            "primary_authority": False,
            "source_status": {
                "classification": "fresh",
                "reason": "Default All Projects shows only current legitimate project authority rows; temp, pytest, demo, placeholder, inactive, adapter-worktree, missing-path, and retained legacy rows are excluded from normal operator views.",
                "source_tables": ["business_projects"]
                + (["prd_documents"] if object_exists(conn, "prd_documents") else [])
                # findings_current_status dropped migration 140 (WO dff23cb0) —
                # derived from security_events at read time, not a schema object.
                + (["security_events"] if object_exists(conn, "security_events") else [])
                + (
                    ["dashboard_attention_items"]
                    if object_exists(conn, "dashboard_attention_items")
                    else []
                )
                + (["validation_results"] if object_exists(conn, "validation_results") else [])
                + (["execution_events"] if object_exists(conn, "execution_events") else [])
                + (
                    ["route_decision_records"]
                    if object_exists(conn, "route_decision_records")
                    else []
                )
                + (
                    ["production_readiness_assessment_runs"]
                    if object_exists(conn, "production_readiness_assessment_runs")
                    else []
                )
                + (
                    ["project_readiness_scorecards"]
                    if object_exists(conn, "project_readiness_scorecards")
                    else []
                ),
                "missing": [] if object_exists(conn, "prd_documents") else ["prd_documents"],
                "excluded_from_default_view": {
                    "count": len(excluded_projects),
                    "by_retention_class": dict(excluded_summary),
                    "sample_project_ids": [
                        project["project_id"] for project in excluded_projects[:12]
                    ],
                },
                "security_finding_assignment_summary": _security_assignment_summary(
                    conn, candidate_projects
                ),
            },
        }

    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
