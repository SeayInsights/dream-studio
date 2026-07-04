"""Project detail, health, history, analysis run, and activity endpoints."""

import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, Query

from core.findings.current_status import FINDINGS_CURRENT_STATUS_SQL, security_spine_present
from core.production_readiness import production_readiness_dashboard_summary
from core.shared_intelligence.task_attribution import project_recent_attributed_work
from projections.api.routes.sqlite_schema import object_exists, table_columns
from projections.api.lib.project_helpers import (
    get_db_connection,
    _decorate_project_for_dashboard,
    _empty_project_source_status,
    _project_surface_availability,
    _unavailable_project_surfaces,
    _module_runtime_fit,
    _recent_validation_state,
    _attention_detail_items,
    _finding_summary,
    _collect_evidence_refs,
    _project_detail_known_gaps,
    _project_detail_next_action,
)
from projections.api.lib.security_helpers import _security_alias_expr

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/{project_id}/health")
async def get_project_health(project_id: str) -> Dict[str, Any]:
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
        project_query = """
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
        """.format(
            stack_detected_expr=stack_detected_expr,
            stack_json_expr=stack_json_expr,
            project_type_expr=project_type_expr,
            project_source_expr=project_source_expr,
            status_expr=status_expr,
            is_temp_expr=is_temp_expr,
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


@router.get("/{project_id}/details")
async def get_project_details(project_id: str) -> Dict[str, Any]:
    """Return project detail view data with health and readiness separated."""

    health_payload = await get_project_health(project_id)
    conn = get_db_connection()
    try:
        production_readiness = production_readiness_dashboard_summary(conn, project_id=project_id)
        security_controls = health_payload["project"]["security_lifecycle_status"]
        from projections.api.routes.project_artifacts import get_project_dependencies

        dependency_graph = await get_project_dependencies(project_id, limit=200)
        # Phase 18.2 compliance: filesystem scan removed from critical popup path.
        # Stack framework data comes from business_projects.stack_json (L3, instant).
        # Detailed filesystem scan deferred — will surface via on-demand endpoint in a
        # future WO with proper event emission and L3 write-back.
        repo_stack = {
            "classification": "deferred",
            "reason": (
                "Detailed filesystem scan not on popup critical path. "
                "Framework data from business_projects.stack_json."
            ),
            "source_refs": [],
            "inferred_dependency_edges": [],
            "inferred_dependency_count": 0,
            "derived_view": True,
            "primary_authority": False,
        }
        # Use L3 stack evidence (from business_projects) for module_runtime_fit
        # instead of the filesystem-derived repo_stack.
        module_fit = _module_runtime_fit(
            health_payload["project"],
            health_payload["project"].get("stack_evidence") or repo_stack,
            dependency_graph,
        )
        validation_state = _recent_validation_state(conn, project_id)
        attention_detail = _attention_detail_items(conn, project_id)
        attributed_work = project_recent_attributed_work(conn, project_id, limit=10)
        prd_lifecycle = {"data_status": "retired", "model_name": "prd_cluster_retired_wo_f"}
        return {
            "project_id": project_id,
            "derived_view": True,
            "primary_authority": False,
            "project_identity": {
                "project_id": project_id,
                "project_name": health_payload["project"].get("project_name"),
                "project_path": health_payload["project"].get("project_path"),
                "project_authority_status": health_payload["project"].get(
                    "project_authority_status"
                ),
                "authority_source": health_payload["project"].get("authority_source"),
            },
            "prd_status": health_payload["project"].get("prd_status"),
            "prd_summary": (health_payload["project"].get("prd_status") or {})
            .get("authority", {})
            .get("summary"),
            "prd_lifecycle_authority": prd_lifecycle.get("data_status", "retired"),
            "prd_version": prd_lifecycle.get("prd_version"),
            "prd_confidence": prd_lifecycle.get("prd_confidence"),
            "in_flight_formalization_status": prd_lifecycle.get("in_flight_formalization_status"),
            "pending_prd_questions": prd_lifecycle.get("pending_prd_questions", []),
            "prd_assumptions": prd_lifecycle.get("prd_assumptions", []),
            "current_milestones": prd_lifecycle.get("current_milestones", []),
            "active_work_orders": prd_lifecycle.get("active_work_orders", []),
            "change_order_history": prd_lifecycle.get("change_order_history", []),
            "pending_change_orders": prd_lifecycle.get("pending_change_orders", []),
            "route_reconciliation_status": prd_lifecycle.get("route_reconciliation_status"),
            "planned_vs_actual_route_summary": prd_lifecycle.get("planned_vs_actual_route_summary"),
            "health_score": health_payload["health"],
            "readiness_score": production_readiness["readiness_score"],
            "readiness_control_coverage": production_readiness["control_summary"],
            "enterprise_security_controls": security_controls["applicability_summary"],
            "enterprise_security_control_status": {
                "controls": security_controls.get("applicability", []),
                "summary": security_controls["applicability_summary"],
                "source_framework": security_controls["source_framework"],
                "manual_review_required": security_controls["applicability_summary"].get(
                    "manual_review_required", 0
                ),
                "unknown": security_controls["applicability_summary"].get("unknown", 0),
                "derived_view": True,
                "primary_authority": False,
            },
            "production_readiness_controls": production_readiness["controls"],
            "findings_by_severity_status": _finding_summary(
                production_readiness["findings"],
                health_payload.get("project", {})
                .get("security_package_status", {})
                .get("open_findings", 0),
            ),
            "not_applicable_controls": [
                item
                for item in production_readiness["controls"]
                if item.get("status") == "not_applicable"
            ],
            "manual_review_controls": [
                item
                for item in production_readiness["controls"]
                if item.get("status") == "manual_review"
            ],
            "remediation_work_orders": production_readiness["remediation_work_orders"],
            "evidence_refs": _collect_evidence_refs(production_readiness["controls"]),
            "release_blockers": [
                item for item in production_readiness["controls"] if item.get("blocking")
            ],
            "compliance_legal_review_flags": production_readiness["compliance_review_flags"],
            "stack_status": health_payload["project"].get("stack_evidence"),
            "stack_evidence": {
                "registry_stack": health_payload["project"].get("stack_evidence"),
                "repo_scan": repo_stack,
                "source_refs": sorted(
                    set(
                        (repo_stack.get("source_refs") or [])
                        + (
                            health_payload["project"]
                            .get("stack_evidence", {})
                            .get("config_files", [])
                        )
                    )
                ),
                "secret_contents_read": False,
                "repo_mutation_authorized": False,
                "derived_view": True,
                "primary_authority": False,
            },
            "confirmed_dependencies": {
                "nodes": dependency_graph.get("nodes", []),
                "edges": dependency_graph.get("edges", []),
                "node_count": dependency_graph.get("node_count", 0),
                "edge_count": dependency_graph.get("edge_count", 0),
                "rendered_by_default": True,
                "source_status": dependency_graph.get("source_status"),
                "knowledge_graph_status": dependency_graph.get("knowledge_graph_status"),
            },
            "inferred_or_unverified_dependencies": {
                "edges": dependency_graph.get("inferred_edges", [])
                + repo_stack.get("inferred_dependency_edges", []),
                "edge_count": dependency_graph.get("inferred_edge_count", 0)
                + repo_stack.get("inferred_dependency_count", 0),
                "rendered_by_default": False,
                "reason": "Manifest-derived or unverified dependencies are labeled separately and hidden from the default confirmed graph.",
            },
            "dependency_drilldown": {
                "project_to_stack_component": "/api/v1/projects/{project_id}/details",
                "stack_component_to_dependency": "/api/v1/projects/{project_id}/dependencies",
                "dependency_to_evidence": "edge.source_refs and node.evidence_refs",
                "confirmed_edges_only_by_default": True,
            },
            "dependency_status": health_payload["project"].get("dependency_source_status"),
            "module_runtime_profile_fit": module_fit,
            "security_status": health_payload["project"].get("security_package_status"),
            "validation_state": {
                "summary": health_payload["project"].get("telemetry_status"),
                "recent": validation_state,
            },
            "recent_attributed_work": attributed_work,
            "work_order_status": health_payload["project"].get("work_order_status"),
            "attention_items": attention_detail,
            "known_gaps": _project_detail_known_gaps(health_payload, production_readiness),
            "current_next_action": _project_detail_next_action(
                health_payload, production_readiness
            ),
            "source_status": {
                "classification": (
                    "fresh" if production_readiness.get("assessment_id") else "empty by design"
                ),
                "source_tables": production_readiness.get("source_tables", []),
                "derived_view": True,
                "primary_authority": False,
            },
        }
    finally:
        conn.close()


@router.get("/{project_id}/history")
async def get_project_history(
    project_id: str, limit: int = Query(20, ge=1, le=100)
) -> Dict[str, Any]:
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
async def get_analysis_run(run_id: str) -> Dict[str, Any]:
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


@router.get("/{project_id}/activity")
async def get_project_activity(
    project_id: str, limit: int = Query(20, ge=1, le=100)
) -> Dict[str, Any]:
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
