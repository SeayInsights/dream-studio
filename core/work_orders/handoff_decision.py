"""WO-SPLIT-HANDOFF: handoff decision module."""

from __future__ import annotations
from typing import Any
from .milestones import (
    INVALID_HANDOFF_REASONS,
    NEXT_ACTION_COMPLETE_MILESTONE,
    NEXT_ACTION_CONTINUE_INTERNAL,
    NEXT_ACTION_GENERATE_HANDOFF,
    NEXT_ACTION_HARD_STOP,
    NEXT_ACTION_REQUIRE_OPERATOR_DECISION,
    NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL,
    NEXT_ACTION_SESSION_TRANSFER,
    NEXT_ACTION_START_NEXT_MILESTONE,
    NEXT_ACTION_USER_REQUESTED_EXPORT,
    classify_next_action,
)

from .handoff_constants import (
    BLOCKING_FAILED_EVALS,
    DECISION_TAXONOMIES,
    FAIL,
    HANDOFF_EVAL_TYPES,
    HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
    HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER,
    HANDOFF_TYPE_RECOVERY_DECISION,
    HOLD,
    PHASE_TYPE_APPROVED_MUTATION,
    PHASE_TYPE_NORMAL_NEXT_WORK_ORDER,
    PHASE_TYPE_PRODUCT_CLOSEOUT,
    PHASE_TYPE_RECOVERY_DECISION,
    READY,
    READY_WITH_CONSTRAINTS,
)
from .handoff_helpers import (
    _as_list,
    _decision_rationale,
    _extract_work_order_id,
    _final_decision,
    _handoff_context,
    _handoff_type,
    _milestone_state,
    _next_mode,
    _next_recommendation,
    _phase_type,
    _transition_recommendation,
)


def _effective_next_recommendation(
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
) -> str:
    return _transition_recommendation(work_order, result_metadata) or _next_recommendation(
        result_metadata
    )


