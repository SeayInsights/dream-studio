"""External project validation pipeline — planning and approved read-only execution.

Two distinct layers with a strict safety boundary between them:

PLANNING LAYER (existing):
  build_external_project_validation_pipeline() always returns execution_allowed=False.
  The planning validator rejects any plan with execution_allowed=True.
  These are the default and the invariant for all planning operations.

EXECUTION LAYER (added in brownfield slice 18.x):
  approve_read_only_execution() is the ONLY path that produces execution_allowed=True.
  It does so by re-asserting every safety property at the execution boundary —
  not by trusting them from the planning layer. The execution validator (separate
  from the planning validator) checks: read-only scope enforced, no push/commit/
  mutation/deploy, private artifact exclusions present, operator approval ref required.

  A safety property that only holds at planning time but not at execution time is
  a hole. The dual-validator design makes each layer responsible for its own invariants.
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

DEFAULT_EXTERNAL_TARGET_IDS = ("dreamysuite", "bill-stack", "torii")
PRIVATE_TARGET_ARTIFACT_PATTERNS = (
    ".planning/**",
    ".dream-studio/**",
    "**/.dream-studio/**",
    "**/meta/work-orders/**",
    "**/handoffs/**",
    "**/backups/**",
    "**/*.db",
    "**/*.sqlite",
    "**/*.sqlite3",
    "**/*-wal",
    "**/*-shm",
    "**/.env",
    "**/.env.*",
)
DEFAULT_SEQUENCE = (
    "capture_target_boundary",
    "verify_current_target_selection",
    "classify_dirty_state",
    "detect_prd_and_status",
    "discover_stack_dependency_evidence",
    "classify_security_readiness_scope",
    "select_validation_profile",
    "verify_approval_scope",
    "run_read_only_validation",
    "record_target_repo_mutation_eval",
    "record_validation_evidence",
    "route_next_decision",
)


def default_external_target_registry() -> dict[str, Any]:
    """Return the built-in external target registry policy.

    The registry is metadata only. It does not assert that the target paths
    exist, and it does not read, scan, validate, or mutate those repositories.
    """

    targets = [
        {
            "target_id": target_id,
            "display_name": display_name,
            "status": "paused",
            "source_boundary": "external_project",
            "validation_profile": "external_project_read_only_intake",
            "read_access_requires_current_selection": True,
            "mutation_requires_scoped_approval": True,
            "commit_requires_validation_and_commit_policy": True,
            "push_deploy_requires_separate_approval": True,
            "private_artifact_policy": "exclude_from_target_git_tracking",
        }
        for target_id, display_name in (
            ("dreamysuite", "DreamySuite"),
            ("bill-stack", "Bill Stack"),
            ("torii", "TORII"),
        )
    ]
    return {
        "derived_view": True,
        "primary_authority": False,
        "source_authority": "dream_studio_project_registry_policy",
        "default_state": "paused",
        "read_access_requires_explicit_current_target_selection": True,
        "mutation_requires_scoped_approval": True,
        "commit_requires_validation_and_commit_policy": True,
        "push_deploy_requires_separate_approval": True,
        "targets": targets,
        "private_target_artifact_patterns": list(PRIVATE_TARGET_ARTIFACT_PATTERNS),
    }


def build_external_project_validation_pipeline(
    target: Mapping[str, Any],
    *,
    requested_checks: Sequence[str] | None = None,
    evidence_refs: Sequence[str] | None = None,
    current_target_selection_ref: str | None = None,
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
    selection_ref = (
        _text(current_target_selection_ref)
        or _text(target.get("current_target_selection_ref"))
        or _text(target.get("operator_selection_ref"))
    )
    read_access_allowed = bool(selection_ref)
    requested_actions = set(_sequence_text(target.get("requested_actions")))

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
        "target_selection": {
            "read_access_requires_explicit_current_target_selection": True,
            "current_target_selection_ref": selection_ref or None,
            "read_access_allowed": read_access_allowed,
            "selected_for_current_run": read_access_allowed,
        },
        "target_intake": {
            "read_only_intake_supported": True,
            "external_target_registry_required": True,
            "prd_status_detection": "metadata_only_until_selected",
            "stack_dependency_discovery": "metadata_only_until_selected",
            "security_readiness_classification": "scope_planned_not_executed",
            "dashboard_project_detail_visibility": "derived_target_card",
        },
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
        "push_deploy_policy": {
            "push_allowed": False,
            "deploy_allowed": False,
            "separate_approval_required": True,
            "reason": "external_targets_require_explicit_push_or_deploy_approval",
        },
        "private_artifact_policy": {
            "exclude_from_target_git_tracking": True,
            "patterns": list(PRIVATE_TARGET_ARTIFACT_PATTERNS),
            "evidence_storage": "dream_studio_meta_or_sqlite_authority",
            "target_repo_files_allowed": "sanitized_public_artifacts_only_when_approved",
        },
        "requested_actions": sorted(requested_actions),
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

    selection = _mapping(plan.get("target_selection"))
    if _truthy(selection.get("read_access_allowed")) and not selection.get(
        "current_target_selection_ref"
    ):
        issues.append("read_access_requires_current_target_selection_ref")
    commit_policy = _mapping(plan.get("commit_policy"))
    if _truthy(commit_policy.get("commit_allowed")):
        issues.append("commit_must_not_be_allowed_in_validation_plan")
    push_policy = _mapping(plan.get("push_deploy_policy"))
    if _truthy(push_policy.get("push_allowed")) or _truthy(push_policy.get("deploy_allowed")):
        issues.append("push_deploy_must_not_be_allowed_in_validation_plan")
    if not plan.get("work_order_sequence"):
        issues.append("work_order_sequence_required")
    if "target_repo_mutation_eval" not in set(_sequence_text(plan.get("evidence_requirements"))):
        issues.append("target_repo_mutation_eval_required")
    artifact_policy = _mapping(plan.get("private_artifact_policy"))
    if not _truthy(artifact_policy.get("exclude_from_target_git_tracking")):
        issues.append("private_target_artifacts_must_be_excluded")
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


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "approved", "present"}
    return bool(value)


# ── Approved read-only execution layer ────────────────────────────────────────
# These are the ONLY functions that produce execution_allowed=True.
# They are deliberately separate from the planning layer and re-assert
# every safety property independently.

_APPROVED_ALLOWED_MODES: frozenset[str] = frozenset({"read_only", "dry_run"})
_APPROVED_FORBIDDEN_MODES: frozenset[str] = frozenset(
    {"mutation", "cleanup", "push", "deploy", "commit", "stage"}
)
_APPROVED_DEFAULT_STEPS: tuple[str, ...] = ("run_read_only_validation",)


def approve_read_only_execution(
    plan: Mapping[str, Any],
    *,
    operator_approval_ref: str,
    execution_steps: Sequence[str] | None = None,
) -> dict[str, Any]:
    """Build an approved, read-only-scoped execution context from a validated plan.

    THIS IS THE ONLY PATH THAT SETS execution_allowed=True.

    Safety properties re-asserted at the execution boundary (not inherited):
    - push_allowed: False
    - commit_allowed: False
    - stage_allowed: False
    - mutation_allowed: False
    - deploy_allowed: False
    - allowed_modes: read_only, dry_run only
    - private_artifact_exclusions: full PRIVATE_TARGET_ARTIFACT_PATTERNS list
    - execution_scope: read_only_validation_only

    Args:
        plan: A planning-only plan from build_external_project_validation_pipeline().
              It is validated before the execution context is created — a plan with
              safety violations cannot yield an approved execution context.
        operator_approval_ref: Non-empty string identifying the operator's explicit
              approval. Required — no approval ref, no execution context.
        execution_steps: Steps permitted in this execution context. Defaults to
              ["run_read_only_validation"]. Any step outside this list is forbidden.

    Returns:
        Approved execution context dict. Must be passed to validate_approved_read_only_execution()
        before any execution step runs.

    Raises:
        ValueError: If plan has safety violations, or operator_approval_ref is empty.
    """
    if not _text(operator_approval_ref):
        raise ValueError(
            "operator_approval_ref is required and must be non-empty. "
            "Approved execution cannot proceed without explicit operator approval."
        )

    # Validate the source plan — a plan with violations cannot yield execution
    plan_issues = validate_external_project_validation_pipeline(plan)
    if plan_issues:
        raise ValueError(
            f"Source plan has safety violations and cannot be promoted to execution: "
            f"{plan_issues}"
        )

    allowed_steps = tuple(execution_steps or _APPROVED_DEFAULT_STEPS)
    if not allowed_steps:
        raise ValueError("execution_steps must be non-empty")

    # Re-assert every safety property independently at the execution boundary.
    # These are NOT inherited from the plan — each is explicitly set here.
    return {
        "derived_from_plan": True,
        "execution_allowed": True,  # The ONLY True in the codebase
        "execution_scope": "read_only_validation_only",
        "approved_execution_steps": list(allowed_steps),
        "operator_approval_ref": _text(operator_approval_ref),
        # ── Safety properties RE-ASSERTED (not inherited) ──────────────────────
        "safety_assertions": {
            "push_allowed": False,
            "commit_allowed": False,
            "stage_allowed": False,
            "mutation_allowed": False,
            "deploy_allowed": False,
            "allowed_execution_modes": sorted(_APPROVED_ALLOWED_MODES),
            "forbidden_execution_modes": sorted(_APPROVED_FORBIDDEN_MODES),
            "private_artifact_exclusions": list(PRIVATE_TARGET_ARTIFACT_PATTERNS),
            "execution_scope_constraint": "read_only_validation_steps_only",
        },
        # ── Context from plan (for traceability, not safety) ──────────────────
        "target_id": _text(_mapping(plan.get("target_policy")).get("target_id")),
        "validation_profile": _mapping(plan.get("validation_profile")).get("profile_id"),
        "source_evidence_refs": list(_sequence_text(plan.get("source_evidence_refs"))),
    }


def validate_approved_read_only_execution(ctx: Mapping[str, Any]) -> list[str]:
    """Validate an approved execution context before any execution step runs.

    This is the execution-layer validator — separate from the planning-layer validator.
    It checks that all safety re-assertions are present and correct.

    Called immediately before any execution step. A non-empty issues list must
    block execution, not proceed with a warning.

    Returns:
        List of safety violation strings. Empty list = safe to execute.
    """
    issues: list[str] = []

    if not _truthy(ctx.get("derived_from_plan")):
        issues.append("execution_context_must_derive_from_validated_plan")
    if not _truthy(ctx.get("execution_allowed")):
        issues.append("execution_context_must_have_execution_allowed_true")
    if ctx.get("execution_scope") != "read_only_validation_only":
        issues.append("execution_scope_must_be_read_only_validation_only")
    if not _text(ctx.get("operator_approval_ref")):
        issues.append("operator_approval_ref_required_in_execution_context")
    if not ctx.get("approved_execution_steps"):
        issues.append("approved_execution_steps_must_be_non_empty")

    safety = _mapping(ctx.get("safety_assertions"))

    # Each safety property re-checked independently — not by reference to the plan
    if safety.get("push_allowed") is not False:
        issues.append("push_must_not_be_allowed_in_execution_context")
    if safety.get("commit_allowed") is not False:
        issues.append("commit_must_not_be_allowed_in_execution_context")
    if safety.get("stage_allowed") is not False:
        issues.append("stage_must_not_be_allowed_in_execution_context")
    if safety.get("mutation_allowed") is not False:
        issues.append("mutation_must_not_be_allowed_in_execution_context")
    if safety.get("deploy_allowed") is not False:
        issues.append("deploy_must_not_be_allowed_in_execution_context")

    allowed_modes = set(safety.get("allowed_execution_modes") or [])
    if not allowed_modes:
        issues.append("allowed_execution_modes_must_be_non_empty_in_execution_context")
    elif not allowed_modes.issubset(_APPROVED_ALLOWED_MODES):
        disallowed = allowed_modes - _APPROVED_ALLOWED_MODES
        issues.append(f"execution_context_allows_non_read_only_modes:{disallowed}")

    if not safety.get("private_artifact_exclusions"):
        issues.append("private_artifact_exclusions_required_in_execution_context")

    scope_constraint = safety.get("execution_scope_constraint")
    if scope_constraint != "read_only_validation_steps_only":
        issues.append("execution_scope_constraint_must_be_read_only_validation_steps_only")

    return issues


def assert_step_is_permitted(
    step: str,
    execution_ctx: Mapping[str, Any],
) -> None:
    """Assert that a step is in the approved execution steps list.

    Raises ValueError if not permitted — prevents executing a step that was
    not in the original approved scope.
    """
    approved = set(execution_ctx.get("approved_execution_steps") or [])
    if step not in approved:
        raise ValueError(
            f"Step '{step}' is not in the approved execution steps {approved}. "
            "The execution context only permits the steps explicitly approved. "
            "This is a safety boundary — steps cannot be added at execution time."
        )
