"""Shared project helpers used by multiple project intelligence route files."""

import ast
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any

from core.security.lifecycle import build_security_lifecycle_gate
from projections.api.routes.sqlite_schema import object_exists, table_columns

logger = logging.getLogger(__name__)

SENSITIVE_PATH_PARTS = {
    ".git",
    ".claude",
    ".codex",
    ".env",
    ".venv",
    "secrets",
    "credentials",
    "node_modules",
}


# ── Small utilities ──────────────────────────────────────────────────────────


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _json_list(raw: Any) -> list[Any]:
    if raw in (None, ""):
        return []
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str):
        return [raw]
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    return parsed if isinstance(parsed, list) else [parsed]


def _optional_column_expr(
    columns: set[str],
    column: str,
    *,
    table_alias: str = "p",
    alias: str | None = None,
) -> str:
    output = alias or column
    return f"{table_alias}.{column} AS {output}" if column in columns else f"NULL AS {output}"


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


# ── PRD helpers ──────────────────────────────────────────────────────────────


def _resolve_prd_file(project: dict[str, Any], file_path: str | None) -> Path | None:
    if not file_path:
        return None
    candidate = Path(file_path)
    if candidate.is_absolute():
        return candidate
    project_path = project.get("project_path")
    if not project_path:
        return None
    root = Path(str(project_path))
    if not root.is_absolute():
        root = Path.home() / "builds" / root
    return root / candidate


def _safe_prd_summary(project: dict[str, Any]) -> dict[str, Any]:
    prd_file = _resolve_prd_file(project, project.get("latest_prd_file_path"))
    if not prd_file or not prd_file.exists() or not prd_file.is_file():
        return {
            "available": False,
            "summary": "PRD content was not available from the recorded source ref.",
            "source_ref": project.get("latest_prd_file_path"),
            "safe_read": False,
        }
    lowered_parts = {part.lower() for part in prd_file.parts}
    if lowered_parts.intersection({".git", ".claude", ".codex", "secrets", "credentials"}):
        return {
            "available": False,
            "summary": "PRD path is in a sensitive or adapter-runtime area and was not read.",
            "source_ref": str(prd_file),
            "safe_read": False,
        }
    try:
        text = prd_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {
            "available": False,
            "summary": "PRD source ref could not be read.",
            "source_ref": str(prd_file),
            "safe_read": False,
        }
    lines = [
        line.strip("# ").strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("<!--")
    ]
    summary_lines = lines[:6]
    return {
        "available": True,
        "summary": " / ".join(summary_lines)[:800] if summary_lines else "PRD file exists.",
        "source_ref": str(prd_file),
        "safe_read": True,
        "line_count": len(text.splitlines()),
    }


def _build_prd_authority_status(project: dict[str, Any]) -> dict[str, Any]:
    prd_count = _as_int(project.get("prd_count"))
    latest_status = str(project.get("latest_prd_status") or "").lower()
    summary = _safe_prd_summary(project) if prd_count else None
    if not prd_count:
        status = "draft_generated"
        confidence = "low"
        reason = "No current PRD authority row is linked; the dashboard exposes an explicit draft-required state instead of inventing claims."
        manual_review_flags = ["prd_missing_current_authority"]
    elif latest_status in {"superseded", "stale", "archived"}:
        status = "stale_superseded"
        confidence = "medium"
        reason = "Latest linked PRD status indicates stale or superseded authority."
        manual_review_flags = ["prd_supersession_review"]
    elif summary and summary["available"]:
        status = "current"
        confidence = "medium"
        reason = "A linked PRD authority row and readable source ref are available."
        manual_review_flags = []
    else:
        status = "needs_update"
        confidence = "low"
        reason = "A PRD row exists but the recorded source ref is missing or unreadable."
        manual_review_flags = ["prd_source_ref_review"]
    return {
        "status": status,
        "latest_lifecycle_status": project.get("latest_prd_status"),
        "title": project.get("latest_prd_title"),
        "file_path": project.get("latest_prd_file_path"),
        "created_at": project.get("latest_prd_created_at"),
        "count": prd_count,
        "confidence": confidence,
        "reason": reason,
        "summary": (
            summary["summary"]
            if summary
            else "Draft PRD required; evidence is insufficient for product claims."
        ),
        "source_refs": (
            [project.get("latest_prd_file_path")] if project.get("latest_prd_file_path") else []
        ),
        "evidence_refs": [summary["source_ref"]] if summary and summary.get("source_ref") else [],
        "manual_review_flags": manual_review_flags,
        "derived_view": True,
        "primary_authority": False,
    }


