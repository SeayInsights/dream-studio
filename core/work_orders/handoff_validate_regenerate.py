"""WO-SPLIT-HANDOFF: handoff self-validation and regeneration module."""

from __future__ import annotations
from typing import Any
from .milestones import (
    ALLOWED_HANDOFF_REASONS,
    INVALID_HANDOFF_REASONS,
)

from .handoff_constants import (
    DECISION_TAXONOMIES,
    FAIL,
    HANDOFF_SELF_VALIDATION,
    HANDOFF_TYPE_HOLD_REVIEW,
    HANDOFF_TYPE_RECOVERY_DECISION,
    HOLD,
    READY_WITH_CONSTRAINTS,
)
from .handoff_helpers import _body_missing, _section_list, _section_text
from .handoff_validate_sections import parse_prompt_sections
from .handoff_validate_evals import evaluate_handoff_prompt
from .handoff_build import build_handoff_prompt


def _section_taxonomy(sections: dict[str, str], phase_type: str) -> list[str]:
    parsed = _section_list(sections.get("required_decision_taxonomy", ""))
    if parsed and parsed != ["unavailable"]:
        return parsed
    return list(DECISION_TAXONOMIES.get(phase_type, ()))


def self_validate_generated_handoff(
    prompt_text: str,
    *,
    readiness: str,
    can_continue: bool,
    target_repo_required: bool = True,
    approval_required: bool | None = None,
    handoff_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate a generated handoff before callers treat it as ready."""
    context = handoff_context or {}
    evals = evaluate_handoff_prompt(
        prompt_text,
        readiness=readiness,
        can_continue=can_continue,
        target_repo_required=target_repo_required,
        approval_required=approval_required,
    )
    problems: list[str] = [
        f"{eval_type}:{result['observed_behavior']}"
        for eval_type, result in evals.items()
        if result.get("pass_fail") == "fail"
    ]
    sections = parse_prompt_sections(prompt_text)

    if "# Handoff Packet" in prompt_text:
        handoff_reason = sections.get("handoff_reason", "").strip()
        if (
            handoff_reason not in ALLOWED_HANDOFF_REASONS
            or handoff_reason in INVALID_HANDOFF_REASONS
        ):
            problems.append(f"invalid_or_missing_handoff_reason: {handoff_reason or 'missing'}")
        why = sections.get("why_internal_continuation_is_not_allowed", "").strip()
        routine_why_terms = (
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
            "unavailable",
        )
        if _body_missing(why) or any(term in why.lower() for term in routine_why_terms):
            problems.append("why_internal_continuation_is_not_allowed missing or routine")
        for required in (
            "route_decision",
            "stop_gate",
            "required_operator_action",
            "source_authority_refs",
            "evidence_refs",
            "validation_refs",
            "next_allowed_action_after_operator_approval",
        ):
            if _body_missing(sections.get(required, "")):
                problems.append(f"{required} missing")

    if context.get("requires_prior_attempt_summary") and _body_missing(
        sections.get("prior_attempt_outcome_summary", "")
    ):
        problems.append("prior_attempt_outcome_summary missing")

    if context.get("requires_database_relationship_context"):
        body = sections.get("database_relationship_context", "")
        required_terms = (
            "current_authority",
            "proposed_authority",
            "source_objects",
            "target_objects",
            "relationship_keys",
            "unresolved_decisions",
            "redaction_boundaries",
            "validation_refs",
        )
        missing = [term for term in required_terms if term not in body]
        if missing:
            problems.append("database_relationship_context missing terms: " + ", ".join(missing))

    if context.get("executable_design_artifact"):
        body = sections.get("executable_design_artifact_boundary", "")
        required_terms = (
            "DRAFT / DO NOT EXECUTE",
            "Do not run tooling",
            "later review and approval",
        )
        missing = [term for term in required_terms if term not in body]
        if missing:
            problems.append(
                "executable_design_artifact_boundary missing terms: " + ", ".join(missing)
            )

    return {
        "pass_fail": "pass" if not problems else "fail",
        "observed_behavior": (
            "generated handoff passed self-validation"
            if not problems
            else "generated handoff failed self-validation"
        ),
        "problems": problems,
        "evidence": [HANDOFF_SELF_VALIDATION],
        "evals": evals,
    }


def regenerate_handoff_prompt(prompt_text: str) -> str:
    """Regenerate an existing Handoff Packet through the current generator.

    This helper is intentionally deterministic and filesystem-passive. It is
    for stale standalone prompt artifacts that already contain enough context
    to be rebuilt after generator/template changes.
    """
    sections = parse_prompt_sections(prompt_text)
    required_source = (
        "phase_name",
        "handoff_type",
        "phase_type",
        "source_work_order_id",
        "next_work_order_id",
        "dream_studio_repo_path",
        "target_repo_path",
        "objective",
        "approval_mode",
        "risk_level",
        "report_path",
    )
    missing = [field for field in required_source if _body_missing(sections.get(field, ""))]
    if missing:
        raise ValueError(f"cannot regenerate handoff prompt; missing fields: {', '.join(missing)}")

    phase_type = _section_text(sections, "phase_type")
    handoff_type = _section_text(sections, "handoff_type")
    approval_mode = _section_text(sections, "approval_mode")
    final_decision = _section_text(sections, "final_decision", default="HOLD")
    is_blocked = handoff_type in {HANDOFF_TYPE_RECOVERY_DECISION, HANDOFF_TYPE_HOLD_REVIEW}
    readiness_state = (
        FAIL
        if handoff_type == HANDOFF_TYPE_HOLD_REVIEW
        else HOLD if is_blocked else READY_WITH_CONSTRAINTS
    )
    can_continue = not is_blocked

    work_order = {
        "work_order_id": _section_text(sections, "source_work_order_id"),
        "project_name": "Regenerated Handoff Packet",
        "target_path": _section_text(sections, "target_repo_path"),
        "objective": _section_text(sections, "objective"),
        "approval_mode": approval_mode,
        "risk_level": _section_text(sections, "risk_level"),
        "scope": {
            "include": _section_list(sections.get("scope_include", "")),
            "exclude": _section_list(sections.get("scope_exclude", "")),
        },
        "forbidden_actions": _section_list(sections.get("forbidden_actions", "")),
        "validation_commands": _section_list(sections.get("validation_commands", "")),
        "stop_conditions": _section_list(sections.get("stop_conditions", "")),
        "handoff_context": {
            "baseline_dream_studio": _section_text(
                sections, "baseline_dream_studio_branch_head", default="unknown"
            ),
            "baseline_target": _section_text(
                sections, "baseline_target_repo_branch_head", default="unknown"
            ),
            "before_after_evidence_requirements": _section_text(
                sections, "before_after_evidence_requirements", default=""
            ),
            "first_safe_action": _section_text(sections, "first_safe_action", default=""),
            "forbidden_files": _section_list(sections.get("forbidden_files", "")),
            "allowed_actions": _section_list(sections.get("allowed_actions", "")),
        },
    }
    recommendation = (
        f"{_section_text(sections, 'phase_name')}; "
        f"Next Work Order: {_section_text(sections, 'next_work_order_id')}; "
        f"Objective: {_section_text(sections, 'objective')}; "
        f"Risk: {_section_text(sections, 'risk_level')}; "
        f"Approval: {approval_mode};"
    )
    result_metadata = {
        "next_work_order_recommendation": recommendation,
        "handoff_context": work_order["handoff_context"],
    }
    readiness = {
        "readiness": readiness_state,
        "can_continue": can_continue,
        "reason": "regenerated from an existing Handoff Packet through the current generator",
        "required_human_decision": (
            "operator approval required before target repo mutation"
            if approval_mode == "approval_required"
            else "none before first safe action"
        ),
        "required_artifacts": [
            "source Handoff Packet",
            "regenerated prompt artifact",
            "handoff eval artifacts",
        ],
        "blockers": [] if can_continue else ["source handoff is not execution-ready"],
        "safe_next_action": "produce a Handoff Understanding Report before taking any repository action",
    }
    decision = {
        "recommended_action": "hold_for_review" if is_blocked else "continue_to_next_work_order",
        "next_work_order_id": _section_text(sections, "next_work_order_id"),
        "next_work_order_mode": approval_mode,
        "human_approval_required": approval_mode == "approval_required",
        "handoff_type": handoff_type,
        "phase_type": phase_type,
        "required_decision_taxonomy": _section_taxonomy(sections, phase_type),
        "final_decision": final_decision,
        "decision_rationale": _section_text(sections, "decision_rationale"),
        "constraints": [
            "fresh-session Handoff Understanding Report required before action",
            "no auto-execution of generated prompts",
            "no target repo mutation without explicit approval evidence",
            "no DB/event/schema/Docker/TORII/cloud/org/global/enterprise expansion",
        ],
    }
    return build_handoff_prompt(
        work_order=work_order,
        result_metadata=result_metadata,
        report_path=_section_text(sections, "report_path"),
        readiness=readiness,
        decision=decision,
        dream_studio_repo_path=_section_text(sections, "dream_studio_repo_path"),
    )
