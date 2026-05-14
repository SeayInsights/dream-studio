"""Draft cleanup manifest generation for installed-state upgrade rehearsal."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CLEANUP_CATEGORIES = (
    "keep",
    "rehydrate",
    "archive_candidate",
    "deduplicate_candidate",
    "delete_candidate",
    "manual_review_required",
    "unknown_defer",
)


def draft_cleanup_manifest(
    reconciliation: Mapping[str, Any],
    *,
    installed_state_path: Path | None = None,
) -> dict[str, Any]:
    """Create a non-executable cleanup manifest draft from reconciliation gaps."""

    sources = {
        source.get("category"): source
        for source in reconciliation.get("evidence_sources", [])
        if isinstance(source, Mapping)
    }
    state_path = installed_state_path or Path(
        reconciliation.get("installed_state_path", Path.home() / ".dream-studio")
    )
    live_db_path = state_path / "state" / "studio.db"
    items = [
        _item(
            "keep",
            str(live_db_path),
            "Installed SQLite state is valuable runtime authority and must be preserved before any cutover.",
            "high",
            "high",
            ["install_bootstrap", "database_authority"],
            human_review_required=True,
            depends_on_rehearsal=True,
        ),
        _item(
            "rehydrate",
            "SQLite telemetry and canonical authority records",
            "Structured facts should map into current telemetry/canonical tables during rehearsal.",
            "high",
            "medium",
            ["database_authority", "dashboard_read_models"],
            human_review_required=True,
            depends_on_rehearsal=True,
        ),
        _item(
            "rehydrate",
            "research cache and decision artifacts",
            "Research and decisions have target telemetry tables and should be preserved into records/evidence refs.",
            "medium",
            "medium",
            ["research_decision_bridge"],
            human_review_required=True,
            depends_on_rehearsal=True,
        ),
        _item(
            "rehydrate",
            "security findings and validation history",
            "Security and validation evidence have file/line/status/outcome targets in telemetry tables.",
            "medium",
            "high",
            ["security_bridge", "dashboard_read_models"],
            human_review_required=True,
            depends_on_rehearsal=True,
        ),
        _item(
            "deduplicate_candidate",
            "legacy dashboard/projection outputs",
            "Dashboard projections are derived views and should not become primary authority.",
            "medium",
            "medium",
            ["dashboard_read_models"],
            human_review_required=True,
            depends_on_rehearsal=True,
        ),
        _item(
            "archive_candidate",
            "old prompts/reports superseded by structured records",
            "Reports/prompts can remain evidence or become archive candidates after source refs are preserved.",
            "medium",
            "medium",
            ["integration_matrix"],
            human_review_required=True,
            depends_on_rehearsal=True,
        ),
        _item(
            "manual_review_required",
            "filesystem folders without current topology manifest",
            "Expected topology manifests were not found, so broad folder cleanup is unsafe without later manifest-backed review.",
            "high",
            "low",
            ["topology_manifests"],
            human_review_required=True,
            depends_on_rehearsal=False,
        ),
        _item(
            "unknown_defer",
            "delete candidates",
            "No deletion is approved and no deletion candidate can be promoted without an approved cleanup manifest.",
            "high",
            "high",
            ["install_bootstrap"],
            human_review_required=True,
            depends_on_rehearsal=True,
        ),
    ]
    if not sources.get("topology_manifests", {}).get("present", False):
        items.append(
            _item(
                "unknown_defer",
                "runtime/manifests/*.json",
                "Named topology manifests were absent; do not infer cleanup from missing manifests.",
                "medium",
                "low",
                ["existing_evidence_reconciliation"],
                human_review_required=True,
                depends_on_rehearsal=False,
            )
        )
    return {
        "artifact_type": "cleanup_gap_manifest_draft",
        "executable": False,
        "cleanup_execution_allowed": False,
        "categories": list(CLEANUP_CATEGORIES),
        "items": items,
    }


def validate_cleanup_manifest(manifest: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("cleanup_execution_allowed") is not False:
        errors.append("cleanup execution must be forbidden")
    for item in manifest.get("items", []):
        if item.get("category") not in CLEANUP_CATEGORIES:
            errors.append(f"invalid cleanup category: {item.get('category')}")
        if item.get("human_review_required") is not True:
            errors.append(f"human review required for cleanup item: {item.get('path_or_category')}")
    return errors


def _item(
    category: str,
    path_or_category: str,
    reason: str,
    risk_level: str,
    confidence: str,
    source_evidence: Sequence[str],
    *,
    human_review_required: bool,
    depends_on_rehearsal: bool,
) -> dict[str, Any]:
    return {
        "category": category,
        "path_or_category": path_or_category,
        "reason": reason,
        "confidence": confidence,
        "source_evidence": list(source_evidence),
        "risk_level": risk_level,
        "human_review_required": human_review_required,
        "depends_on_successful_rehearsal_rehydration": depends_on_rehearsal,
    }
