"""Project Intelligence API routes for health scores, analysis runs, and real-time progress"""

import ast
import json
import logging
import sqlite3
import uuid
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from pathlib import Path
from typing import Dict, Any, List, Optional

from ..websocket.connection_manager import ConnectionManager
from core.config.database import get_connection
from core.security.lifecycle import build_security_lifecycle_gate
from projections.api.routes.sqlite_schema import object_exists, table_columns

logger = logging.getLogger(__name__)

router = APIRouter()

# Global connection manager instance for project intelligence subscriptions
pi_connection_manager = ConnectionManager()


def get_db_path() -> str:
    """Get database path"""
    from core.config.database import get_db_path as _canonical

    return str(_canonical())


def get_db_connection():
    """Get database connection with row factory"""
    db_path = get_db_path()
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    return conn


def _active_project_where(conn) -> str:
    """Filter out quarantined/temp project records when live schema supports it."""

    clauses = ["project_name IS NOT NULL"]
    columns = table_columns(conn, "reg_projects")
    if "status" in columns:
        clauses.append(
            "(status IS NULL OR status NOT IN ('inactive', 'archived', 'deactivated', 'quarantined'))"
        )
    if "is_temp" in columns:
        clauses.append("(is_temp IS NULL OR is_temp = 0)")
    if "project_source" in columns:
        try:
            has_local_builds = (
                conn.execute(
                    "SELECT COUNT(*) FROM reg_projects WHERE project_source = 'local_builds'"
                ).fetchone()[0]
                > 0
            )
        except sqlite3.Error:
            has_local_builds = False
        if has_local_builds:
            clauses.append("project_source = 'local_builds'")
    return " AND ".join(clauses)


def _optional_count_expr(table: str, where_column: str, *, condition: str | None = None) -> str:
    base = f"(SELECT COUNT(*) FROM {table} WHERE {where_column} = p.project_id"
    if condition:
        base += f" AND {condition}"
    return base + ")"


def _project_path_exists(project_path: str | None) -> bool:
    if not project_path:
        return False
    path = Path(project_path)
    if not path.is_absolute():
        path = Path.home() / "builds" / project_path
    return path.exists()


def _parse_stack_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _build_health_model(project: dict[str, Any]) -> dict[str, Any]:
    """Derive dashboard health from current evidence instead of stored legacy scores."""

    signals = {
        "path_confirmed": project.get("path_status") == "confirmed",
        "prd_count": _as_int(project.get("prd_count")),
        "security_open_count": _as_int(project.get("security_open_count")),
        "validation_failed_count": _as_int(project.get("validation_failed_count")),
        "validation_passed_count": _as_int(project.get("validation_passed_count")),
        "attention_open_count": _as_int(project.get("attention_open_count")),
        "route_blocker_count": _as_int(project.get("route_blocker_count")),
        "telemetry_event_count": _as_int(project.get("telemetry_event_count")),
        "dependency_count": _as_int(project.get("dependency_count")),
        "security_lifecycle_manual_review_count": _as_int(
            project.get("security_lifecycle_manual_review_count")
        ),
        "security_lifecycle_unknown_count": _as_int(
            project.get("security_lifecycle_unknown_count")
        ),
    }
    evidence_points = sum(
        1
        for value in (
            signals["prd_count"],
            signals["security_open_count"],
            signals["validation_failed_count"],
            signals["validation_passed_count"],
            signals["attention_open_count"],
            signals["route_blocker_count"],
            signals["telemetry_event_count"],
            signals["dependency_count"],
            signals["security_lifecycle_manual_review_count"],
            signals["security_lifecycle_unknown_count"],
        )
        if value > 0
    )
    if not signals["path_confirmed"] and evidence_points == 0:
        return {
            "status": "unavailable",
            "score": None,
            "label": "Health unavailable",
            "reason": "Project path is unverified and there are no current telemetry, PRD, security, validation, attention, or dependency signals.",
            "signals": signals,
            "derived_view": True,
            "primary_authority": False,
        }

    score = 100
    penalties: list[str] = []
    if not signals["path_confirmed"]:
        score -= 30
        penalties.append("project path is not confirmed")
    if signals["security_open_count"]:
        penalty = min(35, signals["security_open_count"] * 8)
        score -= penalty
        penalties.append(f"{signals['security_open_count']} open security finding(s)")
    if signals["validation_failed_count"]:
        penalty = min(25, signals["validation_failed_count"] * 10)
        score -= penalty
        penalties.append(f"{signals['validation_failed_count']} failed/incomplete validation(s)")
    if signals["attention_open_count"]:
        penalty = min(20, signals["attention_open_count"] * 4)
        score -= penalty
        penalties.append(f"{signals['attention_open_count']} open attention item(s)")
    if signals["route_blocker_count"]:
        penalty = min(20, signals["route_blocker_count"] * 8)
        score -= penalty
        penalties.append(f"{signals['route_blocker_count']} route blocker/approval item(s)")
    if signals["prd_count"] == 0:
        score -= 5
        penalties.append("no PRD authority linked")
    if signals["dependency_count"] == 0:
        score -= 5
        penalties.append("no confirmed dependency evidence")
    if signals["security_lifecycle_manual_review_count"]:
        penalty = min(20, signals["security_lifecycle_manual_review_count"] * 4)
        score -= penalty
        penalties.append(
            f"{signals['security_lifecycle_manual_review_count']} security lifecycle manual review control(s)"
        )
    if signals["security_lifecycle_unknown_count"]:
        penalty = min(30, signals["security_lifecycle_unknown_count"] * 10)
        score -= penalty
        penalties.append(
            f"{signals['security_lifecycle_unknown_count']} unknown security lifecycle control(s)"
        )

    score = max(0, min(100, score))
    if score >= 85:
        label = "Healthy"
    elif score >= 65:
        label = "Watch"
    elif score >= 40:
        label = "At risk"
    else:
        label = "Needs attention"
    return {
        "status": "scored",
        "score": score,
        "label": label,
        "reason": "; ".join(penalties) if penalties else "Current evidence has no active blockers.",
        "signals": signals,
        "derived_view": True,
        "primary_authority": False,
    }


