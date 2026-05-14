"""Planning-only personal installed-state cutover rehearsal documents."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from core.upgrade.evidence_reconciliation import INSTALLED_STATE_PATH, LIVE_DB_PATH
from core.upgrade.installed_state_rehydration import assert_rehearsal_write_target

PLAN_DOCUMENT_NAMES = (
    "cutover_plan",
    "backup_plan",
    "rollback_plan",
    "validation_checklist",
    "approval_gates",
)


def build_personal_state_cutover_rehearsal_plan(
    *,
    repo_path: Path,
    installed_state_path: Path = INSTALLED_STATE_PATH,
    live_db_path: Path = LIVE_DB_PATH,
    rehearsal_state_path: Path,
) -> dict[str, Any]:
    """Build non-executing cutover rehearsal plans for the operator installed state."""

    rehearsal_target = assert_rehearsal_write_target(
        rehearsal_state_path,
        live_state_path=installed_state_path,
    )
    backup_root = rehearsal_target / "backups"
    dry_run_root = rehearsal_target / "dry-run"
    return {
        "artifact_type": "personal_state_cutover_rehearsal_plan",
        "planning_only": True,
        "executes_cutover": False,
        "executes_cleanup": False,
        "live_mutation_allowed": False,
        "repo_path": str(Path(repo_path)),
        "installed_state_path": str(Path(installed_state_path)),
        "live_db_path": str(Path(live_db_path)),
        "rehearsal_state_path": str(rehearsal_target),
        "documents": {
            "cutover_plan": _cutover_plan(
                repo_path, installed_state_path, live_db_path, rehearsal_target
            ),
            "backup_plan": _backup_plan(installed_state_path, live_db_path, backup_root),
            "rollback_plan": _rollback_plan(installed_state_path, live_db_path, backup_root),
            "validation_checklist": _validation_checklist(rehearsal_target, dry_run_root),
            "approval_gates": _approval_gates(),
        },
    }


def validate_cutover_rehearsal_plan(plan: Mapping[str, Any]) -> list[str]:
    """Validate that a cutover rehearsal plan is planning-only and gated."""

    errors: list[str] = []
    if plan.get("planning_only") is not True:
        errors.append("cutover plan must be planning-only")
    if plan.get("executes_cutover") is not False:
        errors.append("cutover execution must be forbidden")
    if plan.get("executes_cleanup") is not False:
        errors.append("cleanup execution must be forbidden")
    if plan.get("live_mutation_allowed") is not False:
        errors.append("live mutation must be forbidden")
    documents = plan.get("documents", {})
    for name in PLAN_DOCUMENT_NAMES:
        if name not in documents:
            errors.append(f"missing plan document: {name}")
    gates = documents.get("approval_gates", {}).get("gates", [])
    gate_names = {gate.get("gate") for gate in gates if isinstance(gate, Mapping)}
    required_gates = {
        "final_repo_build_readiness",
        "full_backup",
        "restore_rehearsal_result",
        "rehearsal_rehydration_result",
        "live_cutover",
        "cleanup_manifest",
        "deletion_archive_compaction",
    }
    missing_gates = required_gates - gate_names
    if missing_gates:
        errors.append(f"missing approval gates: {', '.join(sorted(missing_gates))}")
    cleanup_strategy = documents.get("cutover_plan", {}).get("cleanup_approval_strategy", {})
    if cleanup_strategy.get("cleanup_execution_allowed_now") is not False:
        errors.append("cleanup must remain a separate approval boundary")
    return errors


def _cutover_plan(
    repo_path: Path, installed_state_path: Path, live_db_path: Path, rehearsal_state_path: Path
) -> dict[str, Any]:
    return {
        "pre_cutover_freeze": [
            "Pause or stop running Dream Studio processes before any future live cutover.",
            "Warn about open files, active sessions, and pending writes.",
            "Freeze database writes before final backup.",
            "Require final backup evidence before live mutation approval.",
        ],
        "repo_build_update_strategy": {
            "repo_build_path": str(Path(repo_path)),
            "installed_state_remains": str(Path(installed_state_path)),
            "runtime_code_strategy": "future cutover must either point launch/import paths to the finished repo checkout or use a reviewed copy/sync step",
            "canonical_state_resolution": "repo code must read user-local state through canonical path resolution",
            "duplicate_authority_db_allowed": False,
            "execute_now": False,
        },
        "rehydration_execution_strategy": {
            "input_installed_state_path": str(Path(installed_state_path)),
            "input_live_db_path": str(Path(live_db_path)),
            "rehearsal_state_path": str(rehearsal_state_path),
            "dry_run_output_path": str(rehearsal_state_path / "dry-run"),
            "mapping_output_path": str(
                rehearsal_state_path / "dry-run" / "rehydration_mapping.yaml"
            ),
            "cleanup_manifest_draft_path": str(
                rehearsal_state_path / "dry-run" / "cleanup_manifest_draft.yaml"
            ),
            "validation_output_path": str(
                rehearsal_state_path / "dry-run" / "validation_summary.yaml"
            ),
            "no_live_mutation_guard_required": True,
            "expected_categories": [
                "projects",
                "milestones",
                "work_orders",
                "approvals",
                "decisions",
                "research",
                "security_findings",
                "validations_evals",
                "token_usage",
                "skills",
                "workflows",
                "hooks_tools",
                "reports_prompts",
                "dashboard_projection_data",
                "backups_archives_caches_logs",
            ],
        },
        "cleanup_approval_strategy": {
            "cleanup_execution_allowed_now": False,
            "separate_later_approval_boundary": True,
            "categories": [
                "keep",
                "rehydrate",
                "archive_candidate",
                "deduplicate_candidate",
                "delete_candidate",
                "manual_review_required",
                "unknown_defer",
            ],
            "future_item_required_fields": [
                "path_or_table_or_category",
                "reason",
                "confidence",
                "risk",
                "source_evidence",
                "dependency_on_successful_rehydration",
                "human_approval_required",
            ],
        },
        "dashboard_runtime_validation_strategy": [
            "Validate route-first behavior.",
            "Validate telemetry emitters.",
            "Validate telemetry read models.",
            "Validate dashboard/API/feed if implemented.",
            "Validate SQLite path resolution points at user-local installed state.",
            "Validate no handoff loop regression.",
            "Validate no duplicate authority database exists.",
            "Validate evidence refs are present.",
        ],
    }


def _backup_plan(
    installed_state_path: Path, live_db_path: Path, backup_root: Path
) -> dict[str, Any]:
    return {
        "backup_root": str(backup_root),
        "requires_timestamped_directory": True,
        "backup_targets": [
            str(Path(installed_state_path)),
            str(Path(live_db_path)),
            str(Path(installed_state_path) / "meta" / "audit"),
            str(Path(installed_state_path) / "meta" / "work-orders"),
            "reports/prompts/artifacts under installed state when classified non-sensitive",
            "current config and launch/runtime scripts if present",
        ],
        "required_evidence": [
            "backup_path",
            "timestamp",
            "file_manifest",
            "db_schema_version",
            "db_schema_fingerprint",
            "file_count",
            "total_size",
            "restore_rehearsal_result",
        ],
        "secret_sensitive_policy": "Do not extract or expose secret values; classify unknown sensitive files for manual review.",
        "execute_now": False,
    }


def _rollback_plan(
    installed_state_path: Path, live_db_path: Path, backup_root: Path
) -> dict[str, Any]:
    return {
        "backup_root": str(backup_root),
        "steps": [
            "Stop the new runtime immediately.",
            "Preserve failed cutover logs/evidence outside the restored live state.",
            f"Restore full installed state backup to {Path(installed_state_path)}.",
            f"Restore live SQLite DB backup to {Path(live_db_path)}.",
            "Verify DB schema version and table counts.",
            "Verify launch/runtime behavior.",
            "Record rollback evidence.",
        ],
        "execute_now": False,
    }


def _validation_checklist(rehearsal_state_path: Path, dry_run_root: Path) -> dict[str, Any]:
    return {
        "rehearsal_state_path": str(rehearsal_state_path),
        "dry_run_root": str(dry_run_root),
        "gates": [
            "repo_status_clean",
            "installed_state_backup_complete",
            "backup_restore_rehearsal_passed",
            "rehydration_dry_run_passed",
            "rehearsal_rehydration_passed",
            "cleanup_manifest_generated_not_executed",
            "dashboard_read_model_queries_pass_on_rehearsal_state",
            "no_hardcoded_operator_path_in_repo_source",
            "no_duplicate_authority_db_created",
            "no_live_state_mutation_before_approval",
            "rollback_instructions_verified",
        ],
    }


def _approval_gates() -> dict[str, Any]:
    return {
        "gates": [
            {"gate": "final_repo_build_readiness", "operator_approval_required": True},
            {"gate": "full_backup", "operator_approval_required": True},
            {"gate": "restore_rehearsal_result", "operator_approval_required": True},
            {"gate": "rehearsal_rehydration_result", "operator_approval_required": True},
            {"gate": "live_cutover", "operator_approval_required": True},
            {"gate": "cleanup_manifest", "operator_approval_required": True},
            {"gate": "deletion_archive_compaction", "operator_approval_required": True},
        ],
        "prompt_required_now": False,
        "handoff_required_now": False,
    }
