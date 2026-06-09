"""Rehearsal-safe rehydration planning for an installed Dream Studio state."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.upgrade.cleanup_manifest import draft_cleanup_manifest, validate_cleanup_manifest
from core.upgrade.evidence_reconciliation import (
    INSTALLED_STATE_PATH,
    LIVE_DB_PATH,
    reconcile_existing_evidence,
    validate_evidence_reconciliation,
)

REHYDRATION_DOMAINS: tuple[dict[str, Any], ...] = (
    {
        "source_domain": "projects",
        "target_domain": "project registry and project authority records",
        "target_tables": ["reg_projects", "authority_projection_records"],
        "source_evidence": ["database_authority", "install_bootstrap"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "milestones",
        "target_domain": "milestone/progress state and route records",
        "target_tables": ["route_decision_records", "authority_projection_records"],
        "source_evidence": ["dashboard_read_models", "integration_matrix"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "work_orders",
        "target_domain": "work-order records and evidence refs",
        "target_tables": ["artifact_records", "route_decision_records", "outcome_records"],
        "source_evidence": ["integration_matrix"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "approvals",
        "target_domain": "approval records/artifacts",
        "target_tables": ["canonical_approvals", "canonical_approval_scopes"],
        "source_evidence": ["database_authority"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "decisions",
        "target_domain": "decision_records and canonical decisions",
        "target_tables": ["decision_records", "decision_log"],
        "source_evidence": ["research_decision_bridge"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "research",
        "target_domain": "research_evidence_records and research cache",
        "target_tables": ["research_evidence_records"],
        "source_evidence": ["research_decision_bridge"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "findings",
        "target_domain": "findings with file/line/severity/status",
        "target_tables": ["findings", "dashboard_attention_items"],
        "source_evidence": ["security_bridge"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "validations_evals",
        "target_domain": "validation_results and outcome_records",
        "target_tables": ["validation_results", "outcome_records"],
        "source_evidence": ["dashboard_read_models", "integration_matrix"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "token_usage",
        "target_domain": "token_usage_records",
        "target_tables": ["token_usage_records"],
        "source_evidence": ["dashboard_read_models", "integration_matrix"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "skills",
        "target_domain": "skill_invocations",
        "target_tables": ["skill_invocations"],
        "source_evidence": ["integration_matrix"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "workflows",
        "target_domain": "workflow_invocations",
        "target_tables": ["workflow_invocations"],
        "source_evidence": ["research_decision_bridge", "integration_matrix"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "hooks_tools",
        "target_domain": "hook_invocations and tool_invocations",
        "target_tables": ["hook_invocations", "tool_invocations"],
        "source_evidence": ["integration_matrix"],
        "status": "map_in_rehearsal",
    },
    {
        "source_domain": "reports_prompts",
        "target_domain": "artifact_records or archive candidates",
        "target_tables": ["artifact_records"],
        "source_evidence": ["integration_matrix"],
        "status": "manual_review_before_cleanup",
    },
    {
        "source_domain": "dashboard_projection_data",
        "target_domain": "derived read-model state or stale/superseded records",
        "target_tables": ["authority_projection_records"],
        "source_evidence": ["dashboard_read_models"],
        "status": "deduplicate_after_rehearsal",
    },
    {
        "source_domain": "backups_archives_caches_logs",
        "target_domain": "keep/archive/deduplicate/manual-review categories",
        "target_tables": [],
        "source_evidence": ["install_bootstrap"],
        "status": "manual_review_required",
    },
)


class LiveStateWriteError(ValueError):
    """Raised when tooling is asked to write to the live installed state."""


def assert_rehearsal_write_target(
    path: Path, *, live_state_path: Path = INSTALLED_STATE_PATH
) -> Path:
    """Reject live installed-state write targets and require an explicit rehearsal path."""

    target = Path(path).resolve()
    live = Path(live_state_path).resolve()
    if target == live or live in target.parents:
        raise LiveStateWriteError(f"refusing to write inside live installed state: {target}")
    return target


def build_rehydration_gap_plan(reconciliation: Mapping[str, Any]) -> dict[str, Any]:
    """Create a gap-only rehydration mapping plan from reconciled evidence."""

    return {
        "artifact_type": "rehydration_gap_plan",
        "live_state_path": str(INSTALLED_STATE_PATH),
        "live_db_path": str(LIVE_DB_PATH),
        "live_mutation_allowed": False,
        "rehearsal_required_before_cutover": True,
        "mapping_domains": list(REHYDRATION_DOMAINS),
        "remaining_gaps": list(reconciliation.get("remaining_gaps", [])),
        "next_validation_step": "validate_rehydration_tooling_against_rehearsal_copy",
    }


def build_validation_summary(
    *,
    reconciliation: Mapping[str, Any],
    rehydration_plan: Mapping[str, Any],
    cleanup_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    errors = []
    errors.extend(validate_evidence_reconciliation(reconciliation))
    errors.extend(validate_cleanup_manifest(cleanup_manifest))
    if rehydration_plan.get("live_mutation_allowed") is not False:
        errors.append("rehydration plan must forbid live mutation")
    if not rehydration_plan.get("mapping_domains"):
        errors.append("rehydration mapping domains are required")
    return {
        "artifact_type": "rehydration_tooling_validation_summary",
        "valid": not errors,
        "errors": errors,
        "dry_run_supported": True,
        "rehearsal_mode_supported": True,
        "live_write_guard_supported": True,
        "broad_inventory_repeated": False,
    }


def plan_from_existing_evidence(*, rehearsal_output_path: Path | None = None) -> dict[str, Any]:
    """Build all planning artifacts from existing evidence without touching live state."""

    if rehearsal_output_path is not None:
        assert_rehearsal_write_target(rehearsal_output_path)
    reconciliation = reconcile_existing_evidence()
    rehydration_plan = build_rehydration_gap_plan(reconciliation)
    cleanup_manifest = draft_cleanup_manifest(reconciliation)
    validation = build_validation_summary(
        reconciliation=reconciliation,
        rehydration_plan=rehydration_plan,
        cleanup_manifest=cleanup_manifest,
    )
    return {
        "dry_run": True,
        "rehearsal_output_path": str(rehearsal_output_path) if rehearsal_output_path else None,
        "reconciliation": reconciliation,
        "rehydration_plan": rehydration_plan,
        "cleanup_manifest": cleanup_manifest,
        "validation": validation,
    }
