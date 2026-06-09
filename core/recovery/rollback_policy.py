"""Non-destructive failure recovery and rollback planning."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

FAILURE_TYPES = frozenset(
    {
        "failed_validation",
        "failed_work_order",
        "corrupted_state",
        "interrupted_run",
        "rollback_uncertainty",
    }
)


def build_failure_recovery_plan(
    *,
    failure_type: str,
    evidence_refs: Sequence[str] = (),
    backup_refs: Sequence[str] = (),
    validation_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a recovery plan without executing rollback or cleanup."""

    normalized = failure_type if failure_type in FAILURE_TYPES else "rollback_uncertainty"
    return {
        "plan_type": "failure_recovery_rollback",
        "failure_type": normalized,
        "derived_view": True,
        "primary_authority": False,
        "rollback_executed": False,
        "cleanup_executed": False,
        "live_state_mutation_required": False,
        "evidence_refs": [str(ref) for ref in evidence_refs],
        "backup_refs": [str(ref) for ref in backup_refs],
        "validation_refs": [str(ref) for ref in validation_refs],
        "steps": _steps_for_failure(normalized),
        "route_decision": _route_for_failure(normalized, backup_refs, validation_refs),
        "preservation_requirements": [
            "preserve_failed_run_logs",
            "preserve_validation_output",
            "preserve_pre_failure_boundary",
            "record_post_failure_boundary",
            "do_not_delete_or_compact_evidence",
        ],
    }


def validate_failure_recovery_plan(plan: Mapping[str, Any]) -> list[str]:
    """Return safety/completeness violations for a recovery plan."""

    issues: list[str] = []
    if _truthy(plan.get("rollback_executed")):
        issues.append("rollback_must_not_execute_in_plan")
    if _truthy(plan.get("cleanup_executed")):
        issues.append("cleanup_must_not_execute_in_plan")
    if _truthy(plan.get("live_state_mutation_required")):
        issues.append("plan_must_not_require_live_state_mutation")
    if not plan.get("evidence_refs"):
        issues.append("evidence_refs_required")
    if not plan.get("steps"):
        issues.append("recovery_steps_required")
    return issues


def _steps_for_failure(failure_type: str) -> list[dict[str, str]]:
    common = [
        {"step": "freeze_current_state", "mode": "non_destructive"},
        {"step": "capture_failure_evidence", "mode": "read_only"},
        {"step": "classify_recovery_route", "mode": "planning_only"},
    ]
    if failure_type == "corrupted_state":
        common.append({"step": "verify_backup_before_restore", "mode": "read_only"})
    if failure_type == "interrupted_run":
        common.append({"step": "resume_from_last_file_backed_checkpoint", "mode": "planning_only"})
    common.append({"step": "validate_recovery_before_mutation", "mode": "read_only"})
    return common


def _route_for_failure(
    failure_type: str,
    backup_refs: Sequence[str],
    validation_refs: Sequence[str],
) -> dict[str, Any]:
    if failure_type in {"corrupted_state", "rollback_uncertainty"} and not backup_refs:
        return {
            "route_decision": "hard_stop",
            "operator_action_required": True,
            "reason": "backup_reference_required_before_recovery",
        }
    if failure_type == "failed_validation" and validation_refs:
        return {
            "route_decision": "continue_internal",
            "operator_action_required": False,
            "reason": "validation_evidence_available_for_remediation",
        }
    return {
        "route_decision": "require_operator_approval",
        "operator_action_required": True,
        "reason": "recovery_boundary_requires_review",
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "present"}
    return bool(value)
