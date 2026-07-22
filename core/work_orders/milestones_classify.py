"""Next-action classification for PRD-driven milestone execution.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/milestones.py``. Holds
``classify_next_action`` (the deterministic planner), its private step/risk
helpers, and ``handoff_required_for_decision``. No logic changes — extracted
verbatim from the original module.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .milestones_completion import validate_milestone_completion_criteria
from .milestones_shared import (
    DEFAULT_PAUSED_EXTERNAL_PROJECTS,
    HANDOFF_REASON_BY_STEP_TYPE,
    HANDOFF_REASON_EXTERNAL_RESUME_REQUIRED,
    HANDOFF_REASON_FAILED_VALIDATION,
    HANDOFF_REASON_HARD_BLOCKER,
    HANDOFF_REASON_MILESTONE_COMPLETION,
    HANDOFF_REASON_NONE,
    HANDOFF_REASON_OPERATOR_APPROVAL,
    HANDOFF_REASON_ROLLBACK_UNCERTAINTY,
    LOW_RISK_STEP_TYPES,
    MATERIAL_RISK_STEP_TYPES,
    NEXT_ACTION_COMPLETE_MILESTONE,
    NEXT_ACTION_CONTINUE_INTERNAL,
    NEXT_ACTION_GENERATE_HANDOFF,
    NEXT_ACTION_HARD_STOP,
    NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL,
    NEXT_ACTION_START_NEXT_MILESTONE,
    NextActionDecision,
    _mapping,
    _sequence,
    _text,
    _truthy,
)


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