# ── Health model ─────────────────────────────────────────────────────────────


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


# ── Project classification ───────────────────────────────────────────────────


def _default_operator_exclusion_terms(value: str) -> bool:
    lowered = value.lower()
    return any(term in lowered for term in ("pytest", "temp", "demo", "placeholder"))


def _classify_project_authority(project: dict[str, Any]) -> dict[str, Any]:
    """Classify whether a project belongs in normal operator portfolio views."""

    project_id = str(project.get("project_id") or "")
    project_name = str(project.get("project_name") or "")
    raw_path = str(project.get("project_path") or "")
    project_type = str(project.get("project_type") or "")
    project_source = str(project.get("project_source") or "")
    status = str(project.get("status") or "")
    path = Path(raw_path) if raw_path else None
    if path and not path.is_absolute():
        path = Path.home() / "builds" / path
    path_exists = bool(path and path.exists())
    path_text = str(path or raw_path)

    reasons: list[str] = []
    include_default = True
    classification = "current_legitimate_project"
    operational_classification = "local_active"
    retention_class = "current_authority"

    if not project_name:
        include_default = False
        classification = "manual_review_required"
        retention_class = "manual_review_required"
        reasons.append("project_name is missing")
    if not raw_path:
        # Registered without a path — legitimate but not tied to a local directory.
        # Show in the default operator view; badge as registered_no_path.
        # To backfill a path, call update_project_path(project_id, path) in
        # core/projects/mutations.py — it emits project.path_set for audit trail.
        classification = "registered_no_path"
        reasons.append("project has no path (registered via API without local directory)")
    elif not path_exists:
        # Path is recorded but the directory does not exist on this machine;
        # may be valid on another workstation. Keep in default view.
        classification = "path_unverified"
        reasons.append(f"project path not found locally: {path_text}")
    if status.lower() in {"inactive", "archived", "deactivated", "quarantined"}:
        include_default = False
        classification = "quarantined"
        retention_class = "retention_only"
        operational_classification = "inactive_or_quarantined"
        reasons.append(f"status is {status}")
    if _default_operator_exclusion_terms(" ".join((project_id, project_name))):
        include_default = False
        classification = "retention_only"
        retention_class = "retention_only"
        operational_classification = "excluded_test_demo_or_placeholder"
        reasons.append("project id/name/path matches test, temp, demo, or placeholder policy")
    if any(part in path_text.lower() for part in (".claude", ".codex", "worktrees")):
        include_default = False
        classification = "retention_only"
        retention_class = "retention_only"
        operational_classification = "adapter_runtime_scratch"
        reasons.append("path is adapter scratch/worktree state")
    if project_source and project_source not in {"local_builds", "current_authority"}:
        include_default = False
        classification = "retention_only"
        retention_class = "retention_only"
        operational_classification = "legacy_or_external_retained"
        reasons.append(f"project_source is {project_source}")
    if project_type and project_type not in {
        "local_first_project",
        "local_first_ai_ops",
        "external_project",
    }:
        include_default = False
        classification = "manual_review_required"
        retention_class = "manual_review_required"
        reasons.append(f"project_type is {project_type}")

    return {
        "include_in_default_operator_view": include_default,
        "classification": classification,
        "operational_classification": operational_classification,
        "retention_class": retention_class,
        "source_authority": "business_projects",
        "path_status": "confirmed" if path_exists else "unverified_missing_path",
        "reasons": reasons or ["current project path and authority record are confirmed"],
        "manual_review_required": classification == "manual_review_required",
        "derived_view": True,
        "primary_authority": False,
    }


# ── Stack JSON ───────────────────────────────────────────────────────────────


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


# ── Module runtime fit ───────────────────────────────────────────────────────


