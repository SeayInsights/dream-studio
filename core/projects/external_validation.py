"""Planning-only external project validation pipeline helpers.

External target work must remain explicit, evidence-backed, and approval-gated.
This module creates a reusable validation plan from registry metadata without
opening, scanning, or mutating the target repository.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.projects.paused_targets import (
    ROUTE_KEEP_PAUSED,
    ROUTE_RESUME_AFTER_OPERATOR_APPROVAL,
    classify_project_target,
)

PIPELINE_MODE_PLANNING_ONLY = "planning_only"
PIPELINE_MODE_READ_ONLY_VALIDATION = "read_only_validation"

DIRTY_STATE_CLEAN = "clean"
DIRTY_STATE_DIRTY = "dirty"
DIRTY_STATE_UNKNOWN = "unknown"

DEFAULT_SEQUENCE = (
    "capture_target_boundary",
    "classify_dirty_state",
    "verify_approval_scope",
    "run_read_only_validation",
    "record_target_repo_mutation_eval",
    "record_validation_evidence",
    "route_next_decision",
)


def build_external_project_validation_pipeline(
    target: Mapping[str, Any],
    *,
    requested_checks: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build a non-executing external validation pipeline plan.

    The returned plan is a derived view.  It says what should happen in a future
    approved validation Work Order; it does not perform validation, inspect the
    target repo, stage files, commit, push, or approve mutation.
    """

    policy = classify_project_target(target)
    dirty_state = _normal_dirty_state(target.get("dirty_state"))
    checks = tuple(_sequence_text(requested_checks or target.get("requested_checks")))
    refs = tuple(_sequence_text(evidence_refs or target.get("source_evidence_refs")))
    approval_refs = tuple(
        _sequence_text(target.get("operator_approval_refs") or target.get("approval_refs"))
    )

    mode = (
        PIPELINE_MODE_READ_ONLY_VALIDATION
        if policy["recommended_route"] == ROUTE_RESUME_AFTER_OPERATOR_APPROVAL
        else PIPELINE_MODE_PLANNING_ONLY
    )
    requires_operator_approval = (
        policy["recommended_route"] == ROUTE_KEEP_PAUSED or not approval_refs
    )
    commit_allowed = False
    commit_policy = _commit_policy(dirty_state=dirty_state, approval_refs=approval_refs)
    work_orders = _work_order_sequence(
        target_id=str(policy["target_id"]),
        checks=checks,
        mode=mode,
        dirty_state=dirty_state,
        requires_operator_approval=requires_operator_approval,
    )

    return {
        "derived_view": True,
        "primary_authority": False,
        "pipeline_mode": mode,
        "target_policy": policy,
        "dirty_state": dirty_state,
        "requested_checks": list(checks),
        "work_order_sequence": work_orders,
        "validation_profile": {
            "profile_id": policy["validation_profile"],
            "allowed_modes": ["read_only", "dry_run"],
            "forbidden_modes": ["mutation", "cleanup", "push", "deploy"],
            "requires_temp_or_rehearsal_outputs": True,
        },
        "evidence_requirements": [
            "target_boundary_snapshot",
            "dirty_state_snapshot",
            "approval_scope",
            "validation_output",
            "target_repo_mutation_eval",
            "route_decision",
        ],
        "commit_policy": commit_policy,
        "source_evidence_refs": list(refs),
        "operator_approval_refs": list(approval_refs),
        "execution_allowed": False,
        "external_repo_inspected": False,
        "external_repo_mutated": False,
        "requires_operator_approval": requires_operator_approval,
    }


def validate_external_project_validation_pipeline(plan: Mapping[str, Any]) -> list[str]:
    """Return invariant violations for an external validation pipeline plan."""

    issues: list[str] = []
    if not _truthy(plan.get("derived_view")):
        issues.append("pipeline_must_be_derived_view")
    if _truthy(plan.get("primary_authority")):
        issues.append("pipeline_must_not_be_primary_authority")
    if _truthy(plan.get("execution_allowed")):
        issues.append("pipeline_must_not_execute_by_default")
    if _truthy(plan.get("external_repo_mutated")):
        issues.append("external_repo_mutation_forbidden")
    if _truthy(plan.get("external_repo_inspected")):
        issues.append("external_repo_inspection_not_part_of_plan_generation")

    commit_policy = _mapping(plan.get("commit_policy"))
    if _truthy(commit_policy.get("commit_allowed")):
        issues.append("commit_must_not_be_allowed_in_validation_plan")
    if not plan.get("work_order_sequence"):
        issues.append("work_order_sequence_required")
    if "target_repo_mutation_eval" not in set(_sequence_text(plan.get("evidence_requirements"))):
        issues.append("target_repo_mutation_eval_required")
    return issues


def _work_order_sequence(
    *,
    target_id: str,
    checks: Sequence[str],
    mode: str,
    dirty_state: str,
    requires_operator_approval: bool,
) -> list[dict[str, Any]]:
    work_orders: list[dict[str, Any]] = []
    for index, step in enumerate(DEFAULT_SEQUENCE, start=1):
        work_orders.append(
            {
                "id": f"{target_id}-{index:02d}-{step}",
                "step": step,
                "mode": mode,
                "target_id": target_id,
                "requested_checks": list(checks),
                "dirty_state": dirty_state,
                "requires_operator_approval": requires_operator_approval
                and step in {"verify_approval_scope", "run_read_only_validation"},
                "mutation_allowed": False,
            }
        )
    return work_orders


def _commit_policy(*, dirty_state: str, approval_refs: Sequence[str]) -> dict[str, Any]:
    if dirty_state == DIRTY_STATE_DIRTY:
        reason = "target_dirty_state_requires_review"
    elif not approval_refs:
        reason = "operator_approval_required_before_target_commit"
    else:
        reason = "validation_pipeline_is_read_only"
    return {
        "commit_allowed": False,
        "stage_allowed": False,
        "push_allowed": False,
        "reason": reason,
        "future_commit_requires": [
            "explicit mutation Work Order",
            "clean or reviewed dirty-state evidence",
            "target_repo_mutation_eval pass",
            "operator approval for staging and commit",
        ],
    }


def _normal_dirty_state(value: Any) -> str:
    dirty_state = str(value).strip().lower() if value is not None else ""
    if dirty_state in {"clean", "no_changes"}:
        return DIRTY_STATE_CLEAN
    if dirty_state in {"dirty", "modified", "uncommitted"}:
        return DIRTY_STATE_DIRTY
    return DIRTY_STATE_UNKNOWN


def _sequence_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "present"}
    return bool(value)