def _decorate_project_for_dashboard(project: dict[str, Any]) -> dict[str, Any]:
    stack = _parse_stack_json(project.get("stack_json"))
    dependencies = stack.get("dependencies") if isinstance(stack.get("dependencies"), list) else []
    config_files = stack.get("config_files") if isinstance(stack.get("config_files"), list) else []
    entry_points = stack.get("entry_points") if isinstance(stack.get("entry_points"), list) else []
    path_exists = _project_path_exists(project.get("project_path"))
    framework = project.get("stack_detected") or stack.get("framework")
    project["path_status"] = "confirmed" if path_exists else "unverified_missing_path"
    project["stack_evidence"] = {
        "classification": (
            "confirmed" if framework and framework != "unknown" else "honest_empty_state"
        ),
        "framework": framework or "unknown",
        "dependency_count": len(dependencies),
        "config_files": config_files[:8],
        "entry_points": entry_points[:8],
        "source_tables": ["reg_projects"],
        "source_fields": ["stack_detected", "stack_json", "project_path"],
        "inferred": False,
        "path_status": project["path_status"],
    }
    project["dependency_source_status"] = {
        "classification": (
            "confirmed" if int(project.get("dependency_count") or 0) > 0 else "empty by design"
        ),
        "source_tables": ["pi_dependencies"],
        "reason": (
            "Dependency edges are read from pi_dependencies."
            if int(project.get("dependency_count") or 0) > 0
            else "No confirmed dependency edges recorded for this project."
        ),
        "inferred": False,
    }
    prd_status = project.get("latest_prd_status")
    project["prd_status"] = {
        "count": _as_int(project.get("prd_count")),
        "latest_status": prd_status,
        "latest_title": project.get("latest_prd_title"),
        "latest_file_path": project.get("latest_prd_file_path"),
        "classification": "fresh" if _as_int(project.get("prd_count")) else "empty by design",
        "source_tables": ["prd_documents"],
        "derived_view": True,
        "primary_authority": False,
    }
    project["security_package_status"] = {
        "open_findings": _as_int(project.get("security_open_count")),
        "classification": "fresh" if _as_int(project.get("security_open_count")) else "fresh_empty",
        "source_tables": ["security_findings"],
        "source_package": "security-review-source-47-enterprise-scans.md",
        "derived_view": True,
        "primary_authority": False,
    }
    security_lifecycle = build_security_lifecycle_gate(
        lifecycle_event="project_health",
        project_id=str(project.get("project_id") or "dream-studio"),
        open_finding_count=_as_int(project.get("security_open_count")),
    )
    project["security_lifecycle_status"] = security_lifecycle
    project["security_lifecycle_manual_review_count"] = security_lifecycle["applicability_summary"][
        "manual_review_required"
    ]
    project["security_lifecycle_unknown_count"] = security_lifecycle["applicability_summary"][
        "unknown"
    ]
    project["work_order_status"] = {
        "route_blockers": _as_int(project.get("route_blocker_count")),
        "attention_open": _as_int(project.get("attention_open_count")),
        "source_tables": ["route_decision_records", "dashboard_attention_items"],
        "derived_view": True,
        "primary_authority": False,
    }
    project["telemetry_status"] = {
        "event_count": _as_int(project.get("telemetry_event_count")),
        "validation_passed_count": _as_int(project.get("validation_passed_count")),
        "validation_failed_count": _as_int(project.get("validation_failed_count")),
        "source_tables": ["execution_events", "validation_results"],
        "derived_view": True,
        "primary_authority": False,
    }
    project["health_model"] = _build_health_model(project)
    if project["health_model"].get("score") is not None:
        project["health_score"] = round(float(project["health_model"]["score"]) / 10, 1)
    else:
        project["health_score"] = None
    open_findings = _as_int(project.get("security_open_count"))
    project["security_score"] = round(max(0, 100 - min(100, open_findings * 10)) / 10, 1)
    return project