def _module_runtime_fit(
    project: dict[str, Any],
    stack_evidence: dict[str, Any],
    dependency_graph: dict[str, Any],
) -> dict[str, Any]:
    from core.module_contracts import module_contract_map
    from core.module_profiles import module_profile_map

    contracts = module_contract_map()
    profiles = module_profile_map()
    candidate_profiles = ["core"]
    reasons = ["core fits every installed Dream Studio project authority view"]
    if project.get("security_package_status", {}).get("open_findings", 0) or project.get(
        "security_lifecycle_status"
    ):
        candidate_profiles.append("security_only")
        reasons.append("security authority or lifecycle status is present")
    if stack_evidence.get("classification") == "confirmed" or dependency_graph.get("edge_count"):
        candidate_profiles.append("analytics_only")
        reasons.append("stack/dependency evidence can be consumed by analytics-only")
    if project.get("telemetry_status", {}).get("event_count") or project.get(
        "telemetry_status", {}
    ).get("validation_passed_count"):
        candidate_profiles.append("telemetry_only")
        reasons.append("telemetry or validation evidence exists")
    if project.get("project_id") == "dream-studio":
        candidate_profiles.extend(["shared_intelligence_only", "adapter_router_only", "full"])
        reasons.append(
            "Dream Studio project exposes shared-intelligence and adapter-router surfaces"
        )
    candidate_profiles = list(dict.fromkeys(candidate_profiles))
    fit_modules = [
        module_id
        for module_id, contract in contracts.items()
        if set(contract.get("install_runtime_profile_membership", [])).intersection(
            candidate_profiles
        )
    ]
    return {
        "classification": "evidence_backed_profile_fit",
        "candidate_profiles": [
            {
                "profile_id": profile_id,
                "commands": profiles.get(profile_id, {}).get("exposed_commands", []),
                "routes": profiles.get(profile_id, {}).get("exposed_routes", []),
                "docker_required": profiles.get(profile_id, {}).get("docker_required"),
                "empty_state": profiles.get(profile_id, {}).get("honest_empty_state"),
            }
            for profile_id in candidate_profiles
            if profile_id in profiles
        ],
        "fit_modules": sorted(fit_modules),
        "reasons": reasons,
        "source_refs": ["core.module_profiles", "core.module_contracts"],
        "derived_view": True,
        "primary_authority": False,
    }


# ── Validation / attention ───────────────────────────────────────────────────


