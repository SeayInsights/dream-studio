"""Dashboard decoration and project-detail-page helpers.

WO-GF-API-ROUTES: split out of project_helpers.py.
"""

from __future__ import annotations

import json
from typing import Any

from core.security.lifecycle import build_security_lifecycle_gate

from .project_helpers_classification import _classify_project_authority
from .project_helpers_health import _build_health_model
from .project_helpers_prd import _build_prd_authority_status
from .project_helpers_utils import _as_int, _parse_stack_json, _project_path_exists

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