def _missing_tables(conn, names: list[str]) -> list[str]:
    return [name for name in names if not object_exists(conn, name)]


def _empty_project_source_status(missing: list[str], *, reason: str) -> dict[str, Any]:
    return {
        "classification": "empty by design",
        "reason": reason,
        "missing": missing,
        "derived_view": True,
        "primary_authority": False,
    }


def _project_surface_availability(conn) -> dict[str, bool]:
    dependency_columns = (
        table_columns(conn, "pi_dependencies") if object_exists(conn, "pi_dependencies") else []
    )
    return {
        "overview": True,
        "prds": object_exists(conn, "prd_documents"),
        "security": any(
            object_exists(conn, name)
            for name in ("security_findings", "sec_sarif_findings", "pi_violations")
        ),
        "dependencies": object_exists(conn, "pi_dependencies")
        and {"from_component", "to_component"}.issubset(dependency_columns),
        "activity": any(
            object_exists(conn, name)
            for name in ("execution_events", "process_runs", "pi_analysis_runs")
        ),
        "health_trend": object_exists(conn, "pi_analysis_runs"),
        "bugs_summary": object_exists(conn, "pi_bugs"),
        "violations_summary": object_exists(conn, "pi_violations"),
    }


def _unavailable_project_surfaces(availability: dict[str, bool]) -> list[str]:
    return [name for name, available in availability.items() if not available]


