"""Project authority classification (default operator view eligibility).

WO-GF-API-ROUTES: split out of project_helpers.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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