def _milestone_next_action(
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    state = _milestone_state(work_order, result_metadata)
    if state is None:
        return None
    decision = classify_next_action(state)
    milestone = state.get("milestone") if isinstance(state.get("milestone"), dict) else {}
    stage_gate = state.get("stage_gate") if isinstance(state.get("stage_gate"), dict) else {}
    if isinstance(stage_gate, dict):
        decision["current_stage_gate"] = stage_gate.get("stage_gate_id") or stage_gate.get("id")
    if isinstance(milestone, dict):
        decision["current_milestone"] = milestone.get("id") or milestone.get("milestone_id")
        decision["completed_internal_steps"] = milestone.get("completed_internal_steps", [])
        decision["pending_internal_steps"] = milestone.get("pending_internal_steps", [])
    return decision


def _readiness_from_milestone_decision(decision: dict[str, Any]) -> dict[str, Any]:
    next_action = str(decision.get("next_action", ""))
    reasons = _as_list(decision.get("reasons"))
    handoff_required = bool(decision.get("handoff_required"))

    base = {
        "required_artifacts": [
            "PRD authority",
            "stage-gate authority",
            "milestone execution state",
            "evidence refs when applicable",
        ],
        "blockers": [],
        "milestone_decision": decision,
    }

    if next_action == NEXT_ACTION_CONTINUE_INTERNAL:
        return {
            **base,
            "readiness": READY,
            "can_continue": True,
            "reason": "PRD milestone classifier selected low-risk internal continuation",
            "required_human_decision": "none before continuing the approved milestone",
            "safe_next_action": "continue the current milestone internally without generating a handoff",
        }
    if next_action == NEXT_ACTION_START_NEXT_MILESTONE:
        return {
            **base,
            "readiness": READY,
            "can_continue": True,
            "reason": "stage gate permits starting the next milestone",
            "required_human_decision": "none before starting the stage-gate-valid milestone",
            "safe_next_action": "start the next milestone from structured milestone authority",
        }
    if next_action == NEXT_ACTION_COMPLETE_MILESTONE and not handoff_required:
        return {
            **base,
            "readiness": READY,
            "can_continue": True,
            "reason": "milestone is complete and policy does not require a handoff",
            "required_human_decision": "none before recording milestone completion",
            "safe_next_action": "record milestone completion and continue to the next authorized milestone",
        }
    if next_action == NEXT_ACTION_COMPLETE_MILESTONE:
        return {
            **base,
            "readiness": READY_WITH_CONSTRAINTS,
            "can_continue": True,
            "reason": "milestone completion policy requires a handoff",
            "required_human_decision": "none before rendering the milestone completion handoff",
            "safe_next_action": "render a milestone-completion handoff from structured state",
        }
    if next_action == NEXT_ACTION_GENERATE_HANDOFF:
        return {
            **base,
            "readiness": READY_WITH_CONSTRAINTS,
            "can_continue": True,
            "reason": "milestone classifier requires a handoff for the next action",
            "required_human_decision": "follow the generated handoff reason before execution",
            "safe_next_action": "render and self-validate the required handoff",
        }
    if next_action in {NEXT_ACTION_SESSION_TRANSFER, NEXT_ACTION_USER_REQUESTED_EXPORT}:
        return {
            **base,
            "readiness": READY_WITH_CONSTRAINTS,
            "can_continue": True,
            "reason": f"milestone classifier selected {next_action}",
            "required_human_decision": "operator action required by transfer/export route",
            "safe_next_action": "render a transfer/export packet from structured state",
        }

    return {
        **base,
        "readiness": HOLD,
        "can_continue": False,
        "reason": "milestone classifier selected a stop or approval gate",
        "required_human_decision": (
            "operator approval required"
            if next_action == NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL
            else "operator decision or blocker resolution required"
        ),
        "blockers": reasons or [next_action or "milestone_stop_gate"],
        "safe_next_action": "hold until the milestone stop gate is resolved",
    }


def _status_by_type(eval_artifacts: list[dict[str, Any]]) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for artifact in eval_artifacts:
        eval_type = str(artifact.get("eval_type", ""))
        if eval_type in HANDOFF_EVAL_TYPES:
            continue
        statuses[eval_type] = str(artifact.get("pass_fail", "incomplete"))
    return statuses


def determine_sequential_readiness(
    *,
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    eval_artifacts: list[dict[str, Any]],
) -> dict[str, Any]:
    """Determine whether a report can safely continue to a next Work Order."""
    milestone_decision = _milestone_next_action(work_order, result_metadata)
    if milestone_decision is not None:
        return _readiness_from_milestone_decision(milestone_decision)

    recommendation = _effective_next_recommendation(work_order, result_metadata)
    statuses = _status_by_type(eval_artifacts)
    blockers: list[str] = []

    if result_metadata is None:
        blockers.append("result evidence unavailable")
    if not recommendation or recommendation.lower() == "unavailable":
        blockers.append("next Work Order recommendation unavailable")

    for artifact in eval_artifacts:
        eval_type = str(artifact.get("eval_type", "unknown"))
        if eval_type in HANDOFF_EVAL_TYPES:
            continue
        status = str(artifact.get("pass_fail", "incomplete"))
        if status == "fail" and eval_type in BLOCKING_FAILED_EVALS:
            blockers.append(f"{eval_type} failed")

    incomplete = [eval_type for eval_type, status in statuses.items() if status == "incomplete"]

    if blockers:
        readiness = HOLD
        can_continue = False
        reason = "blocked by required result, recommendation, or eval evidence"
    elif incomplete:
        readiness = READY_WITH_CONSTRAINTS
        can_continue = True
        reason = "no blocking failures; incomplete evidence must be carried forward"
    else:
        readiness = READY
        can_continue = True
        reason = "result, recommendation, and blocking eval evidence are complete"

    next_mode = _next_mode(work_order, recommendation)
    required_human_decision = (
        "operator approval required before target repo mutation"
        if next_mode == "approval_required"
        else "none before first safe action"
    )
    required_artifacts = [
        "source Work Order report",
        "file-backed Work Order result",
        "handoff eval artifacts",
    ]
    if next_mode == "approval_required":
        required_artifacts.append("approval artifact before mutation")
        required_artifacts.append("before/after target mutation evidence")

    return {
        "readiness": readiness,
        "can_continue": can_continue,
        "reason": reason,
        "required_human_decision": required_human_decision,
        "required_artifacts": required_artifacts,
        "blockers": blockers,
        "safe_next_action": (
            "produce a Handoff Understanding Report before taking any repository action"
        ),
    }


def determine_next_action_decision(
    *,
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    readiness: dict[str, Any],
) -> dict[str, Any]:
    milestone_decision = readiness.get("milestone_decision")
    if isinstance(milestone_decision, dict):
        return _decision_from_milestone_next_action(
            work_order=work_order,
            result_metadata=result_metadata,
            readiness=readiness,
            milestone_decision=milestone_decision,
        )

    recommendation = _effective_next_recommendation(work_order, result_metadata)
    next_mode = _next_mode(work_order, recommendation)
    handoff_type = _handoff_type(
        work_order=work_order,
        recommendation=recommendation,
        readiness=readiness,
        next_mode=next_mode,
    )
    phase_type = _phase_type(
        work_order=work_order,
        recommendation=recommendation,
        handoff_type=handoff_type,
        next_mode=next_mode,
    )
    final_decision = _final_decision(
        phase_type=phase_type,
        readiness=str(readiness.get("readiness", HOLD)),
        can_continue=bool(readiness.get("can_continue", False)),
        next_mode=next_mode,
    )
    if readiness["readiness"] in {HOLD, FAIL}:
        recommended_action = "hold_for_review"
    elif next_mode == "approval_required":
        recommended_action = "request_human_approval"
    else:
        recommended_action = "continue_to_next_work_order"

    context_reason = _handoff_context(work_order, result_metadata).get("handoff_reason")
    handoff_reason = (
        str(context_reason)
        if context_reason
        else _handoff_reason_for_legacy_route(
            recommendation=recommendation,
            handoff_type=handoff_type,
            phase_type=phase_type,
            next_mode=next_mode,
            readiness=readiness,
        )
    )
    return {
        "recommended_action": recommended_action,
        "next_work_order_id": _extract_work_order_id(recommendation),
        "next_work_order_mode": next_mode,
        "human_approval_required": next_mode == "approval_required",
        "handoff_type": handoff_type,
        "phase_type": phase_type,
        "required_decision_taxonomy": list(DECISION_TAXONOMIES[phase_type]),
        "final_decision": final_decision,
        "decision_rationale": _decision_rationale(
            phase_type=phase_type,
            final_decision=final_decision,
            readiness=str(readiness.get("readiness", HOLD)),
        ),
        "constraints": [
            "fresh-session Handoff Understanding Report required before action",
            "no auto-execution of generated prompts",
            "no target repo mutation without explicit approval evidence",
            "no DB/event/schema/Docker/TORII/cloud/org/global/enterprise expansion",
        ],
        "handoff_required": handoff_reason not in INVALID_HANDOFF_REASONS,
        "handoff_reason": handoff_reason,
        "route_decision": recommended_action,
        "stop_gate": _stop_gate_for_handoff_reason(handoff_reason),
        "why_internal_continuation_is_not_allowed": _why_internal_continuation_is_not_allowed(
            handoff_reason
        ),
        "required_operator_action": _required_operator_action(handoff_reason),
    }


def _handoff_reason_for_legacy_route(
    *,
    recommendation: str,
    handoff_type: str,
    phase_type: str,
    next_mode: str,
    readiness: dict[str, Any],
) -> str:
    subject = f"{recommendation} {handoff_type} {phase_type}".lower()
    if readiness.get("readiness") in {HOLD, FAIL}:
        return "hard_blocker"
    if "commit" in subject:
        return "commit_required"
    if "push" in subject or "deploy" in subject:
        return "push_or_deploy_required"
    if "database" in subject or "sqlite" in subject:
        return "database_mutation_required"
    if "migration" in subject:
        return "migration_required"
    if "package" in subject or "dependency" in subject:
        return "package_or_dependency_operation_required"
    if "runtime" in subject or "browser" in subject:
        return "runtime_or_browser_validation_required"
    if "secret" in subject or "sensitive" in subject:
        return "secret_or_sensitive_access_required"
    if "session transfer" in subject or "context threshold" in subject:
        return "session_transfer_required"
    if "export" in subject or "user-requested" in subject:
        return "user_requested_export_or_continuation"
    if phase_type == PHASE_TYPE_PRODUCT_CLOSEOUT:
        return "milestone_completion_policy_requires_handoff"
    if next_mode == "approval_required":
        return "operator_approval_required"
    return "no_reason_given"


def _stop_gate_for_handoff_reason(handoff_reason: str) -> str:
    mapping = {
        "operator_approval_required": "operator_approval_required",
        "operator_decision_required": "operator_decision_required",
        "hard_blocker": "hard_blocker",
        "failed_validation": "failed_validation",
        "rollback_uncertainty": "rollback_uncertainty",
        "commit_required": "commit",
        "push_or_deploy_required": "push_or_deploy",
        "database_mutation_required": "database_mutation",
        "migration_required": "database_migration",
        "ddl_or_dml_required": "ddl_or_dml",
        "package_or_dependency_operation_required": "package_or_dependency_operation",
        "runtime_or_browser_validation_required": "runtime_or_browser_validation",
        "secret_or_sensitive_access_required": "secret_or_sensitive_access",
        "artifact_compaction_deletion_archive_required": "artifact_lifecycle_boundary",
        "external_project_resume_required": "external_project_resume",
        "milestone_completion_policy_requires_handoff": "milestone_completion_policy",
        "session_transfer_required": "session_transfer",
        "context_threshold_transfer": "context_threshold_transfer",
        "user_requested_export_or_continuation": "user_requested_export_or_continuation",
        "pause_resume": "pause_resume",
    }
    return mapping.get(handoff_reason, "invalid_handoff_reason")


def _why_internal_continuation_is_not_allowed(handoff_reason: str) -> str:
    if handoff_reason in INVALID_HANDOFF_REASONS:
        return ""
    return f"Internal continuation is blocked because route policy requires handoff reason: {handoff_reason}."


def _required_operator_action(handoff_reason: str) -> str:
    if handoff_reason in INVALID_HANDOFF_REASONS:
        return "none"
    if handoff_reason in {"session_transfer_required", "context_threshold_transfer"}:
        return "resume from the transfer packet"
    if handoff_reason == "user_requested_export_or_continuation":
        return "use the requested export or continuation packet"
    return "review the stop gate and provide required approval or decision"


def _decision_from_milestone_next_action(
    *,
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    readiness: dict[str, Any],
    milestone_decision: dict[str, Any],
) -> dict[str, Any]:
    recommendation = _effective_next_recommendation(work_order, result_metadata)
    next_action = str(milestone_decision.get("next_action", ""))
    handoff_required = bool(milestone_decision.get("handoff_required"))
    next_mode = _next_mode(work_order, recommendation)
    handoff_type = HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER
    phase_type = PHASE_TYPE_NORMAL_NEXT_WORK_ORDER
    final_decision = "CONTINUE_TO_NEXT_WORK_ORDER"
    human_approval_required = False

    if next_action == NEXT_ACTION_CONTINUE_INTERNAL:
        recommended_action = NEXT_ACTION_CONTINUE_INTERNAL
        final_decision = "CONTINUE_TO_NEXT_WORK_ORDER"
    elif next_action == NEXT_ACTION_START_NEXT_MILESTONE:
        recommended_action = NEXT_ACTION_START_NEXT_MILESTONE
        final_decision = "CONTINUE_TO_NEXT_WORK_ORDER"
    elif next_action == NEXT_ACTION_COMPLETE_MILESTONE:
        recommended_action = NEXT_ACTION_COMPLETE_MILESTONE
        final_decision = (
            "CONTINUE_TO_NEXT_WORK_ORDER" if not handoff_required else "CONTINUE_TO_NEXT_WORK_ORDER"
        )
    elif next_action == NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL:
        recommended_action = "request_human_approval"
        human_approval_required = True
        next_mode = "approval_required"
        handoff_type = HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION
        phase_type = PHASE_TYPE_APPROVED_MUTATION
        final_decision = "HOLD"
    elif next_action == NEXT_ACTION_REQUIRE_OPERATOR_DECISION:
        recommended_action = "require_operator_decision"
        human_approval_required = True
        handoff_type = HANDOFF_TYPE_RECOVERY_DECISION
        phase_type = PHASE_TYPE_RECOVERY_DECISION
        final_decision = "HOLD"
    elif next_action == NEXT_ACTION_HARD_STOP:
        recommended_action = "hold_for_review"
        handoff_type = HANDOFF_TYPE_RECOVERY_DECISION
        phase_type = PHASE_TYPE_RECOVERY_DECISION
        final_decision = "HOLD"
    elif next_action == NEXT_ACTION_GENERATE_HANDOFF:
        recommended_action = NEXT_ACTION_GENERATE_HANDOFF
    elif next_action in {NEXT_ACTION_SESSION_TRANSFER, NEXT_ACTION_USER_REQUESTED_EXPORT}:
        recommended_action = next_action
    else:
        recommended_action = "hold_for_review"
        handoff_type = HANDOFF_TYPE_RECOVERY_DECISION
        phase_type = PHASE_TYPE_RECOVERY_DECISION
        final_decision = "HOLD"

    if readiness.get("readiness") == HOLD or not readiness.get("can_continue", False):
        final_decision = "HOLD"
    required_taxonomy = list(DECISION_TAXONOMIES.get(phase_type, ()))
    if final_decision not in required_taxonomy:
        final_decision = "HOLD" if "HOLD" in required_taxonomy else required_taxonomy[0]

    next_work_order_id = _extract_work_order_id(recommendation)
    if next_work_order_id == "unavailable":
        next_work_order_id = str(
            milestone_decision.get("next_milestone")
            or milestone_decision.get("current_internal_step")
            or "internal_milestone_step"
        )

    return {
        "recommended_action": recommended_action,
        "next_work_order_id": next_work_order_id,
        "next_work_order_mode": next_mode,
        "human_approval_required": human_approval_required,
        "handoff_type": handoff_type,
        "phase_type": phase_type,
        "required_decision_taxonomy": required_taxonomy,
        "final_decision": final_decision,
        "decision_rationale": (
            "PRD/stage-gate/milestone classifier selected "
            f"{next_action}; handoff_required={str(handoff_required).lower()}."
        ),
        "constraints": [
            "PRD/stage-gate/milestone authority overrides naive handoff-chain routing",
            "low-risk internal steps must not create micro-prompts",
            "material risk gates require approval, decision, hard stop, or handoff",
            "external project implementation remains paused",
        ],
        "handoff_required": handoff_required,
        "handoff_reason": str(milestone_decision.get("handoff_reason") or "none"),
        "route_decision": next_action,
        "stop_gate": str(
            milestone_decision.get("stop_gate")
            or _stop_gate_for_handoff_reason(
                str(milestone_decision.get("handoff_reason") or "none")
            )
        ),
        "why_internal_continuation_is_not_allowed": str(
            milestone_decision.get("why_internal_continuation_is_not_allowed")
            or _why_internal_continuation_is_not_allowed(
                str(milestone_decision.get("handoff_reason") or "none")
            )
        ),
        "required_operator_action": str(
            milestone_decision.get("required_operator_action")
            or _required_operator_action(str(milestone_decision.get("handoff_reason") or "none"))
        ),
        "next_internal_action": milestone_decision.get("next_internal_action"),
        "current_stage_gate": milestone_decision.get("current_stage_gate"),
        "current_milestone": milestone_decision.get("current_milestone"),
        "completed_internal_steps": milestone_decision.get("completed_internal_steps", []),
        "pending_internal_steps": milestone_decision.get("pending_internal_steps", []),
        "milestone_decision": milestone_decision,
    }