# ── HTTP Endpoints ───────────────────────────────────────────────────────────


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

        if not object_exists(conn, "reg_projects"):
            return {
                "total": 0,
                "limit": limit,
                "offset": offset,
                "projects": [],
                "source_status": {
                    "classification": "missing because live DB schema is behind repo migrations",
                    "reason": "reg_projects is not available.",
                },
            }

        # Get total count of distinct projects
        active_project_where = _active_project_where(conn)
        project_columns = table_columns(conn, "reg_projects")
        stack_detected_expr = (
            "p.stack_detected" if "stack_detected" in project_columns else "NULL AS stack_detected"
        )
        stack_json_expr = (
            "p.stack_json" if "stack_json" in project_columns else "NULL AS stack_json"
        )
        count_query = f"SELECT COUNT(DISTINCT project_path) as total FROM reg_projects WHERE {active_project_where}"
        total = cursor.execute(count_query).fetchone()["total"]

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
        bug_count_expr = (
            _optional_count_expr("pi_bugs", "project_id", condition="status != 'fixed'")
            if object_exists(conn, "pi_bugs")
            else "0"
        )
        critical_bug_count_expr = (
            _optional_count_expr(
                "pi_bugs", "project_id", condition="status != 'fixed' AND severity = 'critical'"
            )
            if object_exists(conn, "pi_bugs")
            else "0"
        )
        violation_count_expr = (
            _optional_count_expr("pi_violations", "project_id", condition="status != 'resolved'")
            if object_exists(conn, "pi_violations")
            else "0"
        )
        dependency_count_expr = (
            _optional_count_expr("pi_dependencies", "project_id")
            if object_exists(conn, "pi_dependencies")
            else "0"
        )
        security_open_count_expr = (
            _optional_count_expr(
                "security_findings",
                "project_id",
                condition="status NOT IN ('resolved', 'mitigated', 'false_positive', 'closed')",
            )
            if object_exists(conn, "security_findings")
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
        query = """
        WITH ranked_projects AS (
            SELECT
                *,
                ROW_NUMBER() OVER (
                    PARTITION BY project_path
                    ORDER BY total_sessions DESC, last_analyzed DESC
                ) as rn
            FROM reg_projects
            WHERE {active_project_where}
        )
        SELECT
            p.project_id,
            p.project_name,
            p.project_path,
            {stack_detected_expr},
            {stack_json_expr},
            p.health_score,
            p.security_score,
            p.maintainability_score,
            p.total_files,
            p.lines_of_code,
            p.first_analyzed,
            p.last_analyzed,
            p.total_sessions,
            COALESCE(
                {prd_count_expr},
                0
            ) as prd_count,
            {latest_prd_status_expr} as latest_prd_status,
            {latest_prd_title_expr} as latest_prd_title,
            {latest_prd_file_path_expr} as latest_prd_file_path,
            COALESCE({bug_count_expr}, 0) as bug_count,
            COALESCE({critical_bug_count_expr}, 0) as critical_bug_count,
            COALESCE({violation_count_expr}, 0) as violation_count,
            COALESCE({dependency_count_expr}, 0) as dependency_count,
            COALESCE({security_open_count_expr}, 0) as security_open_count,
            COALESCE({attention_open_count_expr}, 0) as attention_open_count,
            COALESCE({validation_failed_count_expr}, 0) as validation_failed_count,
            COALESCE({validation_passed_count_expr}, 0) as validation_passed_count,
            COALESCE({telemetry_event_count_expr}, 0) as telemetry_event_count,
            COALESCE({route_blocker_count_expr}, 0) as route_blocker_count
        FROM ranked_projects p
        WHERE p.rn = 1
        ORDER BY p.total_sessions DESC, p.last_analyzed DESC
        LIMIT ? OFFSET ?
        """.format(
            active_project_where=active_project_where,
            stack_detected_expr=stack_detected_expr,
            stack_json_expr=stack_json_expr,
            prd_count_expr=prd_count_expr,
            latest_prd_status_expr=latest_prd_status_expr,
            latest_prd_title_expr=latest_prd_title_expr,
            latest_prd_file_path_expr=latest_prd_file_path_expr,
            bug_count_expr=bug_count_expr,
            critical_bug_count_expr=critical_bug_count_expr,
            violation_count_expr=violation_count_expr,
            dependency_count_expr=dependency_count_expr,
            security_open_count_expr=security_open_count_expr,
            attention_open_count_expr=attention_open_count_expr,
            validation_failed_count_expr=validation_failed_count_expr,
            validation_passed_count_expr=validation_passed_count_expr,
            telemetry_event_count_expr=telemetry_event_count_expr,
            route_blocker_count_expr=route_blocker_count_expr,
        )

        rows = cursor.execute(query, (limit, offset)).fetchall()
        projects = [_decorate_project_for_dashboard(dict(row)) for row in rows]

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "projects": projects,
            "derived_view": True,
            "primary_authority": False,
            "source_status": {
                "classification": "fresh",
                "reason": "Projects are read from current active reg_projects rows; quarantined, temp, inactive, archived, and deactivated records are excluded.",
                "source_tables": ["reg_projects"]
                + (["prd_documents"] if object_exists(conn, "prd_documents") else [])
                + (["pi_bugs"] if object_exists(conn, "pi_bugs") else [])
                + (["pi_violations"] if object_exists(conn, "pi_violations") else [])
                + (["pi_dependencies"] if object_exists(conn, "pi_dependencies") else [])
                + (["security_findings"] if object_exists(conn, "security_findings") else [])
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
                ),
                "missing": [] if object_exists(conn, "prd_documents") else ["prd_documents"],
            },
        }

    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


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

        # Get project details
        project_columns = table_columns(conn, "reg_projects")
        stack_detected_expr = (
            "stack_detected" if "stack_detected" in project_columns else "NULL AS stack_detected"
        )
        stack_json_expr = "stack_json" if "stack_json" in project_columns else "NULL AS stack_json"
        prd_columns = (
            table_columns(conn, "prd_documents") if object_exists(conn, "prd_documents") else set()
        )
        prd_count_expr = (
            "(SELECT COUNT(*) FROM prd_documents WHERE project_id = reg_projects.project_id)"
            if object_exists(conn, "prd_documents")
            else "0"
        )
        latest_prd_status_expr = (
            "(SELECT status FROM prd_documents WHERE project_id = reg_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "status" in prd_columns
            else "NULL"
        )
        latest_prd_title_expr = (
            "(SELECT title FROM prd_documents WHERE project_id = reg_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "title" in prd_columns
            else "NULL"
        )
        latest_prd_file_path_expr = (
            "(SELECT file_path FROM prd_documents WHERE project_id = reg_projects.project_id ORDER BY created_at DESC LIMIT 1)"
            if "file_path" in prd_columns
            else "NULL"
        )
        dependency_count_expr = (
            "(SELECT COUNT(*) FROM pi_dependencies WHERE project_id = reg_projects.project_id)"
            if object_exists(conn, "pi_dependencies")
            else "0"
        )
        security_open_count_expr = (
            "(SELECT COUNT(*) FROM security_findings WHERE project_id = reg_projects.project_id AND status NOT IN ('resolved', 'mitigated', 'false_positive', 'closed'))"
            if object_exists(conn, "security_findings")
            else "0"
        )
        attention_open_count_expr = (
            "(SELECT COUNT(*) FROM dashboard_attention_items WHERE project_id = reg_projects.project_id AND status NOT IN ('resolved', 'closed', 'dismissed'))"
            if object_exists(conn, "dashboard_attention_items")
            else "0"
        )
        validation_failed_count_expr = (
            "(SELECT COUNT(*) FROM validation_results WHERE project_id = reg_projects.project_id AND status IN ('failed', 'error', 'incomplete'))"
            if object_exists(conn, "validation_results")
            else "0"
        )
        validation_passed_count_expr = (
            "(SELECT COUNT(*) FROM validation_results WHERE project_id = reg_projects.project_id AND status = 'passed')"
            if object_exists(conn, "validation_results")
            else "0"
        )
        telemetry_event_count_expr = (
            "(SELECT COUNT(*) FROM execution_events WHERE project_id = reg_projects.project_id)"
            if object_exists(conn, "execution_events")
            else "0"
        )
        route_blocker_count_expr = (
            "(SELECT COUNT(*) FROM route_decision_records WHERE project_id = reg_projects.project_id "
            "AND (handoff_required = 1 OR operator_action_required = 1 OR prompt_required = 1 "
            "OR (recommended_next_work_order IS NOT NULL AND recommended_next_work_order != 'none')))"
            if object_exists(conn, "route_decision_records")
            else "0"
        )
        project_query = """
        SELECT
            project_id,
            project_name,
            project_path,
            {stack_detected_expr},
            {stack_json_expr},
            health_score,
            security_score,
            maintainability_score,
            total_files,
            lines_of_code,
            first_analyzed,
            last_analyzed,
            COALESCE(
                {prd_count_expr},
                0
            ) as prd_count,
            {latest_prd_status_expr} as latest_prd_status,
            {latest_prd_title_expr} as latest_prd_title,
            {latest_prd_file_path_expr} as latest_prd_file_path,
            COALESCE({dependency_count_expr}, 0) as dependency_count,
            COALESCE({security_open_count_expr}, 0) as security_open_count,
            COALESCE({attention_open_count_expr}, 0) as attention_open_count,
            COALESCE({validation_failed_count_expr}, 0) as validation_failed_count,
            COALESCE({validation_passed_count_expr}, 0) as validation_passed_count,
            COALESCE({telemetry_event_count_expr}, 0) as telemetry_event_count,
            COALESCE({route_blocker_count_expr}, 0) as route_blocker_count
        FROM reg_projects
        WHERE project_id = ?
        """.format(
            stack_detected_expr=stack_detected_expr,
            stack_json_expr=stack_json_expr,
            prd_count_expr=prd_count_expr,
            latest_prd_status_expr=latest_prd_status_expr,
            latest_prd_title_expr=latest_prd_title_expr,
            latest_prd_file_path_expr=latest_prd_file_path_expr,
            dependency_count_expr=dependency_count_expr,
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

        missing_optional = _missing_tables(
            conn,
            ["pi_violations", "pi_bugs", "pi_improvements", "pi_analysis_runs"],
        )

        violations = {}
        if object_exists(conn, "pi_violations"):
            violations_query = """
            SELECT severity, COUNT(*) as count
            FROM pi_violations
            WHERE project_id = ? AND status != 'resolved'
            GROUP BY severity
            """
            violations = {
                row["severity"]: row["count"]
                for row in cursor.execute(violations_query, (project_id,))
            }

        bugs = {}
        if object_exists(conn, "pi_bugs"):
            bugs_query = """
            SELECT severity, COUNT(*) as count
            FROM pi_bugs
            WHERE project_id = ? AND status != 'fixed'
            GROUP BY severity
            """
            bugs = {
                row["severity"]: row["count"] for row in cursor.execute(bugs_query, (project_id,))
            }

        improvements = {}
        if object_exists(conn, "pi_improvements"):
            improvements_query = """
            SELECT
                CASE
                    WHEN priority_score >= 8 THEN 'high'
                    WHEN priority_score >= 5 THEN 'medium'
                    ELSE 'low'
                END as priority,
                COUNT(*) as count
            FROM pi_improvements
            WHERE project_id = ? AND status != 'implemented'
            GROUP BY priority
            """
            improvements = {
                row["priority"]: row["count"]
                for row in cursor.execute(improvements_query, (project_id,))
            }

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

        return {
            "project": project,
            "health": {
                "overall_score": project["health_score"],
                "security_score": project["security_score"],
                "maintainability_score": project["maintainability_score"],
            },
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


# ── WebSocket Endpoints ──────────────────────────────────────────────────────


@router.websocket("/ws/project-health/{project_id}")
async def websocket_project_health(websocket: WebSocket, project_id: str):
    """
    WebSocket endpoint for real-time project health updates.

    Clients subscribe to a specific project and receive updates when:
    - Analysis runs complete
    - Health score changes
    - New violations/bugs detected
    - Improvements implemented

    Message protocol:
    - Server sends: {"type": "health_update", "data": {...}}
    """
    client_id = str(uuid.uuid4())

    try:
        # Connect the client
        await pi_connection_manager.connect(client_id, websocket)

        # Subscribe to project health updates
        pi_connection_manager.subscribe(client_id, [f"project_health_{project_id}"])

        # Send welcome message
        await websocket.send_json(
            {
                "type": "connected",
                "client_id": client_id,
                "project_id": project_id,
                "message": f"Subscribed to health updates for project {project_id}",
            }
        )

        # Send current health data immediately
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
            SELECT health_score, security_score, maintainability_score, last_analyzed
            FROM reg_projects
            WHERE project_id = ?
            """
            row = cursor.execute(query, (project_id,)).fetchone()

            if row:
                await websocket.send_json({"type": "health_update", "data": dict(row)})
        finally:
            conn.close()

        # Keep connection alive and handle incoming messages
        while True:
            try:
                message = await websocket.receive_json()
                # Echo back for now (could add commands later)
                await websocket.send_json({"type": "ack", "message": message})
            except ValueError as e:
                logger.error(f"Invalid JSON from client {client_id}: {e}")
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected from project health stream")

    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")

    finally:
        pi_connection_manager.disconnect(client_id)


@router.websocket("/ws/analysis-progress/{run_id}")
async def websocket_analysis_progress(websocket: WebSocket, run_id: str):
    """
    WebSocket endpoint for real-time analysis progress updates.

    Streams progress updates during an analysis run:
    - Phase completions (discovery, research, audit, bugs, synthesis)
    - Partial findings counts
    - ETA updates

    Message protocol:
    - Server sends: {"type": "progress_update", "phase": "...", "percent": ..., "data": {...}}
    """
    client_id = str(uuid.uuid4())

    try:
        # Connect the client
        await pi_connection_manager.connect(client_id, websocket)

        # Subscribe to analysis progress
        pi_connection_manager.subscribe(client_id, [f"analysis_progress_{run_id}"])

        # Send welcome message
        await websocket.send_json(
            {
                "type": "connected",
                "client_id": client_id,
                "run_id": run_id,
                "message": f"Subscribed to progress updates for analysis run {run_id}",
            }
        )

        # Send current progress immediately
        conn = get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
            SELECT
                discovery_completed,
                research_completed,
                audit_completed,
                bug_analysis_completed,
                synthesis_completed,
                status
            FROM pi_analysis_runs
            WHERE run_id = ?
            """
            row = cursor.execute(query, (run_id,)).fetchone()

            if row:
                data = dict(row)
                phases = [
                    data["discovery_completed"],
                    data["research_completed"],
                    data["audit_completed"],
                    data["bug_analysis_completed"],
                    data["synthesis_completed"],
                ]
                progress = (sum(1 for p in phases if p) / len(phases)) * 100

                await websocket.send_json(
                    {"type": "progress_update", "percent": progress, "data": data}
                )
        finally:
            conn.close()

        # Keep connection alive
        while True:
            try:
                message = await websocket.receive_json()
                await websocket.send_json({"type": "ack", "message": message})
            except ValueError as e:
                logger.error(f"Invalid JSON from client {client_id}: {e}")
                await websocket.send_json({"type": "error", "message": "Invalid JSON format"})

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected from analysis progress stream")

    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {e}")

    finally:
        pi_connection_manager.disconnect(client_id)


# ── Helper function for broadcasting updates ─────────────────────────────────


async def broadcast_health_update(project_id: str, data: Dict[str, Any]):
    """
    Broadcast health update to all subscribers of a project.

    Called by the analysis engine when a run completes.
    """
    await pi_connection_manager.send_to_subscribers(
        f"project_health_{project_id}",
        {"type": "health_update", "project_id": project_id, "data": data},
    )


async def broadcast_progress_update(run_id: str, phase: str, percent: float, data: Dict[str, Any]):
    """
    Broadcast progress update to all subscribers of an analysis run.

    Called by the analysis engine during phase completions.
    """
    await pi_connection_manager.send_to_subscribers(
        f"analysis_progress_{run_id}",
        {
            "type": "progress_update",
            "run_id": run_id,
            "phase": phase,
            "percent": percent,
            "data": data,
        },
    )


@router.get("/{project_id}/prds")
async def get_project_prds(project_id: str) -> Dict[str, Any]:
    """
    Get all PRDs associated with a specific project.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "prd_documents"):
            return {
                "project_id": project_id,
                "prds": [],
                "count": 0,
                "source_status": _empty_project_source_status(
                    ["prd_documents"],
                    reason="PRD documents table is not present in this DB snapshot.",
                ),
            }

        query = """
        SELECT
            prd_id,
            title,
            status,
            created_at,
            approved_at,
            completed_at,
            total_tasks,
            completed_tasks,
            ROUND(100.0 * completed_tasks / NULLIF(total_tasks, 0), 1) AS pct_complete
        FROM prd_documents
        WHERE project_id = ?
        ORDER BY created_at DESC
        """

        rows = cursor.execute(query, (project_id,)).fetchall()
        prds = [dict(row) for row in rows]

        return {"project_id": project_id, "prds": prds, "count": len(prds)}

    except Exception as e:
        logger.error(f"Error getting project PRDs: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()


@router.get("/{project_id}/security")
async def get_project_security(project_id: str) -> Dict[str, Any]:
    """
    Get security findings for a specific project.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if object_exists(conn, "security_findings"):
            query = """
            SELECT
                finding_id,
                category,
                severity,
                description,
                file_path,
                start_line,
                status,
                created_at
            FROM security_findings
            WHERE project_id = ? AND COALESCE(status, 'open') NOT IN ('resolved', 'mitigated', 'false_positive')
            ORDER BY
                CASE severity
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    ELSE 4
                END,
                created_at DESC
            """
            rows = cursor.execute(query, (project_id,)).fetchall()
            findings = [
                {
                    "id": row["finding_id"],
                    "title": row["category"] or "security finding",
                    "severity": row["severity"],
                    "description": row["description"],
                    "location": (
                        f"{row['file_path']}:{row['start_line']}" if row["file_path"] else "Unknown"
                    ),
                    "status": row["status"],
                    "created_at": row["created_at"],
                }
                for row in rows
            ]
            return {
                "project_id": project_id,
                "findings": findings,
                "count": len(findings),
                "source_status": {
                    "classification": "fresh",
                    "reason": "Project security detail is read from current security_findings authority.",
                    "source_tables": ["security_findings"],
                    "derived_view": True,
                    "primary_authority": False,
                },
            }

        if not object_exists(conn, "pi_violations"):
            return {
                "project_id": project_id,
                "findings": [],
                "count": 0,
                "source_status": _empty_project_source_status(
                    ["pi_violations"],
                    reason="Project security detail table is not present in this DB snapshot.",
                ),
            }

        query = """
        SELECT
            violation_id,
            violation_type,
            severity,
            description,
            files,
            lines,
            status,
            detected_at
        FROM pi_violations
        WHERE project_id = ? AND status != 'resolved'
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'high' THEN 2
                WHEN 'medium' THEN 3
                ELSE 4
            END,
            detected_at DESC
        """

        rows = cursor.execute(query, (project_id,)).fetchall()
        findings = []

        for row in rows:
            findings.append(
                {
                    "id": row["violation_id"],
                    "title": row["violation_type"],
                    "severity": row["severity"],
                    "description": row["description"],
                    "location": f"{row['files']}:{row['lines']}" if row["files"] else "Unknown",
                    "status": row["status"],
                    "created_at": row["detected_at"],
                }
            )

        return {"project_id": project_id, "findings": findings, "count": len(findings)}

    except Exception as e:
        logger.error(f"Error getting project security: {e}")
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


@router.get("/{project_id}/dependencies")
async def get_project_dependencies(
    project_id: str, limit: int = Query(100, ge=1, le=500)
) -> Dict[str, Any]:
    """
    Get dependency graph for a specific project.
    Returns nodes and edges for visualization.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()

        if not object_exists(conn, "pi_dependencies"):
            return {
                "project_id": project_id,
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "type_counts": {},
                "source_status": _empty_project_source_status(
                    ["pi_dependencies"],
                    reason="Project dependency table is not present in this DB snapshot.",
                ),
            }

        dependency_columns = table_columns(conn, "pi_dependencies")
        if not {"from_component", "to_component"}.issubset(dependency_columns):
            return {
                "project_id": project_id,
                "nodes": [],
                "edges": [],
                "node_count": 0,
                "edge_count": 0,
                "type_counts": {},
                "source_status": _empty_project_source_status(
                    ["pi_dependencies.from_component", "pi_dependencies.to_component"],
                    reason="Project dependency table exists but lacks the required endpoint columns.",
                ),
            }

        dependency_type_expr = (
            "dependency_type"
            if "dependency_type" in dependency_columns
            else "'confirmed' AS dependency_type"
        )
        strength_expr = "strength" if "strength" in dependency_columns else "1.0 AS strength"

        # Get dependencies
        deps_query = """
        SELECT
            from_component,
            to_component,
            {dependency_type_expr},
            {strength_expr}
        FROM pi_dependencies
        WHERE project_id = ?
        LIMIT ?
        """.format(dependency_type_expr=dependency_type_expr, strength_expr=strength_expr)

        rows = cursor.execute(deps_query, (project_id, limit)).fetchall()

        # Build nodes and edges
        nodes = {}
        edges = []

        for row in rows:
            from_comp = row["from_component"]
            to_comp = row["to_component"]
            dep_type = row["dependency_type"]
            strength = row["strength"] or 1.0

            # Extract simple names
            from_name = from_comp.split(":")[-1] if ":" in from_comp else from_comp
            to_name = to_comp.split(":")[-1] if ":" in to_comp else to_comp

            # Add nodes
            if from_comp not in nodes:
                nodes[from_comp] = {"id": from_comp, "name": from_name, "type": dep_type}
            if to_comp not in nodes:
                nodes[to_comp] = {"id": to_comp, "name": to_name, "type": dep_type}

            # Add edge
            edges.append({"from": from_comp, "to": to_comp, "type": dep_type, "strength": strength})

        # Group by dependency type
        type_counts = {}
        for edge in edges:
            t = edge["type"]
            type_counts[t] = type_counts.get(t, 0) + 1

        return {
            "project_id": project_id,
            "nodes": list(nodes.values()),
            "edges": edges,
            "node_count": len(nodes),
            "edge_count": len(edges),
            "type_counts": type_counts,
        }

    except Exception as e:
        logger.error(f"Error getting project dependencies: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
