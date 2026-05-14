"""PRD-driven milestone planning and next-action classification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

NEXT_ACTION_CONTINUE_INTERNAL = "continue_internal"
NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL = "require_operator_approval"
NEXT_ACTION_REQUIRE_OPERATOR_DECISION = "require_operator_decision"
NEXT_ACTION_HARD_STOP = "hard_stop"
NEXT_ACTION_GENERATE_HANDOFF = "generate_handoff"
NEXT_ACTION_COMPLETE_MILESTONE = "complete_milestone"
NEXT_ACTION_START_NEXT_MILESTONE = "start_next_milestone"
NEXT_ACTION_SESSION_TRANSFER = "session_transfer"
NEXT_ACTION_USER_REQUESTED_EXPORT = "user_requested_export"

NEXT_ACTIONS = frozenset(
    {
        NEXT_ACTION_CONTINUE_INTERNAL,
        NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL,
        NEXT_ACTION_REQUIRE_OPERATOR_DECISION,
        NEXT_ACTION_HARD_STOP,
        NEXT_ACTION_GENERATE_HANDOFF,
        NEXT_ACTION_COMPLETE_MILESTONE,
        NEXT_ACTION_START_NEXT_MILESTONE,
        NEXT_ACTION_SESSION_TRANSFER,
        NEXT_ACTION_USER_REQUESTED_EXPORT,
    }
)

HANDOFF_REASON_NONE = "none"
HANDOFF_REASON_OPERATOR_APPROVAL = "operator_approval_required"
HANDOFF_REASON_OPERATOR_DECISION = "operator_decision_required"
HANDOFF_REASON_HARD_BLOCKER = "hard_blocker"
HANDOFF_REASON_MILESTONE_COMPLETION = "milestone_completion_policy_requires_handoff"
HANDOFF_REASON_MATERIAL_RISK_BOUNDARY = "hard_blocker"
HANDOFF_REASON_FAILED_VALIDATION = "failed_validation"
HANDOFF_REASON_ROLLBACK_UNCERTAINTY = "rollback_uncertainty"
HANDOFF_REASON_PAUSE_RESUME = "pause_resume"
HANDOFF_REASON_SESSION_TRANSFER = "session_transfer_required"
HANDOFF_REASON_CONTEXT_TRANSFER = "context_threshold_transfer"
HANDOFF_REASON_USER_EXPORT = "user_requested_export_or_continuation"
HANDOFF_REASON_COMMIT_REQUIRED = "commit_required"
HANDOFF_REASON_PUSH_DEPLOY_REQUIRED = "push_or_deploy_required"
HANDOFF_REASON_DATABASE_MUTATION_REQUIRED = "database_mutation_required"
HANDOFF_REASON_MIGRATION_REQUIRED = "migration_required"
HANDOFF_REASON_DDL_DML_REQUIRED = "ddl_or_dml_required"
HANDOFF_REASON_PACKAGE_REQUIRED = "package_or_dependency_operation_required"
HANDOFF_REASON_RUNTIME_VALIDATION_REQUIRED = "runtime_or_browser_validation_required"
HANDOFF_REASON_SECRET_REQUIRED = "secret_or_sensitive_access_required"
HANDOFF_REASON_ARTIFACT_LIFECYCLE_REQUIRED = "artifact_compaction_deletion_archive_required"
HANDOFF_REASON_EXTERNAL_RESUME_REQUIRED = "external_project_resume_required"

ALLOWED_HANDOFF_REASONS = frozenset(
    {
        HANDOFF_REASON_OPERATOR_APPROVAL,
        HANDOFF_REASON_OPERATOR_DECISION,
        HANDOFF_REASON_HARD_BLOCKER,
        HANDOFF_REASON_FAILED_VALIDATION,
        HANDOFF_REASON_ROLLBACK_UNCERTAINTY,
        HANDOFF_REASON_PAUSE_RESUME,
        HANDOFF_REASON_SESSION_TRANSFER,
        HANDOFF_REASON_CONTEXT_TRANSFER,
        HANDOFF_REASON_USER_EXPORT,
        HANDOFF_REASON_COMMIT_REQUIRED,
        HANDOFF_REASON_PUSH_DEPLOY_REQUIRED,
        HANDOFF_REASON_DATABASE_MUTATION_REQUIRED,
        HANDOFF_REASON_MIGRATION_REQUIRED,
        HANDOFF_REASON_DDL_DML_REQUIRED,
        HANDOFF_REASON_PACKAGE_REQUIRED,
        HANDOFF_REASON_RUNTIME_VALIDATION_REQUIRED,
        HANDOFF_REASON_SECRET_REQUIRED,
        HANDOFF_REASON_ARTIFACT_LIFECYCLE_REQUIRED,
        HANDOFF_REASON_EXTERNAL_RESUME_REQUIRED,
        HANDOFF_REASON_MILESTONE_COMPLETION,
    }
)

INVALID_HANDOFF_REASONS = frozenset(
    {
        "planning_finished",
        "report_written",
        "evidence_created",
        "checklist_review_complete",
        "package_review_needed",
        "routine_validation_needed",
        "next_step_exists",
        "next_milestone_exists",
        "phase_number_incremented",
        "recommended_next_work_order_by_default",
        "legacy_next_work_order_routing",
        "no_reason_given",
        HANDOFF_REASON_NONE,
    }
)

LOW_RISK_STEP_TYPES = frozenset(
    {
        "artifact_read",
        "checklist_review",
        "package_review",
        "evidence_indexing",
        "evidence_creation",
        "report_writing",
        "report_generation",
        "summary",
        "progress_update",
        "non_mutating_validation",
        "backup",
        "checksum",
        "restore_rehearsal",
        "schema_fingerprint",
        "review",
    }
)

MATERIAL_RISK_STEP_TYPES = frozenset(
    {
        "architecture_direction_change",
        "stage_gate_order_change",
        "scope_expansion",
        "source_code_mutation",
        "database_mutation",
        "data_migration",
        "migration",
        "ddl",
        "dml",
        "ddl_or_dml",
        "commit",
        "push",
        "deploy",
        "package_manager",
        "dependency_operation",
        "runtime_browser_validation",
        "artifact_compaction",
        "artifact_deletion",
        "artifact_archive",
        "secret_access",
        "sensitive_data_access",
        "target_repo_work",
        "external_project_resume",
        "executable_design_artifact_execution",
    }
)

HANDOFF_REASON_BY_STEP_TYPE = {
    "database_mutation": HANDOFF_REASON_DATABASE_MUTATION_REQUIRED,
    "data_migration": HANDOFF_REASON_MIGRATION_REQUIRED,
    "migration": HANDOFF_REASON_MIGRATION_REQUIRED,
    "ddl": HANDOFF_REASON_DDL_DML_REQUIRED,
    "dml": HANDOFF_REASON_DDL_DML_REQUIRED,
    "ddl_or_dml": HANDOFF_REASON_DDL_DML_REQUIRED,
    "commit": HANDOFF_REASON_COMMIT_REQUIRED,
    "push": HANDOFF_REASON_PUSH_DEPLOY_REQUIRED,
    "deploy": HANDOFF_REASON_PUSH_DEPLOY_REQUIRED,
    "package_manager": HANDOFF_REASON_PACKAGE_REQUIRED,
    "dependency_operation": HANDOFF_REASON_PACKAGE_REQUIRED,
    "runtime_browser_validation": HANDOFF_REASON_RUNTIME_VALIDATION_REQUIRED,
    "secret_access": HANDOFF_REASON_SECRET_REQUIRED,
    "sensitive_data_access": HANDOFF_REASON_SECRET_REQUIRED,
    "artifact_compaction": HANDOFF_REASON_ARTIFACT_LIFECYCLE_REQUIRED,
    "artifact_deletion": HANDOFF_REASON_ARTIFACT_LIFECYCLE_REQUIRED,
    "artifact_archive": HANDOFF_REASON_ARTIFACT_LIFECYCLE_REQUIRED,
    "target_repo_work": HANDOFF_REASON_EXTERNAL_RESUME_REQUIRED,
    "external_project_resume": HANDOFF_REASON_EXTERNAL_RESUME_REQUIRED,
}

DEFAULT_PAUSED_EXTERNAL_PROJECTS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class NextActionDecision:
    """Reason-coded planner decision for the next milestone action."""

    next_action: str
    handoff_required: bool
    handoff_reason: str = HANDOFF_REASON_NONE
    reasons: tuple[str, ...] = ()
    current_internal_step: str | None = None
    next_milestone: str | None = None
    stop_gate: str | None = None
    why_internal_continuation_is_not_allowed: str | None = None
    required_operator_action: str | None = None
    next_internal_action: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "route_decision": self.next_action,
            "next_action": self.next_action,
            "handoff_required": self.handoff_required,
            "handoff_reason": self.handoff_reason,
            "reasons": list(self.reasons),
            "current_internal_step": self.current_internal_step,
            "next_milestone": self.next_milestone,
            "stop_gate": self.stop_gate,
            "why_internal_continuation_is_not_allowed": self.why_internal_continuation_is_not_allowed,
            "required_operator_action": self.required_operator_action,
            "next_internal_action": self.next_internal_action,
        }


def classify_next_action(state: Mapping[str, Any]) -> dict[str, Any]:
    """Classify the next action for a PRD-driven milestone state.

    The input is intentionally a plain mapping so file-backed YAML/JSON authority
    can feed the planner without requiring runtime DB access.
    """

    if not isinstance(state, Mapping):
        raise TypeError("milestone state must be a mapping")

    prd = _mapping(state.get("prd"))
    stage_gate = _mapping(state.get("stage_gate"))
    milestone = _mapping(state.get("milestone"))
    if not prd or not stage_gate or not milestone:
        return NextActionDecision(
            next_action=NEXT_ACTION_HARD_STOP,
            handoff_required=True,
            handoff_reason=HANDOFF_REASON_HARD_BLOCKER,
            reasons=("missing_required_authority_artifact",),
            stop_gate="missing_required_authority_artifact",
            why_internal_continuation_is_not_allowed="PRD, stage-gate, or milestone authority is missing.",
            required_operator_action="provide the missing authority artifact before continuation",
        ).as_dict()

    pending_steps = [_mapping(step) for step in _sequence(milestone.get("pending_internal_steps"))]
    current_step = _first_pending_step(pending_steps)
    next_milestone = _text(milestone.get("next_milestone"))

    stage_block = _stage_gate_block(stage_gate, next_milestone)
    if stage_block:
        return NextActionDecision(
            next_action=NEXT_ACTION_HARD_STOP,
            handoff_required=True,
            handoff_reason=HANDOFF_REASON_HARD_BLOCKER,
            reasons=(stage_block,),
            next_milestone=next_milestone,
            stop_gate="stage_gate_invalid_next_phase",
            why_internal_continuation_is_not_allowed="The next milestone is not valid for the active stage gate.",
            required_operator_action="choose a stage-gate-valid milestone or update stage-gate authority",
        ).as_dict()

    if current_step and _is_external_project_work(current_step, state):
        return NextActionDecision(
            next_action=NEXT_ACTION_HARD_STOP,
            handoff_required=True,
            handoff_reason=HANDOFF_REASON_EXTERNAL_RESUME_REQUIRED,
            reasons=("external_project_pause_active",),
            current_internal_step=_step_id(current_step),
            next_milestone=next_milestone,
            stop_gate="external_project_resume",
            why_internal_continuation_is_not_allowed="External project implementation is paused by strategic constraint.",
            required_operator_action="explicitly approve external project resume in a later Work Order",
        ).as_dict()

    validation_result = _text(
        current_step.get("validation_result")
        if current_step
        else milestone.get("validation_result")
    ).lower()
    if validation_result in {"fail", "failed", "validation_failed"}:
        if _truthy(milestone.get("rollback_uncertain")):
            return NextActionDecision(
                next_action=NEXT_ACTION_HARD_STOP,
                handoff_required=True,
                handoff_reason=HANDOFF_REASON_ROLLBACK_UNCERTAINTY,
                reasons=("failed_validation", "rollback_uncertainty"),
                current_internal_step=_step_id(current_step),
                next_milestone=next_milestone,
                stop_gate="rollback_uncertainty",
                why_internal_continuation_is_not_allowed="Validation failed and rollback certainty is not established.",
                required_operator_action="resolve rollback uncertainty before continuation",
            ).as_dict()
        return NextActionDecision(
            next_action=NEXT_ACTION_GENERATE_HANDOFF,
            handoff_required=True,
            handoff_reason=HANDOFF_REASON_FAILED_VALIDATION,
            reasons=("failed_validation",),
            current_internal_step=_step_id(current_step),
            next_milestone=next_milestone,
            stop_gate="failed_validation",
            why_internal_continuation_is_not_allowed="Validation failed and must be routed through a failure handoff.",
            required_operator_action="review failure evidence and choose remediation or hold path",
        ).as_dict()

    if _milestone_complete(milestone, pending_steps):
        completion = validate_milestone_completion_criteria(milestone)
        if _truthy(milestone.get("enforce_completion_criteria")) and not completion["complete"]:
            return NextActionDecision(
                next_action=NEXT_ACTION_HARD_STOP,
                handoff_required=True,
                handoff_reason=HANDOFF_REASON_HARD_BLOCKER,
                reasons=("milestone_completion_criteria_not_met",),
                next_milestone=next_milestone,
                stop_gate="milestone_completion_criteria",
                why_internal_continuation_is_not_allowed="Milestone completion criteria are missing or failed.",
                required_operator_action="record required evidence, validation, boundary, route, and gap classifications",
            ).as_dict()
        handoff_required = _milestone_completion_requires_handoff(milestone)
        if next_milestone and not handoff_required:
            return NextActionDecision(
                next_action=NEXT_ACTION_START_NEXT_MILESTONE,
                handoff_required=False,
                reasons=("milestone_completion", "stage_gate_valid_next_milestone"),
                next_milestone=next_milestone,
                next_internal_action=f"start milestone {next_milestone}",
            ).as_dict()
        return NextActionDecision(
            next_action=NEXT_ACTION_COMPLETE_MILESTONE,
            handoff_required=handoff_required,
            handoff_reason=(
                HANDOFF_REASON_MILESTONE_COMPLETION if handoff_required else HANDOFF_REASON_NONE
            ),
            reasons=("milestone_completion",),
            next_milestone=next_milestone,
            stop_gate="milestone_completion_policy" if handoff_required else None,
            why_internal_continuation_is_not_allowed=(
                "Milestone completion policy explicitly requires a handoff."
                if handoff_required
                else None
            ),
            required_operator_action=(
                "review milestone completion handoff" if handoff_required else None
            ),
        ).as_dict()

    if not current_step and next_milestone:
        return NextActionDecision(
            next_action=NEXT_ACTION_START_NEXT_MILESTONE,
            handoff_required=False,
            reasons=("stage_gate_valid_next_milestone",),
            next_milestone=next_milestone,
            next_internal_action=f"start milestone {next_milestone}",
        ).as_dict()

    if not current_step:
        return NextActionDecision(
            next_action=NEXT_ACTION_HARD_STOP,
            handoff_required=True,
            handoff_reason=HANDOFF_REASON_HARD_BLOCKER,
            reasons=("no_pending_internal_step",),
            next_milestone=next_milestone,
            stop_gate="no_pending_internal_step",
            why_internal_continuation_is_not_allowed="Milestone state has no current step and no valid next milestone.",
            required_operator_action="repair milestone execution state",
        ).as_dict()

    if _requires_operator_approval(current_step):
        step_type = _step_type(current_step)
        handoff_reason = _handoff_reason_for_step_type(step_type)
        return NextActionDecision(
            next_action=NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL,
            handoff_required=True,
            handoff_reason=handoff_reason,
            reasons=("operator_approval_required",),
            current_internal_step=_step_id(current_step),
            next_milestone=next_milestone,
            stop_gate=step_type or "operator_approval_required",
            why_internal_continuation_is_not_allowed=(
                f"The current step '{step_type or _step_id(current_step) or 'unknown'}' crosses an approval boundary."
            ),
            required_operator_action="create or grant file-backed approval before continuation",
        ).as_dict()

    if _is_low_risk_auto_continue(current_step, milestone):
        return NextActionDecision(
            next_action=NEXT_ACTION_CONTINUE_INTERNAL,
            handoff_required=False,
            reasons=("low_risk_internal_step",),
            current_internal_step=_step_id(current_step),
            next_milestone=next_milestone,
            next_internal_action=_step_id(current_step),
        ).as_dict()

    return NextActionDecision(
        next_action=NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL,
        handoff_required=True,
        handoff_reason=HANDOFF_REASON_OPERATOR_APPROVAL,
        reasons=("ambiguous_or_material_step",),
        current_internal_step=_step_id(current_step),
        next_milestone=next_milestone,
        stop_gate="ambiguous_or_material_step",
        why_internal_continuation_is_not_allowed="The current step is not classified as low-risk and has no approved continuation policy.",
        required_operator_action="decide or approve the next milestone action",
    ).as_dict()


def handoff_required_for_decision(decision: Mapping[str, Any]) -> bool:
    """Return whether a classified decision requires a handoff artifact."""

    if _truthy(decision.get("handoff_required")):
        return True
    return _text(decision.get("next_action")) == NEXT_ACTION_GENERATE_HANDOFF


def validate_authority_pack(authority: Mapping[str, Any]) -> list[str]:
    """Return missing PRD authority-pack fields.

    This validates structured authority data, not live files or runtime state.
    """

    required = (
        "product_identity",
        "primary_user",
        "problem_statement",
        "product_goals",
        "non_goals",
        "active_objective",
        "end_to_end_loop_definition",
        "success_criteria",
        "strategic_constraints",
        "paused_validation_targets",
    )
    return [field for field in required if not authority.get(field)]


def validate_milestone_completion_criteria(milestone: Mapping[str, Any]) -> dict[str, Any]:
    """Validate deterministic evidence gates before a milestone is declared complete."""

    criteria = _mapping(milestone.get("completion_criteria"))
    evidence_refs = _sequence(criteria.get("evidence_refs") or milestone.get("evidence_refs"))
    validation = _mapping(criteria.get("validation") or milestone.get("validation"))
    boundary = _mapping(
        criteria.get("boundary_confirmation") or milestone.get("boundary_confirmation")
    )
    route_state = _mapping(criteria.get("route_state") or milestone.get("route_state"))
    known_gaps = _sequence(criteria.get("known_gaps") or milestone.get("known_gaps"))

    missing: list[str] = []
    failed: list[str] = []
    if not evidence_refs:
        missing.append("evidence_refs")
    if not validation:
        missing.append("validation")
    elif _text(validation.get("status")).lower() not in {"passed", "pass", "success"}:
        failed.append("validation")
    if not boundary:
        missing.append("boundary_confirmation")
    elif not _truthy(boundary.get("confirmed")):
        failed.append("boundary_confirmation")
    if not route_state:
        missing.append("route_state")
    elif _text(route_state.get("handoff_required")).lower() not in {"false", "0", "no"} and not (
        route_state.get("handoff_required") is False
    ):
        failed.append("route_state")

    unclassified = [
        _text(gap.get("id") or gap.get("name") or index)
        for index, gap in enumerate(_mapping(item) for item in known_gaps)
        if _text(gap.get("classification")).lower()
        not in {
            "none",
            "release_blocker",
            "cutover_rehearsal_blocker",
            "post_cutover_backlog",
            "dashboard_polish",
            "future_module_work",
            "external_validation_work",
            "non_blocking_empty_state",
            "defer",
            "accepted_non_blocker",
        }
    ]
    if unclassified:
        failed.append("known_gaps")

    return {
        "complete": not missing and not failed,
        "missing": missing,
        "failed": failed,
        "unclassified_gaps": unclassified,
        "checks": {
            "evidence_refs_present": bool(evidence_refs),
            "validation_passed": "validation" not in missing and "validation" not in failed,
            "boundary_confirmed": "boundary_confirmation" not in missing
            and "boundary_confirmation" not in failed,
            "route_state_allows_completion": "route_state" not in missing
            and "route_state" not in failed,
            "known_gaps_classified": "known_gaps" not in failed,
        },
    }


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "present", "approved"}
    return bool(value)


def _first_pending_step(steps: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    for step in steps:
        status = _text(step.get("status")).lower()
        if status not in {"complete", "completed", "skipped"}:
            return dict(step)
    return None


def _step_id(step: Mapping[str, Any] | None) -> str | None:
    if not step:
        return None
    return _text(step.get("id") or step.get("step_id") or step.get("name")) or None


def _step_type(step: Mapping[str, Any] | None) -> str:
    if not step:
        return ""
    return _text(step.get("type") or step.get("action_type")).lower()


def _handoff_reason_for_step_type(step_type: str) -> str:
    return HANDOFF_REASON_BY_STEP_TYPE.get(step_type, HANDOFF_REASON_OPERATOR_APPROVAL)


def _stage_gate_block(stage_gate: Mapping[str, Any], next_milestone: str) -> str | None:
    if not next_milestone:
        return None
    blocked = {_text(item).lower() for item in _sequence(stage_gate.get("blocked_milestones"))}
    if next_milestone.lower() in blocked:
        return "stage_gate_blocks_next_milestone"
    sequence = [_text(item) for item in _sequence(stage_gate.get("milestone_sequence"))]
    if sequence and next_milestone not in sequence:
        return "stage_gate_missing_next_milestone"
    return None


def _is_external_project_work(step: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    target = _text(step.get("target_project") or step.get("project")).lower()
    if not target:
        return False
    strategic = _mapping(state.get("strategic_constraints"))
    paused = {
        _text(item).lower()
        for item in _sequence(
            strategic.get("paused_external_projects") or strategic.get("paused_projects")
        )
    }
    if not paused:
        paused = set(DEFAULT_PAUSED_EXTERNAL_PROJECTS)
    work_kind = _text(step.get("work_kind") or step.get("action_type") or step.get("type")).lower()
    return target in paused and work_kind in {
        "implementation",
        "target_repo_work",
        "external_project_resume",
    }


def _milestone_complete(
    milestone: Mapping[str, Any], pending_steps: Sequence[Mapping[str, Any]]
) -> bool:
    status = _text(milestone.get("status") or milestone.get("milestone_status")).lower()
    if status in {"complete", "completed"}:
        return True
    if pending_steps:
        return False
    return _truthy(milestone.get("completion_criteria_met"))


def _milestone_completion_requires_handoff(milestone: Mapping[str, Any]) -> bool:
    policy = _text(milestone.get("handoff_policy")).lower()
    if policy in {"none", "no_handoff", "internal_only"}:
        return False
    return policy in {
        "explicit_handoff",
        "milestone_completion",
        "milestone_completion_only",
        "milestone_completion_policy_requires_handoff",
        "always",
    }


def _requires_operator_approval(step: Mapping[str, Any]) -> bool:
    if _truthy(step.get("approval_granted")):
        return False
    step_type = _step_type(step)
    if step_type in MATERIAL_RISK_STEP_TYPES:
        return True
    return _truthy(step.get("requires_approval") or step.get("material_risk"))


def _is_low_risk_auto_continue(step: Mapping[str, Any], milestone: Mapping[str, Any]) -> bool:
    step_type = _text(step.get("type") or step.get("action_type")).lower()
    if step_type not in LOW_RISK_STEP_TYPES:
        return False
    auto_continue = step.get("auto_continue_allowed")
    if auto_continue is None:
        auto_continue = milestone.get("auto_continue_low_risk", True)
    return _truthy(auto_continue)