def _recent_validation_state(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    if not object_exists(conn, "validation_results"):
        return {
            "classification": "unavailable",
            "reason": "validation_results table is not present.",
            "recent": [],
            "source_tables": [],
        }
    columns = table_columns(conn, "validation_results")
    validation_id = "validation_id" if "validation_id" in columns else "result_id"
    validation_type = (
        "validation_type" if "validation_type" in columns else "NULL AS validation_type"
    )
    command = "command" if "command" in columns else "NULL AS command"
    summary = "summary" if "summary" in columns else "NULL AS summary"
    evidence = (
        "evidence_refs_json" if "evidence_refs_json" in columns else "'[]' AS evidence_refs_json"
    )
    created = "created_at" if "created_at" in columns else "NULL AS created_at"
    rows = conn.execute(
        f"""
        SELECT {validation_id} AS validation_id, {validation_type}, status, {command},
               {summary}, {evidence}, {created}
        FROM validation_results
        WHERE project_id = ?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (project_id,),
    ).fetchall()
    recent = [
        {
            **dict(row),
            "evidence_refs": _json_list(row["evidence_refs_json"]),
        }
        for row in rows
    ]
    failed = sum(1 for row in recent if row.get("status") in {"failed", "error", "incomplete"})
    return {
        "classification": "fresh" if recent else "honest_empty_state",
        "recent": recent,
        "recent_count": len(recent),
        "failed_recent_count": failed,
        "source_tables": ["validation_results"],
        "derived_view": True,
        "primary_authority": False,
    }


def _attention_detail_items(conn: sqlite3.Connection, project_id: str) -> dict[str, Any]:
    if not object_exists(conn, "dashboard_attention_items"):
        return {
            "classification": "unavailable",
            "items": [],
            "source_tables": [],
        }
    columns = table_columns(conn, "dashboard_attention_items")
    attention_id = "attention_id" if "attention_id" in columns else "item_id"
    title = "title" if "title" in columns else "NULL AS title"
    summary = "summary" if "summary" in columns else "NULL AS summary"
    severity = "severity" if "severity" in columns else "NULL AS severity"
    evidence = (
        "evidence_refs_json" if "evidence_refs_json" in columns else "'[]' AS evidence_refs_json"
    )
    source_refs = (
        "source_refs_json" if "source_refs_json" in columns else "'[]' AS source_refs_json"
    )
    created = "created_at" if "created_at" in columns else "NULL AS created_at"
    rows = conn.execute(
        f"""
        SELECT {attention_id} AS attention_id, status, {severity}, {title}, {summary},
               {source_refs}, {evidence}, {created}
        FROM dashboard_attention_items
        WHERE project_id = ?
          AND COALESCE(status, 'open') NOT IN ('resolved', 'closed', 'dismissed')
        ORDER BY created_at DESC
        LIMIT 20
        """,
        (project_id,),
    ).fetchall()
    items = [
        {
            **dict(row),
            "source_refs": _json_list(row["source_refs_json"]),
            "evidence_refs": _json_list(row["evidence_refs_json"]),
        }
        for row in rows
    ]
    return {
        "classification": "fresh" if items else "honest_empty_state",
        "items": items,
        "open_count": len(items),
        "source_tables": ["dashboard_attention_items"],
        "derived_view": True,
        "primary_authority": False,
    }


# ── Component index ──────────────────────────────────────────────────────────


def _component_index(conn: sqlite3.Connection, project_id: str) -> dict[str, dict[str, Any]]:
    if not object_exists(conn, "pi_components"):
        return {}
    columns = table_columns(conn, "pi_components")
    select_cols = ["component_id"]
    for column in ("name", "path", "component_type", "lines", "complexity_score", "last_analyzed"):
        if column in columns:
            select_cols.append(column)
    rows = conn.execute(
        f"SELECT {', '.join(select_cols)} FROM pi_components WHERE project_id = ?",
        (project_id,),
    ).fetchall()
    index: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = dict(row)
        component_id = str(item.get("component_id") or "")
        if component_id:
            index[component_id] = {
                **item,
                "evidence_refs": [item.get("path")] if item.get("path") else [],
                "source_tables": ["pi_components"],
                "confirmation_status": "confirmed_component_record",
            }
    return index


# ── Surface availability ─────────────────────────────────────────────────────


def _missing_tables(conn: sqlite3.Connection, names: list[str]) -> list[str]:
    return [name for name in names if not object_exists(conn, name)]


def _empty_project_source_status(missing: list[str], *, reason: str) -> dict[str, Any]:
    return {
        "classification": "empty by design",
        "reason": reason,
        "missing": missing,
        "derived_view": True,
        "primary_authority": False,
    }


def _project_surface_availability(conn: sqlite3.Connection) -> dict[str, bool]:
    dependency_columns = (
        table_columns(conn, "pi_dependencies") if object_exists(conn, "pi_dependencies") else []
    )
    return {
        "overview": True,
        "prds": object_exists(conn, "prd_documents"),
        "security": any(
            object_exists(conn, name)
            for name in ("findings_current_status", "security_events", "pi_violations")
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


def _project_row_for_authority(conn: sqlite3.Connection, project_id: str) -> dict[str, Any] | None:
    # business_projects is Store 3 authority in studio.db — always read directly.
    if not object_exists(conn, "business_projects"):
        return None
    row = conn.execute(
        "SELECT project_id, name AS project_name, description, status, project_path,"
        " total_sessions, total_tokens, last_session_at, created_at, updated_at"
        " FROM business_projects WHERE project_id = ? LIMIT 1",
        (project_id,),
    ).fetchone()
    return dict(row) if row else None


def _unavailable_project_surfaces(availability: dict[str, bool]) -> list[str]:
    return [name for name, available in availability.items() if not available]


# ── Dashboard decoration ─────────────────────────────────────────────────────


def _decorate_project_for_dashboard(project: dict[str, Any]) -> dict[str, Any]:
    stack = _parse_stack_json(project.get("stack_json"))
    dependencies = stack.get("dependencies") if isinstance(stack.get("dependencies"), list) else []
    config_files = stack.get("config_files") if isinstance(stack.get("config_files"), list) else []
    entry_points = stack.get("entry_points") if isinstance(stack.get("entry_points"), list) else []
    path_exists = _project_path_exists(project.get("project_path"))
    framework = project.get("stack_detected") or stack.get("framework")
    project["path_status"] = "confirmed" if path_exists else "unverified_missing_path"
    project["project_authority_status"] = _classify_project_authority(project)
    project["authority_source"] = {
        "source_table": "business_projects",
        "source_authority": "current_project_registry",
        "derived_view": True,
        "primary_authority": False,
    }
    project["stack_evidence"] = {
        "classification": (
            "confirmed" if framework and framework != "unknown" else "honest_empty_state"
        ),
        "framework": framework or "unknown",
        "dependency_count": len(dependencies),
        "config_files": config_files[:8],
        "entry_points": entry_points[:8],
        "source_tables": ["business_projects"],
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
    prd_authority = _build_prd_authority_status(project)
    project["prd_status"] = {
        "count": _as_int(project.get("prd_count")),
        "latest_status": prd_status,
        "latest_title": project.get("latest_prd_title"),
        "latest_file_path": project.get("latest_prd_file_path"),
        "status": prd_authority["status"],
        "classification": prd_authority["status"],
        "authority": prd_authority,
        "source_tables": ["prd_documents"],
        "derived_view": True,
        "primary_authority": False,
    }
    project["security_package_status"] = {
        "open_findings": _as_int(project.get("security_open_count")),
        "classification": "fresh" if _as_int(project.get("security_open_count")) else "fresh_empty",
        "source_tables": ["findings"],
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
        # dashboard_attention_items: dropped migration 139 (WO-AI-SPINE, AD-5) — attention_open
        # above already reads 0 via object_exists() guards in project_list.py; this static
        # label list should not claim a source table that no longer exists.
        "source_tables": ["route_decision_records"],
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


# ── Detail-page helpers ──────────────────────────────────────────────────────


def _finding_summary(findings: list[dict[str, Any]], open_findings: int) -> dict[str, Any]:
    summary: dict[str, int] = {}
    for finding in findings:
        key = f"{finding.get('severity', 'unknown')}:{finding.get('status', 'unknown')}"
        summary[key] = summary.get(key, 0) + 1
    if open_findings:
        summary["security_open:open"] = int(open_findings)
    return {
        "counts": summary,
        "security_open_findings": open_findings,
        "production_readiness_finding_count": len(findings),
    }


def _collect_evidence_refs(controls: list[dict[str, Any]]) -> list[str]:
    refs: set[str] = set()
    for control in controls:
        evidence = control.get("evidence_refs") or control.get("evidence_refs_json") or []
        if isinstance(evidence, str):
            try:
                evidence = json.loads(evidence)
            except json.JSONDecodeError:
                evidence = [evidence]
        refs.update(str(item) for item in evidence if item)
    return sorted(refs)


def _project_detail_known_gaps(
    health_payload: dict[str, Any],
    production_readiness: dict[str, Any],
) -> list[str]:
    gaps: list[str] = []
    project = health_payload.get("project", {})
    prd_authority = (project.get("prd_status") or {}).get("authority") or {}
    if prd_authority.get("status") != "current":
        gaps.append(f"prd_status:{prd_authority.get('status', 'unknown')}")
    if production_readiness.get("status") == "unavailable":
        gaps.append("production_readiness_assessment_missing")
    dependency_status = project.get("dependency_source_status") or {}
    if dependency_status.get("classification") != "confirmed":
        gaps.append("confirmed_dependency_graph_unavailable")
    if project.get("health_model", {}).get("status") != "scored":
        gaps.append("health_score_unavailable")
    return gaps


def _project_detail_next_action(
    health_payload: dict[str, Any],
    production_readiness: dict[str, Any],
) -> str:
    gaps = _project_detail_known_gaps(health_payload, production_readiness)
    if "production_readiness_assessment_missing" in gaps:
        return "Run or persist a project-scoped production readiness assessment when approved."
    if any(gap.startswith("prd_status:") for gap in gaps):
        return "Review or update PRD authority before release planning."
    if "confirmed_dependency_graph_unavailable" in gaps:
        return "Collect confirmed dependency evidence before drawing a Knowledge Graph."
    return "Continue with the next evidence-backed Work Order."


# ── DB connection helpers ────────────────────────────────────────────────────


def get_db_path() -> str:
    """Get database path"""
    from core.config.database import get_db_path as _canonical

    return str(_canonical())


def get_db_connection():
    """Get database connection with row factory"""
    import sqlite3 as _sqlite3

    from core.config.database import get_connection

    conn = get_connection()
    conn.row_factory = _sqlite3.Row
    return conn


# ── Active project filter ────────────────────────────────────────────────────


def _active_project_where(conn) -> str:
    """Filter out quarantined/temp project records.

    reg_projects deleted in migration 084; this function is retained for callers
    that have not yet been updated. Returns a WHERE clause for business_projects.
    """
    # business_projects: status IN ('active', 'paused', 'deleted') — exclude deleted
    return "p.status != 'deleted'"
