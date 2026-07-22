"""WO-SPLIT-HANDOFF: handoff build sections/orchestration module."""

from __future__ import annotations
from pathlib import Path
from typing import Any

from .handoff_constants import (
    DECISION_TAXONOMIES,
    HANDOFF_TYPES,
    HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
    HANDOFF_TYPE_COMMIT_EXECUTION,
    HANDOFF_TYPE_RECOVERY_EXECUTION,
    HOLD,
    READY,
    READY_WITH_CONSTRAINTS,
)
from .handoff_helpers import _as_list, _handoff_context, _milestone_state
from .handoff_decision import determine_next_action_decision, determine_sequential_readiness
from .handoff_build_prompt import build_handoff_prompt


def _execution_handoff_type(handoff_type: str) -> bool:
    return handoff_type in {
        HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
        HANDOFF_TYPE_COMMIT_EXECUTION,
        HANDOFF_TYPE_RECOVERY_EXECUTION,
    }


def _apply_operator_decision(
    *,
    readiness: dict[str, Any],
    decision: dict[str, Any],
    decision_request: dict[str, Any] | None,
    operator_decision: dict[str, Any] | None,
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not decision_request:
        return readiness, decision

    handoff_type = str(decision.get("handoff_type", ""))
    needs_decision = _execution_handoff_type(handoff_type) or bool(
        decision.get("human_approval_required")
    )
    if not operator_decision and needs_decision:
        gated = dict(readiness)
        blockers = _as_list(gated.get("blockers"))
        blockers.append("operator decision artifact missing for execution handoff")
        gated.update(
            {
                "readiness": HOLD,
                "can_continue": False,
                "reason": "blocked by missing file-backed operator decision",
                "required_human_decision": "record operator_decision.json before execution handoff",
                "blockers": blockers,
            }
        )
        return gated, determine_next_action_decision(
            work_order=work_order,
            result_metadata=result_metadata,
            readiness=gated,
        )

    if not operator_decision:
        return readiness, decision

    selected = str(operator_decision.get("decision", ""))
    phase_type = str(decision_request.get("phase_type") or decision.get("phase_type", ""))
    allowed = DECISION_TAXONOMIES.get(phase_type, ())
    if selected not in allowed:
        gated = dict(readiness)
        blockers = _as_list(gated.get("blockers"))
        blockers.append("operator decision is outside required decision taxonomy")
        gated.update(
            {
                "readiness": HOLD,
                "can_continue": False,
                "reason": "blocked by invalid file-backed operator decision",
                "required_human_decision": "record a valid operator_decision.json",
                "blockers": blockers,
            }
        )
        return gated, determine_next_action_decision(
            work_order=work_order,
            result_metadata=result_metadata,
            readiness=gated,
        )

    decided = dict(decision)
    decided.update(
        {
            "phase_type": phase_type,
            "required_decision_taxonomy": list(allowed),
            "final_decision": selected,
            "decision_rationale": (
                "Final decision comes from a file-backed operator_decision artifact; "
                "the decision does not execute work by itself."
            ),
        }
    )
    approved_handoff_type = str(operator_decision.get("approved_next_handoff_type", "")).strip()
    if approved_handoff_type in HANDOFF_TYPES:
        decided["handoff_type"] = approved_handoff_type
    return readiness, decided


def build_handoff_sections(
    *,
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    eval_artifacts: list[dict[str, Any]],
    report_path: Path | str,
    dream_studio_repo_path: Path | str | None = None,
    decision_request: dict[str, Any] | None = None,
    operator_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    readiness = determine_sequential_readiness(
        work_order=work_order,
        result_metadata=result_metadata,
        eval_artifacts=eval_artifacts,
    )
    decision = determine_next_action_decision(
        work_order=work_order,
        result_metadata=result_metadata,
        readiness=readiness,
    )
    readiness, decision = _apply_operator_decision(
        readiness=readiness,
        decision=decision,
        decision_request=decision_request,
        operator_decision=operator_decision,
        work_order=work_order,
        result_metadata=result_metadata,
    )
    if decision.get("handoff_required") is False:
        return {
            "readiness": readiness,
            "decision": decision,
            "prompt": _internal_milestone_continuation_summary(
                work_order=work_order,
                readiness=readiness,
                decision=decision,
                result_metadata=result_metadata,
            ),
            "decision_request": decision_request,
            "operator_decision": operator_decision,
            "self_validation": {
                "pass_fail": "pass",
                "observed_behavior": "handoff not required for this PRD milestone decision",
                "evidence": ["handoff_required=false"],
            },
        }
    prompt = build_handoff_prompt(
        work_order=work_order,
        result_metadata=result_metadata,
        report_path=report_path,
        readiness=readiness,
        decision=decision,
        dream_studio_repo_path=dream_studio_repo_path,
        decision_request=decision_request,
        operator_decision=operator_decision,
    )
    # Local import breaks the build<->validate module cycle (validate imports
    # build_handoff_prompt at module load; build only needs validate here at call time).
    from .handoff_validate import self_validate_generated_handoff

    self_validation = self_validate_generated_handoff(
        prompt,
        readiness=str(readiness.get("readiness", HOLD)),
        can_continue=bool(readiness.get("can_continue", False)),
        target_repo_required=bool(str(work_order.get("target_path", "")).strip()),
        approval_required=decision.get("next_work_order_mode") == "approval_required",
        handoff_context=_handoff_context(work_order, result_metadata),
    )
    if self_validation["pass_fail"] != "pass" and readiness.get("readiness") in {
        READY,
        READY_WITH_CONSTRAINTS,
    }:
        gated = dict(readiness)
        blockers = _as_list(gated.get("blockers"))
        blockers.append("generated handoff self-validation failed")
        blockers.extend(_as_list(self_validation.get("problems")))
        gated.update(
            {
                "readiness": HOLD,
                "can_continue": False,
                "reason": "blocked by generated handoff self-validation",
                "required_human_decision": "repair generated handoff before emission",
                "blockers": blockers,
            }
        )
        readiness = gated
        decision = determine_next_action_decision(
            work_order=work_order,
            result_metadata=result_metadata,
            readiness=readiness,
        )
    return {
        "readiness": readiness,
        "decision": decision,
        "prompt": prompt,
        "decision_request": decision_request,
        "operator_decision": operator_decision,
        "self_validation": self_validation,
    }


def _internal_milestone_continuation_summary(
    *,
    work_order: dict[str, Any],
    readiness: dict[str, Any],
    decision: dict[str, Any],
    result_metadata: dict[str, Any] | None,
) -> str:
    milestone_decision = decision.get("milestone_decision", {})
    next_internal_action = (
        decision.get("next_internal_action")
        or (
            milestone_decision.get("next_internal_action")
            if isinstance(milestone_decision, dict)
            else None
        )
        or decision.get("recommended_action", "unavailable")
    )
    current_milestone = "unavailable"
    current_stage_gate = "unavailable"
    state = _milestone_state(work_order, result_metadata) or {}
    milestone = state.get("milestone") if isinstance(state.get("milestone"), dict) else {}
    stage_gate = state.get("stage_gate") if isinstance(state.get("stage_gate"), dict) else {}
    if isinstance(milestone, dict):
        current_milestone = str(
            milestone.get("id") or milestone.get("milestone_id") or "unavailable"
        )
    if isinstance(stage_gate, dict):
        current_stage_gate = str(
            stage_gate.get("stage_gate_id") or stage_gate.get("id") or "unavailable"
        )
    return (
        "\n".join(
            [
                "# Continuation Packet",
                "",
                "This is not a Handoff Packet.",
                "PRD/stage-gate/milestone authority classified the next action as safe internal continuation.",
                "artifact_type: continuation_packet",
                "is_handoff: false",
                "auto_resume_allowed: true",
                "operator_action_required: false",
                f"Source Work Order ID: {work_order.get('work_order_id', 'unavailable')}",
                f"Route Decision: {decision.get('route_decision') or decision.get('recommended_action', 'unavailable')}",
                f"Next Internal Action: {next_internal_action}",
                f"Current Stage Gate: {current_stage_gate}",
                f"Current Milestone: {current_milestone}",
                "Evidence Refs:",
                "- rendered from route decision state",
                f"Handoff Required: {str(decision.get('handoff_required', False)).lower()}",
                f"Reason: {readiness.get('reason', 'unavailable')}",
                f"Safe Next Action: {readiness.get('safe_next_action', 'unavailable')}",
                "Forbidden Actions:",
                "- do not treat this continuation packet as a handoff",
                "- do not ask the operator to create a new phase",
                "- do not cross a stop gate without approval",
            ]
        )
        + "\n"
    )
