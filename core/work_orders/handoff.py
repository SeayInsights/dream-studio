"""Deterministic Handoff Packet generation and dry-run checks.

This module is intentionally pure and file-system passive. It does not inspect
target repositories, open Dream Studio runtime state, or execute generated
prompts.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .milestones import (
    ALLOWED_HANDOFF_REASONS,
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

FRESH_SESSION_RULE = (
    "Assume you have no prior conversation context. Use only this prompt and referenced artifacts."
)

READY = "READY"
READY_WITH_CONSTRAINTS = "READY_WITH_CONSTRAINTS"
HOLD = "HOLD"
FAIL = "FAIL"

HANDOFF_PROMPT_COMPLETENESS = "handoff_prompt_completeness"
HANDOFF_CONSTRAINT_PRESERVATION = "handoff_constraint_preservation"
HANDOFF_EXECUTION_READINESS = "handoff_execution_readiness"
HANDOFF_FRESH_SESSION_SUFFICIENCY = "handoff_fresh_session_sufficiency"
HANDOFF_PATH_INTEGRITY = "handoff_path_integrity"
HANDOFF_SELF_VALIDATION = "handoff_self_validation"
HANDOFF_RECOVERY_MODE_COMPLETENESS = "handoff_recovery_mode_completeness"
HANDOFF_CURRENT_STATE_COMPLETENESS = "handoff_current_state_completeness"
HANDOFF_RECOVERY_OPTION_CLARITY = "handoff_recovery_option_clarity"
HANDOFF_OPERATOR_DECISION_GATE = "handoff_operator_decision_gate"
HANDOFF_INDEX_STATE_REQUIREMENTS = "handoff_index_state_requirements"
HANDOFF_HOOK_BEHAVIOR_AWARENESS = "handoff_hook_behavior_awareness"
HANDOFF_PUSH_EXECUTION_COMPLETENESS = "handoff_push_execution_completeness"
HANDOFF_PUSH_TARGET_CONSTRAINTS = "handoff_push_target_constraints"
HANDOFF_PUSH_EVIDENCE_REQUIREMENTS = "handoff_push_evidence_requirements"
SECURITY_HANDOFF_FINDING_REFS_PRESENT = "security_handoff_finding_refs_present"
SECURITY_HANDOFF_RELEASE_GATE_PRESERVED = "security_handoff_release_gate_preserved"
SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED = "security_handoff_target_constraints_preserved"
SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED = "security_handoff_remediation_scope_bounded"
SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED = "security_handoff_forbidden_actions_preserved"
SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL = (
    "security_handoff_no_target_mutation_without_approval"
)
SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE = "security_handoff_no_commit_without_commit_phase"
READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE = "ready_to_copy_next_prompt_contract_compliance"

HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER = "normal_next_work_order"
HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION = "approved_mutation_execution"
HANDOFF_TYPE_COMMIT_EXECUTION = "commit_execution"
HANDOFF_TYPE_RECOVERY_DECISION = "recovery_decision"
HANDOFF_TYPE_RECOVERY_EXECUTION = "recovery_execution"
HANDOFF_TYPE_HOLD_REVIEW = "hold_review"
HANDOFF_TYPES = frozenset(
    {
        HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER,
        HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
        HANDOFF_TYPE_COMMIT_EXECUTION,
        HANDOFF_TYPE_RECOVERY_DECISION,
        HANDOFF_TYPE_RECOVERY_EXECUTION,
        HANDOFF_TYPE_HOLD_REVIEW,
    }
)

PHASE_TYPE_PUSH_PLANNING = "push_planning"
PHASE_TYPE_COMMIT_PLANNING = "commit_planning"
PHASE_TYPE_RECOVERY_DECISION = "recovery_decision"
PHASE_TYPE_PRODUCT_CLOSEOUT = "product_closeout"
PHASE_TYPE_APPROVED_MUTATION = "approved_mutation"
PHASE_TYPE_NORMAL_NEXT_WORK_ORDER = "normal_next_work_order"
DECISION_TAXONOMIES: dict[str, tuple[str, ...]] = {
    PHASE_TYPE_PUSH_PLANNING: (
        "PUSH_READY_WITH_APPROVAL",
        "RUN_BROADER_VALIDATION_FIRST",
        "HOLD",
        "FAIL",
    ),
    PHASE_TYPE_COMMIT_PLANNING: (
        "READY_FOR_COMMIT_PLANNING",
        "NEEDS_ONE_MORE_FIX",
        "HOLD",
        "FAIL",
    ),
    PHASE_TYPE_RECOVERY_DECISION: (
        "LINT_REMEDIATION",
        "NO_VERIFY_CONTINUATION",
        "UNSTAGE_AND_HOLD",
        "ROLLBACK",
        "HOLD",
        "FAIL",
    ),
    PHASE_TYPE_PRODUCT_CLOSEOUT: (
        "READY_FOR_HUMAN_REVIEW",
        "READY_FOR_COMMIT_PLANNING",
        "NEEDS_ONE_MORE_FIX",
        "HOLD",
        "FAIL",
    ),
    PHASE_TYPE_APPROVED_MUTATION: (
        "MUTATION_COMPLETE",
        "NEEDS_REMEDIATION",
        "HOLD",
        "FAIL",
    ),
    PHASE_TYPE_NORMAL_NEXT_WORK_ORDER: (
        "CONTINUE_TO_NEXT_WORK_ORDER",
        "REQUEST_HUMAN_APPROVAL",
        "HOLD",
        "FAIL",
    ),
}

HANDOFF_EVAL_TYPES = frozenset(
    {
        HANDOFF_PROMPT_COMPLETENESS,
        HANDOFF_CONSTRAINT_PRESERVATION,
        HANDOFF_EXECUTION_READINESS,
        HANDOFF_FRESH_SESSION_SUFFICIENCY,
        HANDOFF_PATH_INTEGRITY,
        HANDOFF_RECOVERY_MODE_COMPLETENESS,
        HANDOFF_CURRENT_STATE_COMPLETENESS,
        HANDOFF_RECOVERY_OPTION_CLARITY,
        HANDOFF_OPERATOR_DECISION_GATE,
        HANDOFF_INDEX_STATE_REQUIREMENTS,
        HANDOFF_HOOK_BEHAVIOR_AWARENESS,
        HANDOFF_PUSH_EXECUTION_COMPLETENESS,
        HANDOFF_PUSH_TARGET_CONSTRAINTS,
        HANDOFF_PUSH_EVIDENCE_REQUIREMENTS,
    }
)
SECURITY_HANDOFF_EVAL_TYPES = frozenset(
    {
        SECURITY_HANDOFF_FINDING_REFS_PRESENT,
        SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
        SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
        SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
        SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
        SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
        SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
        READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
    }
)

BLOCKING_FAILED_EVALS = frozenset(
    {
        "approved_mutation_compliance",
        "observe_only_compliance",
        "target_repo_mutation",
        "forbidden_action_compliance",
        "skill_identifier_safety",
        "work_order_render_completeness",
        "next_work_order_recommendation",
        "operator_decision_required_before_execution",
        "operator_decision_validity",
        "operator_decision_reason_completeness",
    }
)

REQUIRED_HANDOFF_SECTIONS = (
    "phase_name",
    "handoff_type",
    "phase_type",
    "required_decision_taxonomy",
    "final_decision",
    "decision_rationale",
    "transition_rationale",
    "fresh_session_rule",
    "source_work_order_id",
    "next_work_order_id",
    "dream_studio_repo_path",
    "target_repo_path",
    "baseline_dream_studio_branch_head",
    "baseline_target_repo_branch_head",
    "objective",
    "capability_boundary",
    "approval_mode",
    "risk_level",
    "scope_include",
    "scope_exclude",
    "approved_files_if_mutation_gated",
    "forbidden_files",
    "allowed_actions",
    "forbidden_actions",
    "approval_artifact_requirement",
    "before_after_evidence_requirements",
    "validation_commands",
    "eval_requirements",
    "report_path",
    "output_artifacts",
    "readiness_rules",
    "expected_verdict",
    "stop_conditions",
    "final_response_must_include",
    "next_handoff_requirements",
    "phase_specific_safety_constraints",
    "handoff_understanding_report_requirement",
    "first_safe_action",
)

RECOVERY_DECISION_REQUIRED_SECTIONS = (
    "source_failure",
    "current_state",
    "known_safe_actions",
    "forbidden_recovery_actions",
    "recovery_options",
    "recommended_option",
    "operator_decision_required",
    "do_not_execute_until_decision",
    "index_state_requirements",
    "hook_behavior_risks",
)

PUSH_EXECUTION_REQUIRED_SECTIONS = (
    "approved_push_target",
    "forbidden_push_targets",
    "before_push_evidence_requirements",
    "push_command",
    "after_push_evidence_requirements",
    "sequential_readiness_rules",
    "expected_verdict",
    "next_prompt_report_requirement",
)

SECURITY_REMEDIATION_REQUIRED_SECTIONS = (
    *REQUIRED_HANDOFF_SECTIONS,
    "target_baseline_constraints",
    "release_gate_decision_rules",
)

UNDERSTANDING_REQUIRED_TERMS = (
    "objective",
    "repositories involved",
    "source Work Order ID",
    "next Work Order ID",
    "approval mode",
    "risk level",
    "approved files",
    "forbidden files",
    "allowed commands/actions",
    "forbidden commands/actions",
    "evidence required",
    "validation required",
    "eval requirements",
    "stop conditions",
    "first safe action",
    "missing context",
)

CONSTRAINT_TERMS = (
    "Do not add DB/event ledger integration",
    "Do not add schema migrations",
    "Do not expand Docker",
    "Do not add dashboard projection integration",
    "Do not add TORII integration",
    "Do not add cloud/org/global sync",
    "Do not add enterprise integration",
    "Do not mutate target repos without explicit approval",
    "Do not change skill identifiers",
    "Do not recreate hooks/lib",
)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _format_list(items: list[Any], *, empty: str = "unavailable") -> str:
    visible = [str(item) for item in items if str(item).strip()]
    if not visible:
        return f"- {empty}"
    return "\n".join(f"- {item}" for item in visible)


def _section(title: str, body: str | list[Any]) -> str:
    if isinstance(body, list):
        rendered = _format_list(body)
    else:
        rendered = str(body).strip() or "unavailable"
    return f"## {title}\n{rendered}\n"


def _extract_prefixed(text: str, label: str) -> str | None:
    pattern = re.compile(rf"(?:^|[;\n])\s*{re.escape(label)}\s*:\s*([^;\n]+)", re.IGNORECASE)
    match = pattern.search(text or "")
    if not match:
        return None
    return match.group(1).strip()


def _extract_work_order_id(text: str, *, fallback: str = "unavailable") -> str:
    for match in re.findall(r"\bwo-[A-Za-z0-9_.-]+\b", text or ""):
        return match
    return fallback


def _section_list(body: str) -> list[str]:
    lines = [line.strip() for line in (body or "").splitlines() if line.strip()]
    bullets: list[str] = []
    for line in lines:
        match = re.match(r"^[-*]\s+(.*)$", line)
        if match:
            bullets.append(match.group(1).strip())
    if bullets:
        return bullets
    return lines or ["unavailable"]


def _section_text(sections: dict[str, str], key: str, *, default: str = "unavailable") -> str:
    return sections.get(key, "").strip() or default


def _section_taxonomy(sections: dict[str, str], phase_type: str) -> list[str]:
    parsed = _section_list(sections.get("required_decision_taxonomy", ""))
    if parsed and parsed != ["unavailable"]:
        return parsed
    return list(DECISION_TAXONOMIES.get(phase_type, ()))


def _next_recommendation(result_metadata: dict[str, Any] | None) -> str:
    if not result_metadata:
        return "unavailable"
    return str(result_metadata.get("next_work_order_recommendation") or "unavailable")


def _transition_rationale(
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    recommendation: str,
) -> str:
    override = _transition_recommendation(work_order, result_metadata)
    if override:
        objective = _extract_prefixed(override, "Objective") or override
        return f"Transition override selected: {objective}"
    return (
        "No transition override was required; the next handoff follows the recorded next Work Order recommendation "
        "and current readiness evidence."
    )


def _metadata_value(
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    *keys: str,
) -> Any:
    context = _handoff_context(work_order, result_metadata)
    for source in (result_metadata or {}, context, work_order):
        for key in keys:
            if isinstance(source, dict) and key in source and source.get(key) not in (None, ""):
                return source.get(key)
    return None


def _metadata_bool(
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    *keys: str,
) -> bool:
    value = _metadata_value(work_order, result_metadata, *keys)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "yes", "1", "performed"}


def _metadata_list(
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    *keys: str,
) -> list[str]:
    for key in keys:
        value = _metadata_value(work_order, result_metadata, key)
        if isinstance(value, list):
            normalized = [str(item) for item in value if str(item).strip()]
        elif value not in (None, ""):
            normalized = [str(value)]
        else:
            normalized = []
        normalized = [
            item
            for item in normalized
            if item.strip().lower() not in {"none", "n/a", "not run", "unavailable", "unknown"}
        ]
        if normalized:
            return normalized
    structured = (result_metadata or {}).get("structured_findings", {})
    if isinstance(structured, dict):
        for key in keys:
            value = structured.get(key)
            if isinstance(value, list):
                normalized = [
                    str(item)
                    for item in value
                    if str(item).strip().lower()
                    not in {"none", "n/a", "not run", "unavailable", "unknown"}
                ]
                if normalized:
                    return normalized
    return []


def _next_work_order_id_from_context(
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    default: str,
) -> str:
    value = _metadata_value(
        work_order, result_metadata, "next_work_order_id", "transition_next_work_order_id"
    )
    return str(value or default)


def _transition_recommendation(
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
) -> str | None:
    source_phase = str(
        _metadata_value(
            work_order, result_metadata, "phase_type", "completed_phase_type", "source_phase_type"
        )
        or ""
    ).lower()
    decision = str(
        _metadata_value(work_order, result_metadata, "decision", "final_decision", "phase_decision")
        or ""
    ).upper()
    release_gate = str(
        _metadata_value(work_order, result_metadata, "release_gate", "current_release_gate") or ""
    )
    changed_files = _metadata_list(
        work_order, result_metadata, "changed_files_after", "files_changed"
    )
    stage_performed = _metadata_bool(
        work_order, result_metadata, "stage_performed", "staging_performed"
    )
    commit_performed = _metadata_bool(work_order, result_metadata, "commit_performed")
    recommendation = _next_recommendation(result_metadata).lower()

    if (
        source_phase in {"bounded_approved_mutation", "approved_mutation"}
        and decision == "MUTATION_COMPLETE"
        and changed_files
        and not stage_performed
        and not commit_performed
    ):
        next_id = _next_work_order_id_from_context(
            work_order, result_metadata, "wo-commit-preparation"
        )
        return (
            f"Phase - Commit Planning; Next Work Order: {next_id}; "
            "Objective: Because the prior phase completed a bounded mutation and left scoped source changes uncommitted, "
            "the next phase is commit preparation before dashboard/projection planning or other unrelated work; "
            "Risk: medium; Approval: approval_required; Non-goals: dashboard/projection planning; "
            "Validation: focused tests, git diff --check, and staged diff checks."
        )

    if source_phase == "commit_planning" and decision in {
        "COMMIT_PLAN_READY",
        "READY_FOR_COMMIT_PLANNING",
    }:
        next_id = _next_work_order_id_from_context(
            work_order, result_metadata, "wo-commit-execution"
        )
        return (
            f"Phase - Commit Execution; Next Work Order: {next_id}; "
            "Objective: Because commit planning is ready, execute the approved commit with exact-path staging and staged diff verification; "
            "Risk: medium; Approval: approval_required; Non-goals: push or unrelated mutation; Validation: focused tests and staged diff checks."
        )

    if source_phase == "commit_execution" and decision == "COMMIT_COMPLETE":
        next_id = _next_work_order_id_from_context(
            work_order, result_metadata, "wo-post-commit-review"
        )
        review_kind = (
            "post-commit release-gate/security review"
            if release_gate or "security" in recommendation
            else "post-commit review"
        )
        return (
            f"Phase - Post-Commit Review; Next Work Order: {next_id}; "
            f"Objective: Because commit execution is complete, perform a {review_kind} before unrelated planning; "
            "Risk: medium; Approval: approval_required; Non-goals: push or new remediation; Validation: file-backed commit scope review."
        )

    if (
        source_phase in {"post_mutation_review", "observe_only_post_mutation_review"}
        and decision
        and any(term in decision for term in ("COMPLETE", "REMEDIATED", "ACCEPTED"))
        and changed_files
        and not commit_performed
    ):
        next_id = _next_work_order_id_from_context(
            work_order, result_metadata, "wo-commit-planning"
        )
        return (
            f"Phase - Commit Planning; Next Work Order: {next_id}; "
            "Objective: Because post-mutation review accepted the remediation while scoped source changes remain uncommitted, plan the commit before unrelated work; "
            "Risk: medium; Approval: approval_required; Non-goals: unrelated planning; Validation: focused tests and commit-scope checks."
        )

    if (
        source_phase in {"observe_only_security_review", "additional_security_review"}
        and decision == "NEEDS_REMEDIATION"
    ):
        next_id = _next_work_order_id_from_context(
            work_order, result_metadata, "wo-remediation-planning"
        )
        return (
            f"Phase - Bounded Remediation Planning; Next Work Order: {next_id}; "
            "Objective: Because observe-only review found blockers, produce bounded remediation planning before implementation; "
            "Risk: medium; Approval: approval_required; Non-goals: mutation or scans; Validation: file-backed evidence review."
        )

    if source_phase == "bounded_remediation_planning" and decision in {
        "REMEDIATION_PLAN_READY",
        "PLAN_READY",
    }:
        next_id = _next_work_order_id_from_context(
            work_order, result_metadata, "wo-bounded-approved-mutation"
        )
        return (
            f"Phase - Bounded Approved Mutation; Next Work Order: {next_id}; "
            "Objective: Because remediation planning is ready, implement only the first approved remediation slice; "
            "Risk: medium; Approval: approval_required; Non-goals: unrelated cleanup; Validation: focused tests."
        )

    if (
        "pause" in recommendation
        or "return-to-core-work" in recommendation
        or "return to core work" in recommendation
    ):
        next_id = _next_work_order_id_from_context(
            work_order, result_metadata, "wo-paused-work-continuity"
        )
        return (
            f"Phase - Pause + Return Continuity; Next Work Order: {next_id}; "
            "Objective: Because the operator chose pause or return-to-core-work while deferred work remains, record paused-work continuity and do not run deferred remediation automatically; "
            "Risk: medium; Approval: approval_required; Non-goals: deferred remediation execution; Validation: pause artifact review."
        )

    if (
        changed_files
        and not commit_performed
        and any(
            term in recommendation for term in ("dashboard", "projection", "unrelated planning")
        )
    ):
        next_id = _next_work_order_id_from_context(
            work_order, result_metadata, "wo-worktree-triage-or-commit-preparation"
        )
        return (
            f"Phase - Commit Planning; Next Work Order: {next_id}; "
            "Objective: Because dirty source files remain before unrelated dashboard/projection planning, triage or commit the worktree first; "
            "Risk: medium; Approval: approval_required; Non-goals: dashboard/projection implementation; Validation: git status and focused tests."
        )

    return None


def _effective_next_recommendation(
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
) -> str:
    return _transition_recommendation(work_order, result_metadata) or _next_recommendation(
        result_metadata
    )


def _milestone_state(
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    context = _handoff_context(work_order, result_metadata)
    for source in (
        (result_metadata or {}).get("milestone_state") if result_metadata else None,
        context.get("milestone_state"),
        work_order.get("milestone_state"),
    ):
        if isinstance(source, dict):
            return source
    return None


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
    _emit_milestone_route_decision(decision, state, work_order, result_metadata)
    return decision


def _emit_milestone_route_decision(
    decision: dict[str, Any],
    state: dict[str, Any],
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
) -> None:
    try:
        from core.telemetry.emitters import TelemetryContext, emit_route_decision

        context = _handoff_context(work_order, result_metadata)
        prd = state.get("prd") if isinstance(state.get("prd"), dict) else {}
        milestone = state.get("milestone") if isinstance(state.get("milestone"), dict) else {}
        stage_gate = state.get("stage_gate") if isinstance(state.get("stage_gate"), dict) else {}
        telemetry_context = TelemetryContext(
            project_id=str(
                prd.get("prd_id")
                or prd.get("project_id")
                or work_order.get("project_name")
                or "dream-studio"
            ),
            milestone_id=str(
                milestone.get("milestone_id")
                or milestone.get("id")
                or decision.get("current_milestone")
                or ""
            ),
            task_id=str(work_order.get("work_order_id") or ""),
            process_run_id=str(context.get("process_run_id") or ""),
            source_refs=tuple(
                str(item) for item in context.get("source_authority_refs", []) if str(item).strip()
            ),
            evidence_refs=tuple(
                str(item) for item in context.get("evidence_refs", []) if str(item).strip()
            ),
            current_stage_gate=str(
                stage_gate.get("stage_gate_id")
                or stage_gate.get("id")
                or decision.get("current_stage_gate")
                or ""
            ),
            current_milestone=str(
                milestone.get("milestone_id")
                or milestone.get("id")
                or decision.get("current_milestone")
                or ""
            ),
            next_stage_gate=str(
                stage_gate.get("next_stage_gate")
                or stage_gate.get("stage_gate_id")
                or stage_gate.get("id")
                or ""
            ),
            next_milestone=str(
                milestone.get("next_milestone") or decision.get("next_milestone") or ""
            ),
        )
        emit_route_decision(decision, context=telemetry_context, state=state)
    except Exception:
        pass


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


def _next_mode(work_order: dict[str, Any], recommendation: str) -> str:
    return _extract_prefixed(recommendation, "Approval") or str(
        work_order.get("approval_mode", "unavailable")
    )


def _next_risk(work_order: dict[str, Any], recommendation: str) -> str:
    return _extract_prefixed(recommendation, "Risk") or str(
        work_order.get("risk_level", "unavailable")
    )


def _next_objective(work_order: dict[str, Any], recommendation: str) -> str:
    return _extract_prefixed(recommendation, "Objective") or (
        recommendation
        if recommendation and recommendation != "unavailable"
        else str(work_order.get("objective", "unavailable"))
    )


def _phase_name(recommendation: str) -> str:
    match = re.search(r"\bPhase\s+[A-Za-z0-9]+[^;\n]*", recommendation or "", re.IGNORECASE)
    return match.group(0).strip() if match else "Next Work Order"


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


def _handoff_type(
    *,
    work_order: dict[str, Any],
    recommendation: str,
    readiness: dict[str, Any],
    next_mode: str,
) -> str:
    if readiness.get("readiness") == HOLD:
        return HANDOFF_TYPE_RECOVERY_DECISION
    if readiness.get("readiness") == FAIL:
        return HANDOFF_TYPE_HOLD_REVIEW
    subject = f"{recommendation} {work_order.get('objective', '')}".lower()
    if "commit" in subject:
        return HANDOFF_TYPE_COMMIT_EXECUTION
    if next_mode == "approval_required":
        return HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION
    return HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER


def _phase_type(
    *,
    work_order: dict[str, Any],
    recommendation: str,
    handoff_type: str,
    next_mode: str,
) -> str:
    subject = f"{recommendation} {work_order.get('objective', '')}".lower()
    if "push planning" in subject or "push-planning" in subject:
        return PHASE_TYPE_PUSH_PLANNING
    if handoff_type == HANDOFF_TYPE_RECOVERY_DECISION or "recovery decision" in subject:
        return PHASE_TYPE_RECOVERY_DECISION
    if (
        "product closeout" in subject
        or "closeout" in subject
        or "retrospective" in subject
        or "case-study" in subject
        or "case study" in subject
    ):
        return PHASE_TYPE_PRODUCT_CLOSEOUT
    if "commit planning" in subject or "human review" in subject:
        return PHASE_TYPE_COMMIT_PLANNING
    if next_mode == "approval_required":
        return PHASE_TYPE_APPROVED_MUTATION
    return PHASE_TYPE_NORMAL_NEXT_WORK_ORDER


def _final_decision(
    *,
    phase_type: str,
    readiness: str,
    can_continue: bool,
    next_mode: str,
) -> str:
    if readiness == FAIL:
        return "FAIL"
    if readiness == HOLD or not can_continue:
        return "HOLD"
    if phase_type == PHASE_TYPE_NORMAL_NEXT_WORK_ORDER:
        if next_mode == "approval_required":
            return "REQUEST_HUMAN_APPROVAL"
        return "CONTINUE_TO_NEXT_WORK_ORDER"
    return "HOLD"


def _decision_rationale(*, phase_type: str, final_decision: str, readiness: str) -> str:
    if final_decision == "HOLD" and phase_type != PHASE_TYPE_NORMAL_NEXT_WORK_ORDER:
        return (
            f"{phase_type} prompts must require the receiving phase report to choose exactly one "
            "allowed decision before claiming execution readiness."
        )
    return f"Final decision {final_decision} follows {readiness} readiness and the {phase_type} taxonomy."


def _source_failure(readiness: dict[str, Any], result_metadata: dict[str, Any] | None) -> list[str]:
    blockers = _as_list(readiness.get("blockers"))
    if blockers:
        return blockers
    if result_metadata:
        summary = str(result_metadata.get("summary", "")).strip()
        if summary:
            return [summary]
    return ["HOLD readiness requires an operator recovery decision before continuation."]


def _current_state_for_recovery(result_metadata: dict[str, Any] | None) -> list[str]:
    structured = result_metadata.get("structured_findings", {}) if result_metadata else {}
    files_changed = _as_list(structured.get("files_changed"))
    current_state = [
        "local commit exists: verify current log; if known from the source report, preserve the local commit evidence.",
        "branch is ahead by local commit count if known; otherwise capture git status before recovery.",
        "staged files remain: capture git diff --cached --name-only before any recovery action.",
        "no push occurred: confirm with git status/log evidence before recovery.",
        "forbidden files were not staged or committed: re-check staged paths before any action.",
    ]
    if files_changed:
        current_state.append(
            f"explicit changed-file evidence from source result: {', '.join(str(item) for item in files_changed)}"
        )
    return current_state


def _known_safe_recovery_actions() -> list[str]:
    return [
        "produce a Handoff Understanding Report",
        "run read-only status/log/diff commands",
        "inspect source Work Order report and evidence artifacts",
        "present recovery options and wait for an operator-selected path",
        "write evidence and reports only under Work Order storage or audit paths",
    ]


def _forbidden_recovery_actions() -> list[str]:
    return [
        "do not edit files before the operator selects a recovery path",
        "do not unstage files before the operator selects a recovery path",
        "do not rollback before the operator selects a recovery path",
        "do not continue commits before the operator selects a recovery path",
        "do not push",
        "do not stage or commit forbidden files",
        "do not run migrations, installs, broad formatters, Docker, dashboard, TORII, cloud, org, global, enterprise, DB/event, hooks/lib, or skill identifier changes",
    ]


def _recovery_options() -> list[str]:
    return [
        "lint remediation: approve the smallest lint fix for approved files, then re-run focused validation and continue only with exact evidence",
        "no-verify continuation: approve local commit continuation with hook bypass risk explicitly accepted; do not push",
        "unstage-and-hold: approve unstaging current index and hold for manual review",
        "rollback: approve exact rollback of the local partial commit and staged paths without touching unrelated dirty files",
    ]


def _handoff_context(
    work_order: dict[str, Any], result_metadata: dict[str, Any] | None
) -> dict[str, Any]:
    context: dict[str, Any] = {}
    for source in (
        work_order.get("handoff_context"),
        (result_metadata or {}).get("handoff_context") if result_metadata else None,
    ):
        if isinstance(source, dict):
            context.update(source)
    return context


def _is_push_execution_handoff(
    *,
    handoff_type: str,
    phase_type: str,
    final_decision: str,
    operator_decision: dict[str, Any] | None,
) -> bool:
    return (
        handoff_type == HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION
        and phase_type == PHASE_TYPE_PUSH_PLANNING
        and final_decision == "PUSH_READY_WITH_APPROVAL"
        and operator_decision is not None
    )


def _push_execution_context(
    *,
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    next_work_order_id: str,
    report_path: Path | str,
) -> dict[str, Any]:
    context = _handoff_context(work_order, result_metadata)
    raw_push = context.get("push_execution", {})
    push = dict(raw_push) if isinstance(raw_push, dict) else {}
    target_path = str(push.get("target_path") or work_order.get("target_path", "unavailable"))
    remote = str(push.get("remote") or "origin")
    branch = str(push.get("branch") or push.get("target_branch") or "unavailable")
    push_command = str(push.get("push_command") or push.get("command") or "")
    if not push_command and target_path != "unavailable" and branch != "unavailable":
        push_command = f'git -C "{target_path}" push {remote} {branch}'
    approval_artifact_path = str(
        push.get("approval_artifact_path")
        or f"<storage_root>/{next_work_order_id}/approvals/approval.json"
    )
    target_label = str(
        push.get("target_display_name")
        or push.get("target_label")
        or push.get("target_name")
        or "target repo"
    )
    return {
        "phase_name": str(push.get("phase_name") or ""),
        "baseline_dream_studio": str(push.get("baseline_dream_studio") or "unknown"),
        "baseline_target": str(push.get("baseline_target") or "unknown"),
        "target_label": target_label,
        "target_path": target_path,
        "remote": remote,
        "branch": branch,
        "push_command": push_command or "unavailable",
        "expected_head": str(push.get("expected_head") or "unavailable"),
        "expected_ahead_behind": str(push.get("expected_ahead_behind") or "unavailable"),
        "local_commits": _as_list(push.get("local_commits")),
        "approval_artifact_path": approval_artifact_path,
        "scope_include": _as_list(push.get("scope_include")),
        "scope_exclude": _as_list(push.get("scope_exclude")),
        "approved_files": _as_list(push.get("approved_files")),
        "forbidden_files": _as_list(push.get("forbidden_files")),
        "validation_commands": _as_list(push.get("validation_commands")),
        "report_path": str(push.get("report_path") or report_path),
    }


def _push_allowed_actions(push: dict[str, Any]) -> list[str]:
    return [
        "produce the Handoff Understanding Report before action",
        "create the approval artifact before push",
        "run read-only Dream Studio and target repo status/log/diff/remote checks",
        "fetch origin before push to verify remote state",
        f"run only the exact Push Command after all before-push gates pass: {push['push_command']}",
        "write evidence and the push execution report only under Dream Studio Work Order storage or audit paths",
    ]


def _push_forbidden_actions() -> list[str]:
    return [
        "no force push",
        "no tags",
        "no pushing any other branch",
        "no pushing any other remote",
        "no delete remote branch",
        "no push with extra refspecs",
        "edits",
        "staging",
        "commits",
        "formatting",
        "validation reruns",
        "schema/test remediation",
        "dependency changes",
        "generated artifacts inside the target repo",
        "Dream Studio DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise changes",
        "hooks/lib recreation",
        "skill identifier changes",
    ]


def _push_approved_files(push: dict[str, Any]) -> list[str]:
    configured = _as_list(push.get("approved_files"))
    if configured:
        return configured
    return [
        f"approved push target: {push['remote']}/{push['branch']}",
        *[f"local commit: {commit}" for commit in _as_list(push.get("local_commits"))],
    ]


def _push_forbidden_files(push: dict[str, Any], scope: dict[str, Any]) -> list[str]:
    configured = _as_list(push.get("forbidden_files"))
    if configured:
        return configured
    return [
        *(_as_list(push.get("scope_exclude")) or _as_list(scope.get("exclude"))),
        "any target repo file edits",
        "any staged or committed files",
        "any generated artifacts inside the target repo",
    ]


def _push_approved_target(push: dict[str, Any]) -> list[str]:
    return [
        f"remote: {push['remote']}",
        f"branch: {push['branch']}",
        f"exact command: {push['push_command']}",
    ]


def _push_before_evidence(push: dict[str, Any]) -> list[str]:
    commits = _as_list(push.get("local_commits"))
    return [
        f"create approval artifact before push: {push['approval_artifact_path']}",
        "capture Dream Studio status and HEAD",
        f"capture target repo status and HEAD for {push['target_label']}",
        f"confirm target repo branch is {push['branch']}",
        f"confirm HEAD is {push['expected_head']}",
        "confirm local commits are exactly:",
        *[f"local commit: {commit}" for commit in commits],
        "confirm index is empty",
        "fetch origin before push",
        f"confirm ahead/behind is exactly {push['expected_ahead_behind']}",
        "confirm unrelated dirty files remain unstaged and uncommitted",
        "confirm no force push, no tags, and no other branch",
    ]


def _push_expected_ahead_count(push: dict[str, Any]) -> str:
    expected = str(push.get("expected_ahead_behind") or "").strip()
    parts = expected.split()
    if len(parts) == 2 and parts[1].isdigit():
        return parts[1]
    return "the expected local commit count"


def _push_after_evidence(push: dict[str, Any]) -> list[str]:
    return [
        "capture push output",
        "capture status after push",
        "capture ahead/behind after push",
        "capture log after push",
        f"prove local branch is no longer ahead by {_push_expected_ahead_count(push)}",
        "prove unrelated dirty files remain local and uncommitted",
        "prove no force push, no tags, and no other branch push",
        "prove no edit/stage/commit occurred during push phase",
    ]


def _push_stop_conditions(push: dict[str, Any]) -> list[str]:
    configured = _as_list(push.get("stop_conditions"))
    if configured:
        return configured
    return [
        "required Handoff Understanding Report is missing",
        "approval artifact is missing or malformed",
        f"target repo branch is not {push['branch']}",
        f"HEAD is not {push['expected_head']}",
        "local commits are not exactly the approved three commits",
        "index is not empty",
        f"ahead/behind is not exactly {push['expected_ahead_behind']} after fetch origin",
        "push command differs from the exact Push Command",
        "force push, tags, other branch, other remote, delete remote branch, or extra refspecs appear",
        "any file is edited, staged, committed, formatted, or remediated",
        "generated artifacts appear inside the target repo",
        "Dream Studio DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise surfaces change",
        "hooks/lib is recreated",
        "skill identifiers change",
    ]


def _push_first_safe_action(push: dict[str, Any]) -> str:
    return (
        "Read this prompt and referenced artifacts, then produce the Handoff Understanding Report. "
        f"After that, create the approval artifact at {push['approval_artifact_path']} "
        "before running read-only pre-push checks; do not push until every before-push gate passes."
    )


def _push_eval_requirements() -> list[str]:
    return [
        HANDOFF_PROMPT_COMPLETENESS,
        HANDOFF_CONSTRAINT_PRESERVATION,
        HANDOFF_EXECUTION_READINESS,
        HANDOFF_FRESH_SESSION_SUFFICIENCY,
        HANDOFF_PUSH_EXECUTION_COMPLETENESS,
        HANDOFF_PUSH_TARGET_CONSTRAINTS,
        HANDOFF_PUSH_EVIDENCE_REQUIREMENTS,
        "operator decision gate satisfied before push execution",
        "approval artifact exists before push",
        "forbidden_action_compliance proves no force push, tags, wrong branch, edits, staging, commits, or authority drift",
        "result_report_completeness includes push output, before/after state, and no-forbidden-action proof",
    ]


def _prior_attempt_summary(
    handoff_context: dict[str, Any],
    result_metadata: dict[str, Any] | None,
) -> list[str]:
    value = handoff_context.get("prior_attempt_outcome_summary") or (result_metadata or {}).get(
        "prior_attempt_outcome_summary"
    )
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        return [f"{key}: {value[key]}" for key in sorted(value)]
    if value:
        return [str(value)]
    if handoff_context.get("requires_prior_attempt_summary"):
        return ["unavailable"]
    return []


def _database_relationship_context(handoff_context: dict[str, Any]) -> list[str]:
    value = handoff_context.get("database_relationship_context")
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, dict):
        required_keys = (
            "current_authority",
            "proposed_authority",
            "source_objects",
            "target_objects",
            "relationship_keys",
            "unresolved_decisions",
            "redaction_boundaries",
            "validation_refs",
        )
        return [f"{key}: {value.get(key, 'unavailable')}" for key in required_keys]
    if value:
        return [str(value)]
    if handoff_context.get("requires_database_relationship_context"):
        return ["unavailable"]
    return []


def _executable_design_boundary(handoff_context: dict[str, Any]) -> list[str]:
    if not handoff_context.get("executable_design_artifact"):
        return []
    return [
        "DRAFT / DO NOT EXECUTE",
        "Executable-looking SQL, scripts, or configs are design artifacts only.",
        "Do not run tooling, execute scripts, apply DDL/DML, or mutate state from this artifact.",
        "A later review and approval Work Order is required before implementation or execution.",
    ]


def _source_authority_refs(handoff_context: dict[str, Any]) -> list[str]:
    return _as_list(handoff_context.get("source_authority_refs")) or [
        "Dream Studio PRD",
        "Dream Studio stage-gate authority",
        "milestone execution state",
        "human-in-the-loop policy",
    ]


def _evidence_refs(
    handoff_context: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    report_path: Path | str,
) -> list[str]:
    refs = _as_list(handoff_context.get("evidence_refs"))
    raw_ref = (result_metadata or {}).get("raw_output_ref")
    if raw_ref:
        refs.append(str(raw_ref))
    refs.append(str(report_path))
    return [ref for ref in refs if str(ref).strip()]


def _validation_refs(
    handoff_context: dict[str, Any],
    work_order: dict[str, Any],
) -> list[str]:
    return _as_list(handoff_context.get("validation_refs")) or _as_list(
        work_order.get("validation_commands")
    )


def _next_allowed_action_after_operator_approval(decision: dict[str, Any]) -> str:
    if not decision.get("human_approval_required") and decision.get("handoff_reason") not in {
        "operator_approval_required",
        "operator_decision_required",
    }:
        return "continue only according to the route decision and stop-gate policy"
    return "resume the approved milestone route, not a default next-prompt chain"


def _with_unique_items(items: list[Any], additions: list[str]) -> list[str]:
    result = [str(item) for item in items if str(item).strip()]
    lowered = "\n".join(result).lower()
    for addition in additions:
        if addition.lower() not in lowered:
            result.append(addition)
            lowered = "\n".join(result).lower()
    return result


def _product_closeout_forbidden_files(items: list[Any]) -> list[str]:
    return _with_unique_items(
        items,
        [
            "any target repo file",
            "generated artifacts inside the target repo",
            "package.json",
            "lockfiles",
            "schema/migration files",
        ],
    )


def _product_closeout_allowed_actions(items: list[Any], scope_include: list[Any]) -> list[str]:
    additions: list[str] = []
    if any("report" in str(item).lower() for item in scope_include):
        additions.append("inspect referenced source report")
    return _with_unique_items(items, additions)


def _readiness_rules(*, phase_type: str, is_push_execution: bool) -> list[str]:
    if phase_type == PHASE_TYPE_PRODUCT_CLOSEOUT:
        return [
            "Proceed only if the source report confirms completed work and no forbidden action.",
            "Proceed only if this phase remains observe-only.",
            "HOLD if any mutation, validation, push, target repo artifact write, authority drift, hooks/lib recreation, or skill identifier drift is requested or detected.",
            "HOLD if the retrospective cannot be produced under Dream Studio meta/audit only.",
            "Future implementation work must be opened as separate Work Orders.",
        ]
    if is_push_execution:
        return [
            "READY_WITH_CONSTRAINTS if push succeeds, ahead/behind becomes 0 0, no forbidden actions occur, and unrelated dirty files remain local.",
            "HOLD if remote state changed before push, index is not empty, HEAD is not expected, or push fails without forbidden action.",
            "FAIL if wrong branch/remote is pushed, force push occurs, tags are pushed, files are edited/staged/committed, or authority drift occurs.",
        ]
    if phase_type == PHASE_TYPE_COMMIT_PLANNING:
        return [
            "Proceed only if reviewed changes can be separated from unrelated dirty work.",
            "Proceed only if the phase remains within its stated approval mode and scope.",
            "HOLD if commit readiness, staging scope, or validation evidence is unclear.",
            "FAIL if forbidden mutation, staging, commit, push, or authority drift occurs.",
        ]
    if phase_type == PHASE_TYPE_RECOVERY_DECISION:
        return [
            "HOLD until the operator selects exactly one recovery option.",
            "Proceed only with a separate recovery_execution handoff after a valid file-backed operator decision.",
            "FAIL if recovery mutation or index changes occur before the operator decision.",
        ]
    return [
        "Proceed only if the source report supports the stated final decision and no stop condition is active.",
        "Proceed only within the stated approval mode, scope, allowed actions, and evidence requirements.",
        "HOLD if required evidence, repository state, or operator decision context is missing.",
        "FAIL if a forbidden action occurs or authority boundaries drift.",
    ]


def _expected_verdict(*, phase_type: str, is_push_execution: bool) -> list[str] | str:
    if phase_type == PHASE_TYPE_PRODUCT_CLOSEOUT:
        return [
            "PASS if the retrospective/case-study planning artifact is produced under Dream Studio meta/audit only, before/after evidence is captured, and no forbidden action occurs.",
            "PASS WITH RISKS if the artifact is produced but unresolved external risks remain, such as target repo dirty worktree, known unrelated test failure, or dependency vulnerability alerts.",
            "HOLD if the phase cannot proceed safely without mutation or missing evidence.",
            "FAIL if a forbidden action occurs.",
        ]
    if is_push_execution:
        return "PASS WITH RISKS if push succeeds and no forbidden action occurs."
    return [
        "PASS if the Work Order completes within scope, required evidence is captured, and no forbidden action occurs.",
        "PASS WITH RISKS if the Work Order completes but bounded residual risks remain.",
        "HOLD if required evidence or safe execution context is missing.",
        "FAIL if a forbidden action occurs.",
    ]


def _output_artifacts(
    work_order: dict[str, Any],
    handoff_context: dict[str, Any],
    report_path_text: str,
) -> list[str]:
    explicit = _as_list(handoff_context.get("output_artifacts"))
    if explicit:
        return explicit
    return [
        f"primary report: {report_path_text}",
        "work-order evidence artifacts under the Work Order storage path when applicable",
        "next handoff prompt artifact when the phase recommends follow-up work",
        *[str(item) for item in _as_list(work_order.get("expected_outputs"))],
    ]


def _final_response_requirements(
    *,
    handoff_type: str,
    phase_type: str,
    handoff_context: dict[str, Any],
) -> list[str]:
    explicit = _as_list(handoff_context.get("final_response_must_include"))
    if explicit:
        return explicit
    required = [
        "Understanding Report summary",
        "branch/HEAD/status evidence gathered in the phase",
        "files inspected or changed, as applicable",
        "validation commands and results, or why validation was not run",
        "artifacts created",
        "boundary confirmation",
        "final verdict",
        "recommended next Work Order",
    ]
    if handoff_type == HANDOFF_TYPE_COMMIT_EXECUTION:
        required.extend(
            [
                "files staged",
                "staged diff confirmation",
                "commit hash if a commit is performed",
            ]
        )
    if phase_type == PHASE_TYPE_COMMIT_PLANNING:
        required.extend(["expected staged files", "commit message recommendation"])
    return required


def _next_handoff_requirements(
    *,
    handoff_context: dict[str, Any],
    next_work_order_id: str,
) -> list[str]:
    explicit = _as_list(handoff_context.get("next_handoff_requirements"))
    if explicit:
        return explicit
    return [
        f"generate or preserve the next handoff for {next_work_order_id}",
        "carry forward source artifact paths and final decision evidence",
        "preserve approval mode, risk level, scope include/exclude, and forbidden actions",
        "do not auto-execute the next phase",
    ]


def _phase_specific_safety_constraints(
    *,
    phase_name: str,
    handoff_type: str,
    phase_type: str,
    approved_files: list[Any],
    handoff_context: dict[str, Any],
) -> list[str]:
    explicit = _as_list(handoff_context.get("phase_specific_safety_constraints"))
    if explicit:
        return explicit
    subject = f"{phase_name} {handoff_type} {phase_type}".lower()
    constraints = [
        "Required first action must be completed before approval artifact creation, source inspection, mutation, staging, commit, push, or validation.",
        "Approval artifact requirement must be satisfied before any approval-gated action.",
        "Allowed commands/actions and forbidden commands/actions must be explicit before execution.",
        "Output artifacts, readiness rules, stop conditions, final response requirements, and next handoff requirements must be present.",
    ]
    if handoff_type == HANDOFF_TYPE_COMMIT_EXECUTION or "commit execution" in subject:
        constraints.extend(
            [
                f"exact staged file list: {', '.join(str(path) for path in approved_files) or 'unavailable'}",
                "stage exact file paths only",
                "do not stage parent directories wholesale",
                "run git diff --cached --name-only after staging",
                "run git diff --cached --stat after staging",
                "run git diff --cached --check before commit",
                "no push unless separately approved",
            ]
        )
    if "pause" in subject or "return" in subject or "paused work" in subject:
        constraints.extend(
            [
                "paused work artifact reference required",
                "completed commit hashes required when applicable",
                "current release gate required",
                "remaining deferred work required",
                "resume requirements required",
                "do not run deferred phases without separate approval",
            ]
        )
    return constraints


def build_handoff_prompt(
    *,
    work_order: dict[str, Any],
    result_metadata: dict[str, Any] | None,
    report_path: Path | str,
    readiness: dict[str, Any],
    decision: dict[str, Any],
    dream_studio_repo_path: Path | str | None = None,
    decision_request: dict[str, Any] | None = None,
    operator_decision: dict[str, Any] | None = None,
) -> str:
    """Build a ready-to-copy prompt or a remediation prompt for HOLD/FAIL states."""
    recommendation = _next_recommendation(result_metadata)
    scope = work_order.get("scope", {})
    handoff_context = _handoff_context(work_order, result_metadata)
    next_mode = str(decision.get("next_work_order_mode", _next_mode(work_order, recommendation)))
    next_work_order_id = str(
        decision.get("next_work_order_id") or _extract_work_order_id(recommendation)
    )
    if not next_work_order_id or next_work_order_id == "unavailable":
        next_work_order_id = "unavailable"

    is_execution_ready = readiness.get("readiness") in {READY, READY_WITH_CONSTRAINTS}
    handoff_type = str(
        decision.get("handoff_type")
        or _handoff_type(
            work_order=work_order,
            recommendation=recommendation,
            readiness=readiness,
            next_mode=next_mode,
        )
    )
    phase_type = str(
        decision.get("phase_type")
        or _phase_type(
            work_order=work_order,
            recommendation=recommendation,
            handoff_type=handoff_type,
            next_mode=next_mode,
        )
    )
    required_decisions = _as_list(decision.get("required_decision_taxonomy")) or list(
        DECISION_TAXONOMIES.get(phase_type, ())
    )
    final_decision = str(
        decision.get("final_decision")
        or _final_decision(
            phase_type=phase_type,
            readiness=str(readiness.get("readiness", HOLD)),
            can_continue=bool(readiness.get("can_continue", False)),
            next_mode=next_mode,
        )
    )
    decision_rationale = str(
        decision.get("decision_rationale")
        or _decision_rationale(
            phase_type=phase_type,
            final_decision=final_decision,
            readiness=str(readiness.get("readiness", HOLD)),
        )
    )
    is_recovery_decision = handoff_type == HANDOFF_TYPE_RECOVERY_DECISION
    is_push_execution = _is_push_execution_handoff(
        handoff_type=handoff_type,
        phase_type=phase_type,
        final_decision=final_decision,
        operator_decision=operator_decision,
    )
    push_context = (
        _push_execution_context(
            work_order=work_order,
            result_metadata=result_metadata,
            next_work_order_id=next_work_order_id,
            report_path=report_path,
        )
        if is_push_execution
        else None
    )
    phase_name = (
        str(push_context.get("phase_name") or _phase_name(recommendation))
        if push_context
        else _phase_name(recommendation)
    )
    report_path_text = str(push_context.get("report_path") if push_context else report_path)
    baseline_dream_studio = (
        str(push_context.get("baseline_dream_studio"))
        if push_context
        else str(
            handoff_context.get("baseline_dream_studio")
            or handoff_context.get("baseline_dream_studio_branch_head")
            or "unknown"
        )
    )
    baseline_target = (
        str(push_context.get("baseline_target"))
        if push_context
        else str(
            handoff_context.get("baseline_target")
            or handoff_context.get("baseline_target_repo_branch_head")
            or "unknown"
        )
    )
    scope_include = (
        _as_list(push_context.get("scope_include")) or _as_list(scope.get("include"))
        if push_context
        else _as_list(scope.get("include"))
    )
    scope_exclude = (
        _as_list(push_context.get("scope_exclude")) or _as_list(scope.get("exclude"))
        if push_context
        else _as_list(scope.get("exclude"))
    )
    approved_files = (
        _push_approved_files(push_context)
        if push_context
        else (
            _as_list(scope.get("include"))
            if next_mode == "approval_required"
            else ["not applicable"]
        )
    )
    forbidden_files = (
        _push_forbidden_files(push_context, scope)
        if push_context
        else _as_list(handoff_context.get("forbidden_files")) or _as_list(scope.get("exclude"))
    )
    allowed_actions = _as_list(handoff_context.get("allowed_actions"))
    if phase_type == PHASE_TYPE_PRODUCT_CLOSEOUT:
        forbidden_files = _product_closeout_forbidden_files(forbidden_files)
        allowed_actions = _product_closeout_allowed_actions(allowed_actions, scope_include)
    validation_commands = (
        _as_list(push_context.get("validation_commands"))
        if push_context and _as_list(push_context.get("validation_commands"))
        else _as_list(work_order.get("validation_commands"))
    )
    stop_conditions = (
        _push_stop_conditions(push_context)
        if push_context
        else _as_list(work_order.get("stop_conditions"))
    )
    first_safe_action = (
        _push_first_safe_action(push_context)
        if push_context
        else str(
            handoff_context.get("first_safe_action")
            or "Read this prompt and referenced artifacts, then produce the Handoff Understanding Report before touching any repository."
        )
    )
    readiness_rules = _readiness_rules(
        phase_type=phase_type,
        is_push_execution=bool(push_context),
    )
    expected_verdict = _expected_verdict(
        phase_type=phase_type,
        is_push_execution=bool(push_context),
    )
    approval_requirement = (
        "Create file-backed approvals/approval.json before mutation. It must list approval_status, approved_by, approved_at, approval_mode, approved_files, forbidden_files, and approval_scope."
        if next_mode == "approval_required"
        else "not applicable for this Work Order mode"
    )
    if push_context:
        approval_requirement = (
            f"Create the approval artifact before push: {push_context['approval_artifact_path']}. "
            "It must list approval_status, approved_by, approved_at, approval_mode, approved_files, forbidden_files, and approval_scope for approved push execution only."
        )
    if is_recovery_decision:
        approval_requirement = (
            "For recovery_decision handoffs, do not mutate files or the git index until the operator selects one recovery path. "
            "Create a new approval artifact before any recovery mutation or index change."
        )
    before_after = str(
        handoff_context.get("before_after_evidence_requirements")
        or "Capture explicit before/after status, diff-name, changed-file, or snapshot evidence before claiming target mutation safety."
    )
    if next_mode == "approval_required":
        before_after += " Approved mutation can pass only when changed-file evidence is wholly within approved_files."
    if push_context:
        before_after = (
            "Before push, capture Dream Studio and target repo branch/index/remote evidence, create the approval artifact, "
            "fetch origin, and prove ahead/behind is exactly the required value. After push, capture push output, status, log, "
            "ahead/behind, no-push-target violations, no edit/stage/commit proof, and unchanged unrelated dirty-file status."
        )

    lines = [
        "# Handoff Packet",
        "",
        _section("Phase Name", phase_name),
        _section("Handoff Type", handoff_type),
        _section("Phase Type", phase_type),
        _section("Required Decision Taxonomy", required_decisions),
        _section("Final Decision", final_decision),
        _section("Decision Rationale", decision_rationale),
        _section(
            "Transition Rationale",
            _transition_rationale(work_order, result_metadata, recommendation),
        ),
        _section(
            "Route Decision",
            str(
                decision.get("route_decision")
                or decision.get("recommended_action")
                or "unavailable"
            ),
        ),
        _section("Handoff Reason", str(decision.get("handoff_reason") or "no_reason_given")),
        _section("Stop Gate", str(decision.get("stop_gate") or "unavailable")),
        _section(
            "Why Internal Continuation Is Not Allowed",
            str(decision.get("why_internal_continuation_is_not_allowed") or "unavailable"),
        ),
        _section(
            "Required Operator Action",
            str(decision.get("required_operator_action") or "unavailable"),
        ),
        _section("Source Authority Refs", _source_authority_refs(handoff_context)),
        _section("Evidence Refs", _evidence_refs(handoff_context, result_metadata, report_path)),
        _section("Validation Refs", _validation_refs(handoff_context, work_order)),
        _section(
            "Next Allowed Action After Operator Approval",
            _next_allowed_action_after_operator_approval(decision),
        ),
        *(
            [
                _section(
                    "Prior Attempt / Outcome Summary",
                    _prior_attempt_summary(handoff_context, result_metadata),
                )
            ]
            if _prior_attempt_summary(handoff_context, result_metadata)
            else []
        ),
        *(
            [
                _section(
                    "Database Relationship Context", _database_relationship_context(handoff_context)
                )
            ]
            if _database_relationship_context(handoff_context)
            else []
        ),
        *(
            [
                _section(
                    "Executable Design Artifact Boundary",
                    _executable_design_boundary(handoff_context),
                )
            ]
            if _executable_design_boundary(handoff_context)
            else []
        ),
        _section(
            "Operator Decision Request",
            _operator_decision_request_summary(decision_request),
        ),
        _section(
            "Operator Decision",
            _operator_decision_summary(operator_decision),
        ),
        _section("Fresh-Session Rule", FRESH_SESSION_RULE),
        _section("Source Work Order ID", str(work_order.get("work_order_id", "unavailable"))),
        _section("Next Work Order ID", next_work_order_id),
        _section("Dream Studio Repo Path", str(dream_studio_repo_path or Path.cwd())),
        _section("Target Repo Path", str(work_order.get("target_path", "unavailable"))),
        _section("Baseline Dream Studio Branch/HEAD", baseline_dream_studio),
        _section("Baseline Target Repo Branch/HEAD", baseline_target),
        _section("Objective", _next_objective(work_order, recommendation)),
        _section(
            "Capability Boundary",
            "\n".join(
                [
                    "This Handoff Packet is not an execution command.",
                    "Do not auto-execute generated prompts.",
                    "Do not add mutation-capable behavior beyond the stated approval mode.",
                    *CONSTRAINT_TERMS,
                ]
            ),
        ),
        _section("Approval Mode", next_mode),
        _section("Risk Level", _next_risk(work_order, recommendation)),
        _section("Scope Include", scope_include),
        _section("Scope Exclude", scope_exclude),
        _section("Approved Files If Mutation-Gated", approved_files),
        _section("Forbidden Files", forbidden_files),
        _section(
            "Allowed Actions",
            (
                _known_safe_recovery_actions()
                if is_recovery_decision
                else (
                    _push_allowed_actions(push_context)
                    if push_context
                    else allowed_actions
                    or [
                        "read this Handoff Packet and referenced artifacts",
                        "produce the Handoff Understanding Report before action",
                        "run listed validation only when it is explicitly safe for the stated mode",
                        "write evidence only to Work Order storage or approved audit paths",
                    ]
                )
            ),
        ),
        _section(
            "Forbidden Actions",
            (
                _forbidden_recovery_actions()
                if is_recovery_decision
                else (
                    _push_forbidden_actions()
                    if push_context
                    else _as_list(work_order.get("forbidden_actions"))
                )
            ),
        ),
        _section("Approval Artifact Requirement", approval_requirement),
        _section("Before/After Evidence Requirements", before_after),
        _section("Validation Commands", validation_commands),
        _section(
            "Eval Requirements",
            (
                _push_eval_requirements()
                if push_context
                else [
                    HANDOFF_PROMPT_COMPLETENESS,
                    HANDOFF_CONSTRAINT_PRESERVATION,
                    HANDOFF_EXECUTION_READINESS,
                    HANDOFF_FRESH_SESSION_SUFFICIENCY,
                    "target_repo_mutation must pass before claiming target mutation safety",
                    "approved_mutation_compliance must pass before claiming approved mutation compliance",
                ]
            ),
        ),
        _section("Report Path", report_path_text),
        _section(
            "Output Artifacts", _output_artifacts(work_order, handoff_context, report_path_text)
        ),
        _section("Readiness Rules", readiness_rules),
        _section("Expected Verdict", expected_verdict),
        _section("Stop Conditions", stop_conditions),
        _section(
            "Final Response Must Include",
            _final_response_requirements(
                handoff_type=handoff_type,
                phase_type=phase_type,
                handoff_context=handoff_context,
            ),
        ),
        _section(
            "Next Handoff Requirements",
            _next_handoff_requirements(
                handoff_context=handoff_context,
                next_work_order_id=next_work_order_id,
            ),
        ),
        _section(
            "Phase-Specific Safety Constraints",
            _phase_specific_safety_constraints(
                phase_name=phase_name,
                handoff_type=handoff_type,
                phase_type=phase_type,
                approved_files=approved_files,
                handoff_context=handoff_context,
            ),
        ),
        _section(
            "Handoff Understanding Report Requirement",
            [
                "Before taking action, produce a Handoff Understanding Report.",
                *UNDERSTANDING_REQUIRED_TERMS,
            ],
        ),
        _section(
            "First Safe Action",
            first_safe_action,
        ),
    ]
    if push_context:
        lines.extend(
            [
                _section("Approved Push Target", _push_approved_target(push_context)),
                _section("Forbidden Push Targets", _push_forbidden_actions()[:6]),
                _section("Before-Push Evidence Requirements", _push_before_evidence(push_context)),
                _section("Push Command", push_context["push_command"]),
                _section("After-Push Evidence Requirements", _push_after_evidence(push_context)),
                _section(
                    "Sequential Readiness Rules",
                    readiness_rules,
                ),
                _section(
                    "Next Prompt/Report Requirement",
                    [
                        "create the push execution report",
                        "if push succeeds, generate post-push retrospective or case-study planning handoff",
                        "if push fails, generate remediation handoff",
                        "do not continue automatically",
                    ],
                ),
            ]
        )
    if is_recovery_decision:
        lines.extend(
            [
                _section("Source Failure", _source_failure(readiness, result_metadata)),
                _section("Current State", _current_state_for_recovery(result_metadata)),
                _section("Known Safe Actions", _known_safe_recovery_actions()),
                _section("Forbidden Recovery Actions", _forbidden_recovery_actions()),
                _section("Recovery Options", _recovery_options()),
                _section(
                    "Recommended Option",
                    "lint remediation, unless the source report explicitly selects another recovery path",
                ),
                _section(
                    "Operator Decision Required",
                    "true - operator must choose one recovery path before any mutation or index change.",
                ),
                _section(
                    "Do Not Execute Until Decision",
                    "true - this is a recovery decision handoff, not a recovery execution prompt.",
                ),
                _section(
                    "Index State Requirements",
                    "\n".join(
                        [
                            "Capture git diff --cached --name-only before recovery.",
                            "Record current staged files and any branch-ahead state.",
                            "After any hook attempt, re-check working tree and index.",
                            "Stop if a forbidden file is staged or committed.",
                        ]
                    ),
                ),
                _section(
                    "Hook Behavior Risks",
                    "\n".join(
                        [
                            "pre-commit, lint-staged, or other hooks may modify files.",
                            "After any hook attempt, re-check working tree and index.",
                            "Never assume hooks are non-mutating.",
                        ]
                    ),
                ),
                _section(
                    "Decision Gate",
                    "The operator must choose lint remediation, no-verify continuation, unstage-and-hold, or rollback before any recovery execution.",
                ),
            ]
        )
    elif not is_execution_ready:
        lines.extend(
            [
                "## Remediation Required",
                "Do not execute the next Work Order. Resolve the blockers below before producing an execution prompt.",
                _format_list(_as_list(readiness.get("blockers"))),
                "",
            ]
        )
    return "\n".join(lines).replace("\n\n\n", "\n\n").strip() + "\n"


def _operator_decision_request_summary(decision_request: dict[str, Any] | None) -> list[str]:
    if not decision_request:
        return ["not required or not yet requested"]
    if decision_request.get("_invalid"):
        return [f"invalid: {decision_request['_invalid']}"]
    return [
        f"path: {decision_request.get('_path', 'unavailable')}",
        f"decision_request_id: {decision_request.get('decision_request_id', 'unavailable')}",
        f"status: {decision_request.get('status', 'unavailable')}",
        f"phase_type: {decision_request.get('phase_type', 'unavailable')}",
        f"recommended_decision: {decision_request.get('recommended_decision', 'unavailable')}",
        "operator_decision artifact required before generating an execution handoff for this request",
    ]


def _operator_decision_summary(operator_decision: dict[str, Any] | None) -> list[str]:
    if not operator_decision:
        return ["not recorded"]
    if operator_decision.get("_invalid"):
        return [f"invalid: {operator_decision['_invalid']}"]
    return [
        f"path: {operator_decision.get('_path', 'unavailable')}",
        f"decision: {operator_decision.get('decision', 'unavailable')}",
        f"decided_by: {operator_decision.get('decided_by', 'unavailable')}",
        f"approved_next_handoff_type: {operator_decision.get('approved_next_handoff_type', 'unavailable')}",
        "operator decision is file-backed evidence only and does not execute work by itself",
    ]


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


def _normalize_heading(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def parse_prompt_sections(prompt_text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in prompt_text.splitlines():
        if line.startswith("## "):
            current = _normalize_heading(line[3:])
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return {key: "\n".join(value).strip() for key, value in sections.items()}


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


def _body_missing(value: str, *, allow_unknown: bool = False) -> bool:
    text = value.strip()
    if not text:
        return True
    lowered = text.lower()
    if allow_unknown and lowered == "unknown":
        return False
    return lowered in {"unavailable", "- unavailable"}


def _is_push_execution_sections(sections: dict[str, str]) -> bool:
    return (
        sections.get("handoff_type", "").strip() == HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION
        and sections.get("phase_type", "").strip() == PHASE_TYPE_PUSH_PLANNING
        and sections.get("final_decision", "").strip() == "PUSH_READY_WITH_APPROVAL"
    )


def _profile_contract_missing(sections: dict[str, str], prompt_text: str) -> list[str]:
    combined = "\n".join(
        [
            prompt_text,
            sections.get("phase_name", ""),
            sections.get("handoff_type", ""),
            sections.get("phase_type", ""),
            sections.get("objective", ""),
            sections.get("phase_specific_safety_constraints", ""),
            sections.get("final_response_must_include", ""),
            sections.get("next_handoff_requirements", ""),
        ]
    ).lower()
    missing: list[str] = []

    required_contract_terms = (
        "required first action",
        "approval artifact",
        "allowed commands",
        "forbidden commands",
        "output artifacts",
        "readiness rules",
        "stop conditions",
        "final response",
        "next handoff",
    )
    for term in required_contract_terms:
        if term not in combined:
            missing.append(f"phase_specific_contract.{term}")

    if (
        sections.get("handoff_type", "").strip() == HANDOFF_TYPE_COMMIT_EXECUTION
        or "commit execution" in combined
    ):
        commit_terms = (
            "exact staged file list",
            "stage exact file paths only",
            "do not stage parent directories wholesale",
            "git diff --cached --name-only",
            "git diff --cached --stat",
            "git diff --cached --check",
            "no push unless separately approved",
        )
        for term in commit_terms:
            if term not in combined:
                missing.append(f"commit_execution_contract.{term}")

    if "pause" in combined or "return" in combined or "paused work" in combined:
        pause_terms = (
            "paused work artifact",
            "completed commit hashes",
            "current release gate",
            "remaining deferred work",
            "resume requirements",
            "do not run deferred phases",
        )
        for term in pause_terms:
            if term not in combined:
                missing.append(f"pause_return_contract.{term}")

    return missing


_MALFORMED_DREAM_STUDIO_META_ROOT_RE = re.compile(
    r"[A-Za-z]:\\Users\\[^\\\r\n]+\.dream-studio(?=\\|/|\s|$)"
)
_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s`<>\"|]+")


def _handoff_path_integrity_problems(prompt_text: str) -> list[str]:
    problems: list[str] = []
    malformed_roots = sorted(set(_MALFORMED_DREAM_STUDIO_META_ROOT_RE.findall(prompt_text)))
    problems.extend(f"malformed_dream_studio_meta_root:{root}" for root in malformed_roots)

    for path in sorted(set(_WINDOWS_ABSOLUTE_PATH_RE.findall(prompt_text))):
        if ".dream-studio" not in path:
            continue
        if "\\.dream-studio" in path or "/.dream-studio" in path:
            continue
        problems.append(f"missing_separator_before_dream_studio_segment:{path}")

    return sorted(set(problems))


def dry_run_handoff_prompt(
    prompt_text: str,
    *,
    target_repo_required: bool = True,
    approval_required: bool | None = None,
) -> dict[str, Any]:
    """Extract required fields from a Handoff Packet without executing it."""
    sections = parse_prompt_sections(prompt_text)
    extracted = {field: sections.get(field, "") for field in REQUIRED_HANDOFF_SECTIONS}
    missing: list[str] = []
    for field in REQUIRED_HANDOFF_SECTIONS:
        if field == "target_repo_path" and not target_repo_required:
            continue
        allow_unknown = field.startswith("baseline_")
        if field not in sections or _body_missing(
            sections.get(field, ""), allow_unknown=allow_unknown
        ):
            missing.append(field)

    prompt_approval_required = (
        approval_required
        if approval_required is not None
        else "approval_required" in sections.get("approval_mode", "")
    )
    if prompt_approval_required:
        approved_body = sections.get("approved_files_if_mutation_gated", "")
        approval_body = sections.get("approval_artifact_requirement", "")
        if "not applicable" in approved_body.lower():
            missing.append("approved_files_if_mutation_gated")
        if "not applicable" in approval_body.lower():
            missing.append("approval_artifact_requirement")

    handoff_type = sections.get("handoff_type", "").strip()
    if handoff_type and handoff_type not in HANDOFF_TYPES:
        missing.append("handoff_type")
    phase_type = sections.get("phase_type", "").strip()
    if phase_type and phase_type not in DECISION_TAXONOMIES:
        missing.append("phase_type")
    required_taxonomy_body = sections.get("required_decision_taxonomy", "")
    final_decision = sections.get("final_decision", "").strip()
    allowed_decisions = DECISION_TAXONOMIES.get(phase_type, ())
    if phase_type in DECISION_TAXONOMIES:
        missing_decisions = [
            decision for decision in allowed_decisions if decision not in required_taxonomy_body
        ]
        if missing_decisions:
            missing.append("required_decision_taxonomy")
    if handoff_type == HANDOFF_TYPE_RECOVERY_DECISION:
        for field in RECOVERY_DECISION_REQUIRED_SECTIONS:
            if field not in sections or _body_missing(sections.get(field, "")):
                missing.append(field)
    if _is_push_execution_sections(sections):
        for field in PUSH_EXECUTION_REQUIRED_SECTIONS:
            if field not in sections or _body_missing(sections.get(field, "")):
                missing.append(field)

    if FRESH_SESSION_RULE not in prompt_text:
        missing.append("fresh_session_rule")
    understanding = sections.get("handoff_understanding_report_requirement", "")
    for term in UNDERSTANDING_REQUIRED_TERMS:
        if term not in understanding:
            missing.append(f"handoff_understanding_report_requirement.{term}")
    missing.extend(_profile_contract_missing(sections, prompt_text))
    path_integrity_problems = _handoff_path_integrity_problems(prompt_text)
    if path_integrity_problems:
        missing.append(HANDOFF_PATH_INTEGRITY)

    unique_missing = sorted(set(missing))
    readiness = "fail" if unique_missing else "pass"
    return {
        "extracted_fields": extracted,
        "missing_fields": unique_missing,
        "path_integrity_problems": path_integrity_problems,
        "readiness": readiness,
    }


def _not_applicable_recovery_eval(eval_type: str) -> dict[str, Any]:
    return {
        "pass_fail": "pass",
        "observed_behavior": f"{eval_type} is not applicable to this non-recovery handoff.",
        "score": 1,
        "evidence": ["handoff_type"],
    }


def _not_applicable_push_eval(eval_type: str) -> dict[str, Any]:
    return {
        "pass_fail": "pass",
        "observed_behavior": f"{eval_type} is not applicable to this non-push-execution handoff.",
        "score": 1,
        "evidence": ["handoff_type", "phase_type", "final_decision"],
    }


def _eval_result(
    *,
    pass_fail: str,
    observed_behavior: str,
    evidence: list[str],
) -> dict[str, Any]:
    return {
        "pass_fail": pass_fail,
        "observed_behavior": observed_behavior,
        "score": 1 if pass_fail == "pass" else 0,
        "evidence": evidence,
    }


def _evaluate_push_execution_completeness(
    sections: dict[str, str],
    is_push_execution: bool,
) -> dict[str, Any]:
    if not is_push_execution:
        return _not_applicable_push_eval(HANDOFF_PUSH_EXECUTION_COMPLETENESS)
    missing = [
        section
        for section in PUSH_EXECUTION_REQUIRED_SECTIONS
        if section not in sections or _body_missing(sections.get(section, ""))
    ]
    if missing:
        return _eval_result(
            pass_fail="fail",
            observed_behavior=f"push execution handoff missing sections: {', '.join(missing)}.",
            evidence=missing,
        )
    return _eval_result(
        pass_fail="pass",
        observed_behavior="push execution handoff includes required push-specific sections.",
        evidence=list(PUSH_EXECUTION_REQUIRED_SECTIONS),
    )


def _evaluate_push_target_constraints(
    sections: dict[str, str],
    is_push_execution: bool,
) -> dict[str, Any]:
    if not is_push_execution:
        return _not_applicable_push_eval(HANDOFF_PUSH_TARGET_CONSTRAINTS)
    combined = "\n".join(
        [
            sections.get("approved_push_target", ""),
            sections.get("forbidden_push_targets", ""),
            sections.get("push_command", ""),
            sections.get("forbidden_actions", ""),
        ]
    ).lower()
    required_terms = (
        "remote: origin",
        "branch:",
        "git -c",
        "push origin",
        "no force push",
        "no tags",
        "no pushing any other branch",
        "no pushing any other remote",
        "no delete remote branch",
        "no push with extra refspecs",
    )
    missing = [term for term in required_terms if term not in combined]
    command_body = sections.get("push_command", "")
    if "git -C" not in command_body or " push origin " not in command_body:
        missing.append("exact push command")
    if missing:
        return _eval_result(
            pass_fail="fail",
            observed_behavior=f"push execution handoff omits push target constraints: {', '.join(sorted(set(missing)))}.",
            evidence=sorted(set(missing)),
        )
    return _eval_result(
        pass_fail="pass",
        observed_behavior="push execution handoff constrains remote, branch, command, force-push, tags, other remotes, other branches, deletes, and extra refspecs.",
        evidence=["approved_push_target", "forbidden_push_targets", "push_command"],
    )


def _evaluate_push_evidence_requirements(
    sections: dict[str, str],
    is_push_execution: bool,
) -> dict[str, Any]:
    if not is_push_execution:
        return _not_applicable_push_eval(HANDOFF_PUSH_EVIDENCE_REQUIREMENTS)
    combined = "\n".join(
        [
            sections.get("approval_artifact_requirement", ""),
            sections.get("before_push_evidence_requirements", ""),
            sections.get("after_push_evidence_requirements", ""),
            sections.get("sequential_readiness_rules", ""),
        ]
    ).lower()
    required_terms = (
        "approval artifact",
        "dream studio status",
        "target repo status",
        "branch is",
        "head is",
        "local commits are exactly",
        "index is empty",
        "fetch origin",
        "ahead/behind is exactly",
        "unrelated dirty files",
        "no force push",
        "capture push output",
        "status after push",
        "ahead/behind after push",
        "log after push",
        "no edit/stage/commit",
        "ahead/behind becomes 0 0",
    )
    missing = [term for term in required_terms if term not in combined]
    if missing:
        return _eval_result(
            pass_fail="fail",
            observed_behavior=f"push execution handoff omits evidence gates: {', '.join(missing)}.",
            evidence=missing,
        )
    return _eval_result(
        pass_fail="pass",
        observed_behavior="push execution handoff requires approval, before-push, after-push, fetch, ahead/behind, HEAD, index, and no-forbidden-action evidence.",
        evidence=[
            "approval_artifact_requirement",
            "before_push_evidence_requirements",
            "after_push_evidence_requirements",
            "sequential_readiness_rules",
        ],
    )


def _evaluate_recovery_mode(
    prompt_text: str,
    sections: dict[str, str],
    is_recovery_decision: bool,
) -> dict[str, Any]:
    if not is_recovery_decision:
        return _not_applicable_recovery_eval(HANDOFF_RECOVERY_MODE_COMPLETENESS)
    missing = [
        section
        for section in RECOVERY_DECISION_REQUIRED_SECTIONS
        if section not in sections or _body_missing(sections.get(section, ""))
    ]
    allowed_actions = sections.get("allowed_actions", "").lower()
    direct_execution_markers = (
        "stage only exact files",
        "create local commits",
        "run git commit",
        "execute recovery immediately",
    )
    blends_execution = any(marker in allowed_actions for marker in direct_execution_markers)
    has_gate = (
        "operator must choose" in prompt_text.lower()
        and "do_not_execute_until_decision" in sections
        and "true" in sections.get("do_not_execute_until_decision", "").lower()
    )
    if missing:
        return _eval_result(
            pass_fail="fail",
            observed_behavior=f"recovery_decision handoff missing sections: {', '.join(missing)}.",
            evidence=missing,
        )
    if blends_execution and not has_gate:
        return _eval_result(
            pass_fail="fail",
            observed_behavior="recovery_decision handoff blends decision and execution without an operator-selected path.",
            evidence=["allowed_actions", "operator_decision_required"],
        )
    if "no push" not in prompt_text.lower() or "forbidden file" not in prompt_text.lower():
        return _eval_result(
            pass_fail="fail",
            observed_behavior="recovery_decision handoff omits no-push or no-forbidden-staging constraints.",
            evidence=["forbidden_recovery_actions", "current_state"],
        )
    return _eval_result(
        pass_fail="pass",
        observed_behavior="recovery_decision handoff includes required recovery mode fields and remains decision-only.",
        evidence=["handoff_type", *RECOVERY_DECISION_REQUIRED_SECTIONS],
    )


def _evaluate_current_state(sections: dict[str, str], is_recovery_decision: bool) -> dict[str, Any]:
    if not is_recovery_decision:
        return _not_applicable_recovery_eval(HANDOFF_CURRENT_STATE_COMPLETENESS)
    body = sections.get("current_state", "").lower()
    required = ("local commit", "branch is ahead", "staged files", "no push", "forbidden files")
    missing = [term for term in required if term not in body]
    if missing:
        return _eval_result(
            pass_fail="fail",
            observed_behavior=f"recovery current state omits: {', '.join(missing)}.",
            evidence=missing,
        )
    return _eval_result(
        pass_fail="pass",
        observed_behavior="recovery current state records local commit, branch-ahead, staged/index, no-push, and forbidden-file status requirements.",
        evidence=["current_state"],
    )


def _evaluate_recovery_options(
    sections: dict[str, str], is_recovery_decision: bool
) -> dict[str, Any]:
    if not is_recovery_decision:
        return _not_applicable_recovery_eval(HANDOFF_RECOVERY_OPTION_CLARITY)
    options = sections.get("recovery_options", "").lower()
    recommended = sections.get("recommended_option", "").lower()
    required = ("lint remediation", "no-verify continuation", "unstage-and-hold", "rollback")
    missing = [term for term in required if term not in options]
    if missing or "lint remediation" not in recommended:
        evidence = missing or ["recommended_option"]
        return _eval_result(
            pass_fail="fail",
            observed_behavior="recovery prompt omits required recovery options or recommended safest option.",
            evidence=evidence,
        )
    return _eval_result(
        pass_fail="pass",
        observed_behavior="recovery prompt lists options and recommends lint remediation unless source evidence says otherwise.",
        evidence=["recovery_options", "recommended_option"],
    )


def _evaluate_operator_gate(sections: dict[str, str], is_recovery_decision: bool) -> dict[str, Any]:
    if not is_recovery_decision:
        return _not_applicable_recovery_eval(HANDOFF_OPERATOR_DECISION_GATE)
    operator = sections.get("operator_decision_required", "").lower()
    do_not_execute = sections.get("do_not_execute_until_decision", "").lower()
    decision_gate = sections.get("decision_gate", "").lower()
    if "true" not in operator or "operator must choose" not in operator:
        return _eval_result(
            pass_fail="fail",
            observed_behavior="recovery prompt does not require an operator decision before action.",
            evidence=["operator_decision_required"],
        )
    if "true" not in do_not_execute or "not a recovery execution prompt" not in do_not_execute:
        return _eval_result(
            pass_fail="fail",
            observed_behavior="recovery prompt does not clearly block execution until a decision exists.",
            evidence=["do_not_execute_until_decision"],
        )
    if "operator must choose" not in decision_gate:
        return _eval_result(
            pass_fail="fail",
            observed_behavior="recovery prompt omits a decision gate.",
            evidence=["decision_gate"],
        )
    return _eval_result(
        pass_fail="pass",
        observed_behavior="recovery prompt requires an operator decision before any mutation or index change.",
        evidence=["operator_decision_required", "do_not_execute_until_decision", "decision_gate"],
    )


def _evaluate_index_requirements(
    prompt_text: str,
    sections: dict[str, str],
    is_recovery_decision: bool,
) -> dict[str, Any]:
    if not is_recovery_decision:
        return _not_applicable_recovery_eval(HANDOFF_INDEX_STATE_REQUIREMENTS)
    needs_index = any(
        term in prompt_text.lower() for term in ("staged", "index", "git diff --cached")
    )
    body = sections.get("index_state_requirements", "").lower()
    if not needs_index:
        return _eval_result(
            pass_fail="pass",
            observed_behavior="recovery prompt does not involve git staging or index state.",
            evidence=["index_state_not_involved"],
        )
    required = ("git diff --cached --name-only", "staged", "index", "forbidden")
    missing = [term for term in required if term not in body]
    if missing:
        return _eval_result(
            pass_fail="fail",
            observed_behavior=f"recovery prompt omits index state requirements: {', '.join(missing)}.",
            evidence=missing,
        )
    return _eval_result(
        pass_fail="pass",
        observed_behavior="recovery prompt requires explicit staged/index evidence and forbidden-file checks.",
        evidence=["index_state_requirements"],
    )


def _evaluate_hook_awareness(
    prompt_text: str,
    sections: dict[str, str],
    is_recovery_decision: bool,
) -> dict[str, Any]:
    if not is_recovery_decision:
        return _not_applicable_recovery_eval(HANDOFF_HOOK_BEHAVIOR_AWARENESS)
    hook_involved = any(
        term in prompt_text.lower() for term in ("pre-commit", "lint-staged", "hook")
    )
    body = sections.get("hook_behavior_risks", "").lower()
    if not hook_involved:
        return _eval_result(
            pass_fail="pass",
            observed_behavior="recovery source does not indicate hook involvement.",
            evidence=["hook_not_involved"],
        )
    required = (
        "may modify files",
        "re-check working tree and index",
        "never assume hooks are non-mutating",
    )
    missing = [term for term in required if term not in body]
    if missing:
        return _eval_result(
            pass_fail="fail",
            observed_behavior=f"recovery prompt omits hook behavior risks: {', '.join(missing)}.",
            evidence=missing,
        )
    return _eval_result(
        pass_fail="pass",
        observed_behavior="recovery prompt treats pre-commit/lint-staged hooks as potentially mutating and requires re-checks.",
        evidence=["hook_behavior_risks"],
    )


def _decision_taxonomy_problems(sections: dict[str, str]) -> list[str]:
    phase_type = sections.get("phase_type", "").strip()
    taxonomy_body = sections.get("required_decision_taxonomy", "")
    final_decision = sections.get("final_decision", "").strip()
    if not phase_type or phase_type not in DECISION_TAXONOMIES:
        return ["phase_type invalid or unavailable"]
    allowed = DECISION_TAXONOMIES[phase_type]
    problems = [
        f"required decision missing from taxonomy: {decision}"
        for decision in allowed
        if decision not in taxonomy_body
    ]
    if final_decision not in allowed:
        problems.append(
            f"final decision {final_decision or 'unavailable'} is not allowed for {phase_type}"
        )
    return problems


def evaluate_handoff_prompt(
    prompt_text: str,
    *,
    readiness: str,
    can_continue: bool,
    target_repo_required: bool = True,
    approval_required: bool | None = None,
) -> dict[str, dict[str, Any]]:
    """Run deterministic handoff evals over a generated prompt."""
    simulation = dry_run_handoff_prompt(
        prompt_text,
        target_repo_required=target_repo_required,
        approval_required=approval_required,
    )
    sections = parse_prompt_sections(prompt_text)
    handoff_type = sections.get("handoff_type", "").strip()
    is_recovery_decision = handoff_type == HANDOFF_TYPE_RECOVERY_DECISION
    is_push_execution = _is_push_execution_sections(sections)
    missing = simulation["missing_fields"]
    completeness_status = "pass" if not missing else "fail"
    path_integrity_problems = simulation.get("path_integrity_problems", [])
    path_status = "pass" if not path_integrity_problems else "fail"

    missing_constraints = [term for term in CONSTRAINT_TERMS if term not in prompt_text]
    constraint_status = "pass" if not missing_constraints else "fail"

    has_handoff_packet = "# Handoff Packet" in prompt_text
    if can_continue and readiness in {READY, READY_WITH_CONSTRAINTS}:
        execution_status = (
            "pass"
            if has_handoff_packet
            and handoff_type not in {HANDOFF_TYPE_RECOVERY_DECISION, HANDOFF_TYPE_HOLD_REVIEW}
            else "fail"
        )
        execution_observed = (
            "execution handoff prompt is present for a continuation-ready report"
            if execution_status == "pass"
            else "continuation-ready report did not include an execution Handoff Packet"
        )
    else:
        execution_status = (
            "pass"
            if has_handoff_packet
            and handoff_type in {HANDOFF_TYPE_RECOVERY_DECISION, HANDOFF_TYPE_HOLD_REVIEW}
            else "fail"
        )
        execution_observed = (
            "HOLD/FAIL report produced a non-executing recovery or hold handoff"
            if execution_status == "pass"
            else "HOLD/FAIL report did not produce a recovery or hold handoff"
        )
    decision_problems = _decision_taxonomy_problems(sections)
    if decision_problems:
        execution_status = "fail"
        execution_observed = (
            f"{execution_observed}; decision taxonomy invalid: {', '.join(decision_problems)}"
        )

    fresh_missing = []
    if FRESH_SESSION_RULE not in prompt_text:
        fresh_missing.append("fresh-session rule")
    if "Handoff Understanding Report" not in prompt_text:
        fresh_missing.append("Handoff Understanding Report requirement")
    fresh_status = "pass" if not fresh_missing else "fail"

    recovery_mode = _evaluate_recovery_mode(prompt_text, sections, is_recovery_decision)
    current_state = _evaluate_current_state(sections, is_recovery_decision)
    recovery_options = _evaluate_recovery_options(sections, is_recovery_decision)
    operator_gate = _evaluate_operator_gate(sections, is_recovery_decision)
    index_requirements = _evaluate_index_requirements(prompt_text, sections, is_recovery_decision)
    hook_awareness = _evaluate_hook_awareness(prompt_text, sections, is_recovery_decision)
    push_completeness = _evaluate_push_execution_completeness(sections, is_push_execution)
    push_target_constraints = _evaluate_push_target_constraints(sections, is_push_execution)
    push_evidence_requirements = _evaluate_push_evidence_requirements(
        sections,
        is_push_execution,
    )

    return {
        HANDOFF_PROMPT_COMPLETENESS: {
            "pass_fail": completeness_status,
            "observed_behavior": (
                "handoff prompt includes required fields"
                if completeness_status == "pass"
                else f"handoff prompt missing critical fields: {', '.join(missing)}"
            ),
            "score": 1 if completeness_status == "pass" else 0,
            "evidence": missing or ["required_sections"],
            "simulation": simulation,
        },
        HANDOFF_CONSTRAINT_PRESERVATION: {
            "pass_fail": constraint_status,
            "observed_behavior": (
                "handoff prompt preserves authority constraints"
                if constraint_status == "pass"
                else f"handoff prompt missing authority constraints: {', '.join(missing_constraints)}"
            ),
            "score": 1 if constraint_status == "pass" else 0,
            "evidence": missing_constraints or ["constraint_terms"],
        },
        HANDOFF_EXECUTION_READINESS: {
            "pass_fail": execution_status,
            "observed_behavior": execution_observed,
            "score": 1 if execution_status == "pass" else 0,
            "evidence": [readiness, f"can_continue={str(can_continue).lower()}"],
        },
        HANDOFF_FRESH_SESSION_SUFFICIENCY: {
            "pass_fail": fresh_status,
            "observed_behavior": (
                "handoff prompt includes fresh-session rule and understanding report requirement"
                if fresh_status == "pass"
                else f"handoff prompt missing fresh-session requirements: {', '.join(fresh_missing)}"
            ),
            "score": 1 if fresh_status == "pass" else 0,
            "evidence": fresh_missing or ["fresh_session_rule", "handoff_understanding_report"],
        },
        HANDOFF_PATH_INTEGRITY: {
            "pass_fail": path_status,
            "observed_behavior": (
                "handoff prompt preserves Dream Studio artifact path separators"
                if path_status == "pass"
                else "handoff prompt contains malformed Dream Studio artifact paths: "
                + ", ".join(path_integrity_problems)
            ),
            "score": 1 if path_status == "pass" else 0,
            "evidence": path_integrity_problems or ["dream_studio_artifact_paths"],
        },
        HANDOFF_RECOVERY_MODE_COMPLETENESS: recovery_mode,
        HANDOFF_CURRENT_STATE_COMPLETENESS: current_state,
        HANDOFF_RECOVERY_OPTION_CLARITY: recovery_options,
        HANDOFF_OPERATOR_DECISION_GATE: operator_gate,
        HANDOFF_INDEX_STATE_REQUIREMENTS: index_requirements,
        HANDOFF_HOOK_BEHAVIOR_AWARENESS: hook_awareness,
        HANDOFF_PUSH_EXECUTION_COMPLETENESS: push_completeness,
        HANDOFF_PUSH_TARGET_CONSTRAINTS: push_target_constraints,
        HANDOFF_PUSH_EVIDENCE_REQUIREMENTS: push_evidence_requirements,
    }


def _artifact_path_label(path: Path | str | None) -> str:
    return str(path) if path else "unavailable"


def _nested_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def _security_next_recommendation(security_report: dict[str, Any]) -> dict[str, Any]:
    value = security_report.get("next_work_order_recommendation")
    return value if isinstance(value, dict) else {}


def _finding_short_id(finding_id: str) -> str:
    marker = "sec.finding.bill_stack."
    if finding_id.startswith(marker):
        return finding_id[len(marker) :]
    return finding_id.split(".")[-1]


def _security_finding_refs(finding_records: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for finding in finding_records:
        finding_id = str(finding.get("finding_id", "")).strip()
        if not finding_id:
            continue
        refs.append(f"{_finding_short_id(finding_id)} ({finding_id})")
    return refs or ["unavailable"]


def _security_finding_ids(finding_records: list[dict[str, Any]]) -> list[str]:
    ids = [str(finding.get("finding_id", "")).strip() for finding in finding_records]
    return [finding_id for finding_id in ids if finding_id]


def _extract_target_path_from_report(source_report_text: str, target_id: str) -> str:
    target_label = re.escape(target_id.replace("-", " "))
    patterns = (
        rf"{target_label}\s+target:\s*([^\n]+)",
        r"Target Repo Path\s*\n([^\n]+)",
        r"Target Repo Path\s*:\s*([^\n]+)",
    )
    for pattern in patterns:
        match = re.search(pattern, source_report_text, flags=re.IGNORECASE)
        if match:
            candidate = match.group(1).strip().strip("`")
            candidate = re.split(r"`?,\s+", candidate, maxsplit=1)[0].strip().strip("`")
            return candidate
    return "not supplied; confirm before any target access"


def _target_branch_head_from_evidence(
    evidence_records: list[dict[str, Any]],
) -> tuple[str, str]:
    for evidence in evidence_records:
        branch_head = evidence.get("branch_head")
        if not isinstance(branch_head, dict):
            continue
        branch = str(branch_head.get("target_branch") or branch_head.get("branch") or "").strip()
        head = str(branch_head.get("target_head") or branch_head.get("head") or "").strip()
        if branch or head:
            return branch or "unknown", head or "unknown"
    return "unknown", "unknown"


def _target_untracked_entries(evidence_records: list[dict[str, Any]]) -> list[str]:
    entries: list[str] = []
    for evidence in evidence_records:
        for key in ("before_status", "after_status", "no_target_mutation_proof"):
            body = str(evidence.get(key, ""))
            for line in body.splitlines():
                match = re.match(r"\s*\?\?\s+(.+?)\s*$", line)
                if match:
                    entries.append(match.group(1).strip())
    deduped: list[str] = []
    for entry in entries:
        if entry and entry not in deduped:
            deduped.append(entry)
    return deduped


def _security_release_gate_decision(
    security_report: dict[str, Any],
    release_gate: dict[str, Any],
) -> str:
    decision = str(release_gate.get("decision", "")).strip()
    if decision:
        return decision
    embedded = security_report.get("release_gate_decision")
    if isinstance(embedded, dict):
        return str(embedded.get("decision", "")).strip() or "HOLD"
    return "HOLD"


def build_security_review_remediation_handoff_prompt(
    *,
    source_report_text: str,
    source_report_path: Path | str,
    security_report: dict[str, Any],
    security_report_path: Path | str,
    release_gate: dict[str, Any],
    release_gate_path: Path | str,
    finding_records: list[dict[str, Any]],
    findings_dir: Path | str,
    evidence_records: list[dict[str, Any]],
    evidence_dir: Path | str,
    dashboard_projection_path: Path | str,
    output_report_path: Path | str,
    dream_studio_repo_path: Path | str,
    baseline_dream_studio: str = "Unknown; capture exact current Dream Studio branch/HEAD before planning.",
) -> str:
    """Build a complete remediation-planning handoff from Security Review artifacts.

    This generator is intentionally filesystem-passive. Callers load artifacts
    and provide their paths; the generator only renders prompt text.
    """
    recommendation = _security_next_recommendation(security_report)
    next_work_order_id = str(
        recommendation.get("recommended_work_order_id")
        or "wo-dream-studio-018s12-bill-stack-tier0-security-remediation-planning"
    )
    phase_name = str(
        recommendation.get("recommended_phase_name")
        or "Phase 18S.12 - Bill Stack Tier 0 Security Remediation Planning"
    )
    handoff_type = str(
        recommendation.get("recommended_handoff_type") or HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER
    )
    phase_type = str(
        recommendation.get("recommended_phase_type") or PHASE_TYPE_NORMAL_NEXT_WORK_ORDER
    )
    taxonomy = _as_list(recommendation.get("decision_taxonomy")) or list(
        DECISION_TAXONOMIES[PHASE_TYPE_NORMAL_NEXT_WORK_ORDER]
    )
    final_decision = str(recommendation.get("recommended_decision") or HOLD)
    target_id = str(security_report.get("target_id") or "target").strip()
    target_path = _extract_target_path_from_report(source_report_text, target_id)
    target_branch, target_head = _target_branch_head_from_evidence(evidence_records)
    untracked_entries = _target_untracked_entries(evidence_records)
    release_decision = _security_release_gate_decision(security_report, release_gate)
    finding_refs = _security_finding_refs(finding_records)
    finding_ids = _security_finding_ids(finding_records)

    lines = [
        "# Handoff Packet",
        "",
        _section("Phase Name", phase_name),
        _section("Handoff Type", handoff_type),
        _section("Phase Type", phase_type),
        _section("Required Decision Taxonomy", taxonomy),
        _section("Final Decision", final_decision),
        _section(
            "Decision Rationale",
            (
                f"Phase 18S.11 produced a SecurityReviewReport with release gate "
                f"{release_decision}, verdict {security_report.get('verdict', 'unknown')}, "
                f"{len(finding_ids)} finding records, and {len(evidence_records)} evidence records. "
                "This next phase is remediation planning only and starts at HOLD until the receiver "
                "confirms scope, constraints, and the file-backed security artifacts."
            ),
        ),
        _section(
            "Transition Rationale",
            "Security review found release-blocking risks; the next safe step is observe-only remediation planning from file-backed artifacts.",
        ),
        _section("Fresh-Session Rule", FRESH_SESSION_RULE),
        _section(
            "Source Work Order ID", str(security_report.get("source_work_order_id", "unavailable"))
        ),
        _section("Next Work Order ID", next_work_order_id),
        _section("Dream Studio Repo Path", str(dream_studio_repo_path)),
        _section("Target Repo Path", target_path),
        _section("Baseline Dream Studio Branch/HEAD", baseline_dream_studio),
        _section(
            "Baseline Target Repo Branch/HEAD",
            f"Branch: {target_branch}\nHEAD: {target_head}",
        ),
        _section(
            "Target Baseline Constraints",
            [
                f"Target branch is {target_branch}.",
                f"Target HEAD is {target_head}.",
                "Current branch differs from the original intake default branch main; carry this forward as a constraint.",
                *[
                    f"Preserve pre-existing untracked entry: {entry}."
                    for entry in untracked_entries
                ],
                "Do not inspect untracked entries unless separately approved.",
                "Do not write artifacts inside the target repository.",
            ],
        ),
        _section(
            "Objective",
            (
                "Plan bounded remediation for the Phase 18S.11 Bill Stack Tier 0 findings. "
                "Do not mutate Bill Stack in this planning phase; actual remediation must be opened "
                "as a later approved mutation Work Order."
            ),
        ),
        _section(
            "Capability Boundary",
            [
                "This Handoff Packet is not an execution command.",
                "This phase is remediation planning only.",
                "Do not touch Bill Stack unless a later Work Order explicitly approves target access.",
                "Do not run scans.",
                "Do not run target validation.",
                "Do not mutate target repositories.",
                "Do not read production secrets, real .env values, private keys, or credentials.",
                "Future remediation must be a separate approved mutation Work Order.",
                *CONSTRAINT_TERMS,
            ],
        ),
        _section("Approval Mode", "observe_only"),
        _section("Risk Level", "medium"),
        _section(
            "Scope Include",
            [
                f"Phase 18S.11 report: {_artifact_path_label(source_report_path)}",
                f"SecurityReviewReport: {_artifact_path_label(security_report_path)}",
                f"ReleaseGateSummary: {_artifact_path_label(release_gate_path)}",
                f"Finding records directory: {_artifact_path_label(findings_dir)}",
                f"Evidence records directory: {_artifact_path_label(evidence_dir)}",
                f"Dashboard projection input: {_artifact_path_label(dashboard_projection_path)}",
                "Handoff Packet Contract: docs/contracts/handoff-packet-contract.md",
                "Security Review Report Artifact Contract: docs/contracts/security-review-report-artifact-contract.md",
            ],
        ),
        _section(
            "Scope Exclude",
            [
                "Bill Stack source inspection",
                "Bill Stack mutation",
                "security remediation execution",
                "security scan execution",
                "target validation",
                "dependency updates",
                "lockfile updates",
                "schema migrations",
                "generated artifacts inside Bill Stack",
                "runtime, CLI, dashboard, profile registry, DB/event, Docker, TORII, cloud, org, global, or enterprise work",
            ],
        ),
        _section(
            "Approved Files If Mutation-Gated",
            [
                "not applicable for observe-only remediation planning",
                "no Bill Stack files are approved for mutation in this phase",
            ],
        ),
        _section(
            "Forbidden Files",
            [
                "Any Bill Stack file unless a later Work Order separately approves read-only access",
                "billstack-api/migrate_direct.py",
                "billstack-web/dev-dist/",
                "production secrets",
                ".env files with real values",
                "private keys",
                "credentials",
                "dependency manifests or lockfiles for mutation",
                "DB/event ledger files",
                "schema migration files",
                "Docker files",
                "dashboard implementation files",
                "TORII/cloud/org/global/enterprise files",
            ],
        ),
        _section(
            "Allowed Actions",
            [
                "produce the Handoff Understanding Report before action",
                "inspect the Phase 18S.11 report and file-backed security artifacts",
                "summarize remediation options for the six finding records",
                "recommend a bounded approved mutation Work Order for actual Bill Stack fixes",
                "write planning output only under Dream Studio meta/audit or Work Order storage",
                "run Dream Studio status checks only if needed for the planning report",
            ],
        ),
        _section(
            "Forbidden Actions",
            [
                "touch Bill Stack",
                "inspect Bill Stack source files without separate approval",
                "run scans",
                "run target validation",
                "mutate target repositories",
                "write artifacts inside Bill Stack",
                "read production secrets, real .env values, private keys, or credentials",
                "inspect untracked entries",
                "stage, commit, or push",
                "install dependencies",
                "update dependencies or lockfiles",
                "implement remediation",
                "add runtime, CLI, dashboard, profile registry, DB/event/schema/Docker/TORII/cloud/org/global/enterprise surfaces",
            ],
        ),
        _section(
            "Approval Artifact Requirement",
            (
                "Not applicable for observe-only remediation planning. Create a new file-backed approval "
                "artifact before any later Bill Stack mutation, scan execution, target validation, dependency "
                "change, lockfile update, or source inspection beyond referenced artifacts."
            ),
        ),
        _section(
            "Before/After Evidence Requirements",
            [
                "Before planning: capture Dream Studio branch, HEAD, and status.",
                "Before planning: confirm Phase 18S.11 SecurityReviewReport, ReleaseGateSummary, finding records, evidence records, and dashboard projection input exist.",
                "Before planning: confirm release gate remains REMEDIATE_BEFORE_RELEASE.",
                "During planning: cite file-backed findings and evidence only.",
                "After planning: confirm no Bill Stack access, mutation, scan, validation, dependency change, lockfile update, or target artifact write occurred.",
                "After planning: list any recommended future approved mutation Work Orders.",
            ],
        ),
        _section(
            "Validation Commands",
            [
                "No Bill Stack validation is approved.",
                "No security scans are approved.",
                "Run Dream Studio checks only if tracked Dream Studio files change.",
            ],
        ),
        _section(
            "Eval Requirements",
            [
                HANDOFF_PROMPT_COMPLETENESS,
                HANDOFF_CONSTRAINT_PRESERVATION,
                HANDOFF_EXECUTION_READINESS,
                HANDOFF_FRESH_SESSION_SUFFICIENCY,
                SECURITY_HANDOFF_FINDING_REFS_PRESENT,
                SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
                SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
                SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
                SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
                SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
                READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
                "forbidden_action_compliance",
                "target_repo_mutation",
                "result_report_completeness",
                "next_work_order_recommendation",
            ],
        ),
        _section("Report Path", str(output_report_path)),
        _section(
            "Output Artifacts",
            [
                f"Remediation planning report: {output_report_path}",
                "Bounded approved mutation Work Order recommendation, if remediation remains required.",
                "No target-repo files, scans, validation outputs, commits, pushes, or runtime mutations.",
            ],
        ),
        _section(
            "Readiness Rules",
            [
                "Proceed only after producing the Handoff Understanding Report.",
                "Proceed only if Phase 18S.12 remains remediation planning only.",
                "Proceed only from file-backed Phase 18S.11 report, finding, evidence, release-gate, and dashboard artifacts.",
                "HOLD if Bill Stack access is required.",
                "HOLD if remediation implementation is required.",
                "HOLD if scans or target validation are required.",
                "FAIL if any forbidden action occurs.",
            ],
        ),
        _section(
            "Expected Verdict",
            [
                "PASS if a bounded remediation plan and next approved mutation Work Order recommendation are produced without forbidden action.",
                "PASS WITH RISKS if planning succeeds but unresolved security risks remain, including the RevenueCat finding.",
                "HOLD if target access, scan execution, validation, or mutation is required before planning can continue.",
                "FAIL if Bill Stack, scans, validation, runtime authority, dashboard authority, or forbidden surfaces are mutated.",
            ],
        ),
        _section(
            "Release-Gate Decision Rules",
            [
                f"Current release gate is {release_decision}.",
                "Release gate remains REMEDIATE_BEFORE_RELEASE until the high-severity RevenueCat finding is remediated or risk-accepted through a file-backed operator decision.",
                "SECURITY_CLEAR is forbidden in Phase 18S.12 because remediation has not occurred.",
                "ACCEPT_RISK_WITH_APPROVAL requires a file-backed operator decision artifact.",
                "Any actual fix must be proposed as a separate approved mutation Work Order.",
            ],
        ),
        _section(
            "Stop Conditions",
            [
                "Handoff Understanding Report is missing.",
                "Bill Stack access is requested.",
                "Bill Stack source inspection is requested without separate approval.",
                "Scan execution is requested.",
                "Target validation is requested.",
                "Target mutation is requested.",
                "Production secrets, real .env values, private keys, or credentials are needed.",
                "Untracked entries must be inspected.",
                "Dependency or lockfile changes are requested.",
                "Runtime/dashboard/DB/event/schema/Docker/TORII/cloud/org/global/enterprise expansion appears.",
                "Validation fails and the failure is not understood.",
            ],
        ),
        _section(
            "Final Response Must Include",
            [
                "final response summarizes reviewed artifacts, findings, release-gate status, and recommended next Work Order",
                "final response confirms no Bill Stack access, mutation, scan, validation, dependency change, or push occurred",
                "final response states whether release remains blocked",
            ],
        ),
        _section(
            "Next Handoff Requirements",
            [
                "next handoff must include required first action, approval artifact requirement, allowed commands, forbidden commands, output artifacts, readiness rules, stop conditions, final response, and next handoff sections",
                "next handoff must preserve finding IDs, release gate, target branch/head, and untracked-entry constraints",
            ],
        ),
        _section(
            "Phase-Specific Safety Constraints",
            [
                "required first action is a Handoff Understanding Report",
                "approval artifact is required before any future mutation, scan, target validation, dependency change, or source inspection beyond referenced artifacts",
                "allowed commands are limited to file-backed artifact review unless separately approved",
                "forbidden commands include target validation, scans, package managers, git stage, git commit, git push, Docker, and deploy",
                "output artifacts must stay under Dream Studio meta/audit or Work Order storage",
            ],
        ),
        _section(
            "Handoff Understanding Report Requirement",
            [
                "Before taking action, produce a Handoff Understanding Report.",
                *UNDERSTANDING_REQUIRED_TERMS,
            ],
        ),
        _section(
            "First Safe Action",
            (
                "Read the Phase 18S.11 report, SecurityReviewReport, ReleaseGateSummary, finding "
                "records, and evidence records, then produce the Handoff Understanding Report before "
                "any remediation planning."
            ),
        ),
        _section("Security Finding References", finding_refs),
    ]
    return "\n".join(lines).replace("\n\n\n", "\n\n").strip() + "\n"


def _finding_matches(finding: dict[str, Any], wanted: set[str]) -> bool:
    finding_id = str(finding.get("finding_id", "")).strip()
    return finding_id in wanted or _finding_short_id(finding_id) in wanted


def _selected_security_findings(
    finding_records: list[dict[str, Any]],
    included_finding_ids: list[str] | None,
) -> list[dict[str, Any]]:
    wanted = {item.strip() for item in included_finding_ids or [] if item.strip()}
    if not wanted:
        return finding_records
    return [finding for finding in finding_records if _finding_matches(finding, wanted)]


def _finding_assets(finding_records: list[dict[str, Any]]) -> list[str]:
    assets: list[str] = []
    for finding in finding_records:
        for asset in _as_list(finding.get("affected_assets")):
            text = str(asset).strip()
            if text and text not in assets:
                assets.append(text)
    return assets


def _finding_titles(finding_records: list[dict[str, Any]]) -> list[str]:
    titles: list[str] = []
    for finding in finding_records:
        finding_id = str(finding.get("finding_id", "")).strip()
        title = str(finding.get("title", "")).strip()
        label = _finding_short_id(finding_id)
        if title:
            titles.append(f"{label}: {title}")
        elif label:
            titles.append(label)
    return titles or ["unavailable"]


def build_security_remediation_mutation_handoff_prompt(
    *,
    planning_report_text: str,
    planning_report_path: Path | str,
    security_report: dict[str, Any],
    security_report_path: Path | str,
    release_gate: dict[str, Any],
    release_gate_path: Path | str,
    finding_records: list[dict[str, Any]],
    findings_dir: Path | str,
    evidence_records: list[dict[str, Any]],
    evidence_dir: Path | str,
    output_report_path: Path | str,
    dream_studio_repo_path: Path | str,
    baseline_dream_studio: str = "Unknown; capture exact current Dream Studio branch/HEAD before mutation.",
    included_finding_ids: list[str] | None = None,
) -> str:
    """Build a mutation-only security remediation handoff from planning artifacts."""
    target_id = str(security_report.get("target_id") or "target").strip()
    target_path = _extract_target_path_from_report(planning_report_text, target_id)
    target_branch, target_head = _target_branch_head_from_evidence(evidence_records)
    untracked_entries = _target_untracked_entries(evidence_records)
    release_decision = _security_release_gate_decision(security_report, release_gate)
    all_finding_refs = _security_finding_refs(finding_records)
    selected_findings = _selected_security_findings(finding_records, included_finding_ids)
    selected_refs = _security_finding_refs(selected_findings)
    selected_assets = _finding_assets(selected_findings)
    selected_titles = _finding_titles(selected_findings)
    phase_name = "Phase 18S.13 - Bill Stack Tier 0 Priority Security Remediation"
    next_work_order_id = "wo-dream-studio-018s13-bill-stack-tier0-priority-security-remediation"

    lines = [
        "# Handoff Packet",
        "",
        _section("Phase Name", phase_name),
        _section("Handoff Type", HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION),
        _section("Phase Type", PHASE_TYPE_APPROVED_MUTATION),
        _section(
            "Required Decision Taxonomy", list(DECISION_TAXONOMIES[PHASE_TYPE_APPROVED_MUTATION])
        ),
        _section("Final Decision", HOLD),
        _section(
            "Decision Rationale",
            (
                "Phase 18S.12 completed observe-only remediation planning from Phase 18S.11 "
                "file-backed Security Review artifacts. The receiving phase must perform only a "
                "bounded approved mutation for the priority Bill Stack findings, must not stage, "
                "commit, or push, and must defer commit planning to a later Work Order."
            ),
        ),
        _section(
            "Transition Rationale",
            "Remediation planning selected a bounded approved mutation slice; commit and push remain separate later phases.",
        ),
        _section("Fresh-Session Rule", FRESH_SESSION_RULE),
        _section(
            "Source Work Order ID", "wo-dream-studio-018s12-bill-stack-tier0-remediation-planning"
        ),
        _section("Next Work Order ID", next_work_order_id),
        _section("Dream Studio Repo Path", str(dream_studio_repo_path)),
        _section("Target Repo Path", target_path),
        _section("Baseline Dream Studio Branch/HEAD", baseline_dream_studio),
        _section(
            "Baseline Target Repo Branch/HEAD",
            f"Branch: {target_branch}\nHEAD: {target_head}",
        ),
        _section(
            "Target Baseline Constraints",
            [
                f"Target branch is {target_branch}.",
                f"Target HEAD is {target_head}.",
                "Current branch differs from the original intake default branch main; carry this forward as a constraint.",
                *[
                    f"Preserve pre-existing untracked entry: {entry}."
                    for entry in untracked_entries
                ],
                "Do not inspect untracked entries unless separately approved.",
                "Do not write generated artifacts inside Bill Stack.",
                "Do not stage, commit, or push.",
                "Commit planning must occur in a later separate Work Order after mutation evidence exists.",
            ],
        ),
        _section(
            "Objective",
            (
                "Implement a bounded Bill Stack security remediation slice for file-backed Phase 18S.11 "
                "findings: require RevenueCat webhook authentication before premium entitlement mutation, "
                "remove or split general household invite-code exposure, and enforce server-side password "
                "policy for registration/reset. Leave other findings for later Work Orders."
            ),
        ),
        _section(
            "Capability Boundary",
            [
                "This Handoff Packet is not an execution command.",
                "This is an approved mutation Work Order for a narrow Bill Stack security remediation slice.",
                "Do not stage, commit, or push.",
                "Commit planning must occur in a later separate Work Order after mutation evidence exists.",
                "Do not run scans.",
                "Do not run target validation unless a focused command is explicitly selected and documented after approved test-surface inspection.",
                "Do not mutate unapproved files.",
                "Do not inspect untracked entries.",
                "Do not read production secrets, real .env values, private keys, or credentials.",
                "Do not update dependencies or lockfiles.",
                "Do not add schema migrations.",
                "Do not implement browser token/session architecture changes.",
                "Do not implement durable auth-state storage.",
                *CONSTRAINT_TERMS,
            ],
        ),
        _section("Approval Mode", "approval_required"),
        _section("Risk Level", "medium"),
        _section(
            "Scope Include",
            [
                f"Phase 18S.12 remediation planning report: {_artifact_path_label(planning_report_path)}",
                f"SecurityReviewReport: {_artifact_path_label(security_report_path)}",
                f"ReleaseGateSummary: {_artifact_path_label(release_gate_path)}",
                f"Finding records directory: {_artifact_path_label(findings_dir)}",
                f"Evidence records directory: {_artifact_path_label(evidence_dir)}",
                "Priority finding: revenuecat_webhook_unsigned",
                "Secondary candidate finding: household_invite_code_exposure",
                "Secondary candidate finding: server_password_policy_gap",
                *[f"Selected finding: {item}" for item in selected_titles],
                *[
                    f"Candidate approved target file from finding evidence: {asset}"
                    for asset in selected_assets
                ],
            ],
        ),
        _section(
            "Scope Exclude",
            [
                "browser token/localStorage/SSE session architecture changes",
                "durable reset/verification/revocation state implementation",
                "dependency updates",
                "lockfile updates",
                "schema migrations",
                "security scans",
                "broad target validation",
                "untracked entries",
                "production secrets, real .env values, private keys, credentials",
                "runtime dashboard/API work",
                "DB/event/schema/Docker/TORII/cloud/org/global/enterprise work",
                "stage, commit, and push",
            ],
        ),
        _section(
            "Approved Files If Mutation-Gated",
            [
                "billstack-api/app/routers/purchases.py",
                "billstack-api/app/routers/household.py",
                "billstack-api/app/schemas/schemas.py",
                "billstack-api/app/routers/auth.py",
                "narrowly scoped Bill Stack test files needed for the approved fixes",
                "non-secret example environment file only if required for a RevenueCat verification placeholder",
                "Dream Studio meta/audit report for this phase",
                "Dream Studio Work Order approval/evidence artifacts for this phase",
            ],
        ),
        _section(
            "Forbidden Files",
            [
                "billstack-api/migrate_direct.py",
                "billstack-web/dev-dist/",
                "production secrets",
                "real .env values",
                "private keys",
                "credentials",
                "dependency manifests or lockfiles for mutation",
                "schema migration files",
                "runtime dashboard implementation files",
                "DB/event ledger files",
                "Docker files",
                "TORII/cloud/org/global/enterprise files",
                "unrelated Bill Stack files",
                "unrelated Dream Studio files",
            ],
        ),
        _section(
            "Allowed Actions",
            [
                "Produce Handoff Understanding Report before mutation.",
                "Create file-backed approval artifact before Bill Stack source inspection or mutation.",
                "Capture Dream Studio branch, HEAD, and status.",
                "Capture Bill Stack branch, HEAD, and status.",
                "Confirm target branch/head and pre-existing untracked entries.",
                "Inspect only approved finding/evidence artifacts.",
                "Inspect approved Bill Stack files only after approval artifact exists.",
                "Implement the bounded RevenueCat webhook authentication fix if source evidence confirms the finding.",
                "Implement household invite-code response boundary fix if source evidence confirms the finding.",
                "Implement server-side password policy enforcement if source evidence confirms the finding.",
                "Add or update narrowly scoped tests for these fixes.",
                "Run only explicitly selected focused validation commands after inspecting the target test surface.",
                "Run git diff/status checks.",
                "Write the phase report under Dream Studio meta/audit.",
            ],
        ),
        _section(
            "Forbidden Actions",
            [
                "Do not stage, commit, or push.",
                "Do not inspect untracked entries.",
                "Do not run scans.",
                "Do not run target validation before selecting and documenting the exact focused command.",
                "Do not read production secrets, real .env values, private keys, or credentials.",
                "Do not update dependencies or lockfiles.",
                "Do not add schema migrations.",
                "Do not implement browser token/session architecture changes.",
                "Do not implement durable reset/verification/revocation storage.",
                "Do not add DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise surfaces.",
                "Do not write generated artifacts inside Bill Stack.",
                "Do not mutate unrelated files.",
                "Do not claim release gate clearance without follow-up evidence or file-backed operator decision.",
            ],
        ),
        _section(
            "Approval Artifact Requirement",
            (
                "Before inspecting or mutating Bill Stack source, create a file-backed approval artifact under "
                "Dream Studio Work Order storage for Phase 18S.13. The approval scope must be limited to the "
                "approved Bill Stack source/test files and Dream Studio evidence/report artifacts. It must "
                "explicitly forbid scans, target validation until named, dependency changes, lockfile changes, "
                "secrets, untracked entry inspection, schema migrations, browser session architecture changes, "
                "durable auth-state storage, dashboard/runtime/DB/event/Docker/TORII/cloud/org/global/enterprise "
                "expansion, stage, commit, push, and unrelated mutation."
            ),
        ),
        _section(
            "Before/After Evidence Requirements",
            [
                "Before mutation: capture Dream Studio branch, HEAD, and status.",
                "Before mutation: capture Bill Stack branch, HEAD, and status.",
                f"Before mutation: confirm Bill Stack branch is {target_branch} or record drift.",
                f"Before mutation: confirm Bill Stack HEAD is {target_head} or record drift.",
                "Before mutation: confirm pre-existing untracked entries are preserved.",
                "Before mutation: confirm approval artifact exists before Bill Stack source inspection or mutation.",
                f"Before mutation: confirm release gate is {release_decision}.",
                "During mutation: record every Bill Stack file inspected.",
                "During mutation: record every Bill Stack file changed.",
                "During mutation: keep the mutation limited to the three included findings.",
                "During mutation: HOLD if implementation requires secrets, dependency changes, lockfile changes, schema migrations, browser session architecture, durable auth-state storage, scans, or untracked entry inspection.",
                "After mutation: capture Bill Stack branch, HEAD, status, and diff summary.",
                "After mutation: capture Dream Studio branch, HEAD, and status.",
                "After mutation: list changed files.",
                "After mutation: confirm pre-existing untracked entries remain uninspected and preserved.",
                "After mutation: confirm no stage, commit, or push occurred.",
                "After mutation: confirm no scans were run unless separately approved.",
                "After mutation: confirm no dependency or lockfile changes occurred.",
                "After mutation: confirm no schema migrations occurred.",
                "After mutation: confirm no target artifacts were written outside approved tracked changes.",
                f"After mutation: confirm release gate remains {release_decision} pending follow-up review or operator decision.",
            ],
        ),
        _section(
            "Validation Commands",
            [
                "No scans are approved by default.",
                "No broad target validation is approved by default.",
                "After approved test-surface inspection, select the narrowest existing test commands for changed backend files.",
                "HOLD if no safe focused command can be identified without package installation, dependency changes, broad target execution, staging, or committing.",
                "Run git status --short in Dream Studio.",
                f'Run git -C "{target_path}" status --short --branch.',
                "Run git diff --check for changed repositories before reporting completion.",
            ],
        ),
        _section(
            "Eval Requirements",
            [
                HANDOFF_PROMPT_COMPLETENESS,
                HANDOFF_CONSTRAINT_PRESERVATION,
                HANDOFF_EXECUTION_READINESS,
                HANDOFF_FRESH_SESSION_SUFFICIENCY,
                SECURITY_HANDOFF_FINDING_REFS_PRESENT,
                SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
                SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
                SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
                SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
                SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
                SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
                READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
                "forbidden_action_compliance",
                "target_repo_mutation",
                "approved_mutation_compliance",
                "result_report_completeness",
                "next_work_order_recommendation",
            ],
        ),
        _section("Report Path", str(output_report_path)),
        _section(
            "Output Artifacts",
            [
                f"Mutation evidence/report: {output_report_path}",
                "Changed-file evidence limited to approved files.",
                "Focused validation evidence if a safe command is identified.",
                "No stage, commit, push, cleanup, scans, dependency changes, or runtime authority changes.",
            ],
        ),
        _section(
            "Readiness Rules",
            [
                "Proceed only after Handoff Understanding Report.",
                "Proceed only after approval artifact exists.",
                "Proceed only if Bill Stack branch/head/status can be captured.",
                "Proceed only if mutation remains limited to the approved files/findings.",
                "Proceed only if staging, committing, and pushing remain forbidden.",
                "HOLD if target branch/head drift makes the baseline unclear.",
                "HOLD if secrets, scans, broad validation, dependency changes, lockfile changes, migrations, untracked entries, or broader architecture work are required.",
                "HOLD if commit planning is requested inside this mutation Work Order.",
                "FAIL if any forbidden action occurs.",
            ],
        ),
        _section(
            "Expected Verdict",
            [
                "MUTATION_COMPLETE if the three scoped remediations are implemented, focused validation passes, evidence is recorded, no stage/commit/push occurs, and no forbidden action occurs.",
                "NEEDS_REMEDIATION if some scoped findings remain open but no forbidden action occurs.",
                "HOLD if target drift, missing approval, secrets, broader architecture, scans, dependency changes, migrations, unsafe validation, staging, committing, or pushing block completion.",
                "FAIL if any forbidden action occurs.",
            ],
        ),
        _section(
            "Release-Gate Decision Rules",
            [
                f"Current release gate is {release_decision}.",
                "The release gate remains REMEDIATE_BEFORE_RELEASE until the high-severity RevenueCat finding is remediated and verified, or risk-accepted through a file-backed operator decision.",
                "This mutation Work Order may produce remediation evidence, but it must not declare final security clearance by itself.",
                "A follow-up observe-only review, release-gate review, or operator decision is required before any release-gate upgrade.",
            ],
        ),
        _section(
            "Stop Conditions",
            [
                "Handoff Understanding Report is missing.",
                "Approval artifact is missing before Bill Stack source inspection or mutation.",
                "Bill Stack branch/HEAD/status cannot be captured.",
                "Target branch/head drift is not understood.",
                "Untracked entries must be inspected.",
                "Secrets, real .env values, private keys, or credentials are needed.",
                "Scans are requested.",
                "Dependency or lockfile changes are requested.",
                "Schema migrations are required.",
                "Browser token/session architecture changes are required.",
                "Durable auth-state storage is required.",
                "Stage, commit, or push is requested.",
                "Commit planning is requested inside this mutation Work Order.",
                "Dashboard/runtime/DB/event/Docker/TORII/cloud/org/global/enterprise expansion appears.",
                "Validation fails and the failure is not understood.",
            ],
        ),
        _section(
            "Final Response Must Include",
            [
                "final response lists files inspected, files changed, focused validation, and unresolved findings",
                "final response confirms no stage, commit, push, scan, dependency change, lockfile change, or schema migration occurred",
                "final response recommends the next handoff, normally post-remediation review or commit planning only after review accepts the mutation evidence",
            ],
        ),
        _section(
            "Next Handoff Requirements",
            [
                "next handoff must include required first action, approval artifact, allowed commands, forbidden commands, output artifacts, readiness rules, stop conditions, final response, and next handoff sections",
                "next handoff must preserve release gate, changed-file evidence, validation evidence, and stage/commit/push prohibition until an explicit commit phase",
            ],
        ),
        _section(
            "Phase-Specific Safety Constraints",
            [
                "required first action is a Handoff Understanding Report",
                "approval artifact is required before source inspection or mutation",
                "allowed commands are limited to exact focused validation selected after approved test-surface inspection",
                "forbidden commands include scans, package managers, git stage, git commit, git push, Docker, deploy, and broad validation",
                "output artifacts must stay under Dream Studio meta/audit or Work Order storage",
            ],
        ),
        _section(
            "Handoff Understanding Report Requirement",
            [
                "Before taking action, produce a Handoff Understanding Report with:",
                *UNDERSTANDING_REQUIRED_TERMS,
            ],
        ),
        _section(
            "First Safe Action",
            (
                "Read the Phase 18S.12 remediation planning report, Phase 18S.11 SecurityReviewReport, "
                "ReleaseGateSummary, and the three included finding/evidence records, then produce the "
                "Handoff Understanding Report before creating the approval artifact."
            ),
        ),
        _section("Security Finding References", all_finding_refs),
        _section("Included Remediation Findings", selected_refs),
        _section(
            "Deferred Security Findings",
            [
                "browser_token_exposure_window remains deferred to a later session/auth architecture Work Order.",
                "in_memory_auth_state remains deferred to a later durable auth-state Work Order.",
                "dependency_reproducibility_gap remains deferred to a later dependency review and reproducibility Work Order.",
            ],
        ),
    ]
    return "\n".join(lines).replace("\n\n\n", "\n\n").strip() + "\n"


def _mutation_validation_lines(mutation_evidence: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in _as_list(mutation_evidence.get("focused_validation")):
        if not isinstance(item, dict):
            continue
        command = str(item.get("command", "")).strip()
        result = str(item.get("result", "")).strip()
        if command and result:
            lines.append(f"{command} -> {result}")
    return lines or ["unavailable"]


def build_security_post_remediation_review_handoff_prompt(
    *,
    mutation_report_text: str,
    mutation_report_path: Path | str,
    mutation_evidence: dict[str, Any],
    mutation_evidence_path: Path | str,
    paused_work_path: Path | str,
    security_report: dict[str, Any],
    security_report_path: Path | str,
    release_gate: dict[str, Any],
    release_gate_path: Path | str,
    finding_records: list[dict[str, Any]],
    findings_dir: Path | str,
    output_report_path: Path | str,
    dream_studio_repo_path: Path | str,
    baseline_dream_studio: str = "Unknown; capture exact current Dream Studio branch/HEAD before review.",
) -> str:
    """Build an observe-only post-remediation review handoff from mutation artifacts."""
    target_id = str(
        mutation_evidence.get("target_id") or security_report.get("target_id") or "target"
    )
    target_path = str(
        mutation_evidence.get("target_path") or ""
    ).strip() or _extract_target_path_from_report(
        mutation_report_text,
        target_id,
    )
    target_branch = str(mutation_evidence.get("target_branch") or "unknown").strip()
    target_head = str(mutation_evidence.get("target_head") or "unknown").strip()
    changed_files = [str(item) for item in _as_list(mutation_evidence.get("files_changed"))]
    preserved_untracked = [
        str(item) for item in _as_list(mutation_evidence.get("preserved_untracked_entries"))
    ]
    included_ids = [str(item) for item in _as_list(mutation_evidence.get("included_findings"))]
    selected_findings = _selected_security_findings(finding_records, included_ids)
    selected_refs = _security_finding_refs(selected_findings)
    all_finding_refs = _security_finding_refs(finding_records)
    release_decision = str(
        mutation_evidence.get("release_gate_after") or ""
    ).strip() or _security_release_gate_decision(security_report, release_gate)
    validation_lines = _mutation_validation_lines(mutation_evidence)
    phase_name = "Phase 18S.14 - Bill Stack Post-Remediation Security Review"
    next_work_order_id = "wo-dream-studio-018s14-bill-stack-post-remediation-security-review"

    lines = [
        "# Handoff Packet",
        "",
        _section("Phase Name", phase_name),
        _section("Handoff Type", HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER),
        _section("Phase Type", PHASE_TYPE_NORMAL_NEXT_WORK_ORDER),
        _section(
            "Required Decision Taxonomy",
            list(DECISION_TAXONOMIES[PHASE_TYPE_NORMAL_NEXT_WORK_ORDER]),
        ),
        _section("Final Decision", HOLD),
        _section(
            "Decision Rationale",
            (
                "Phase 18S.13 completed a bounded approved mutation for the priority Bill Stack "
                "Tier 0 security findings. This next phase is an observe-only post-remediation "
                "security review that must verify the file-backed mutation evidence before any "
                "release-gate or commit-planning recommendation changes."
            ),
        ),
        _section(
            "Transition Rationale",
            "A bounded mutation produced evidence; the next safe step is observe-only review before any commit planning or release-gate upgrade.",
        ),
        _section("Fresh-Session Rule", FRESH_SESSION_RULE),
        _section(
            "Source Work Order ID", str(mutation_evidence.get("work_order_id", "unavailable"))
        ),
        _section("Next Work Order ID", next_work_order_id),
        _section("Dream Studio Repo Path", str(dream_studio_repo_path)),
        _section("Target Repo Path", target_path),
        _section("Baseline Dream Studio Branch/HEAD", baseline_dream_studio),
        _section(
            "Baseline Target Repo Branch/HEAD",
            f"Branch: {target_branch}\nHEAD: {target_head}",
        ),
        _section(
            "Target Baseline Constraints",
            [
                f"Target branch is {target_branch}.",
                f"Target HEAD before the Phase 18S.13 mutation slice was {target_head}.",
                "Current branch differs from the original intake default branch main; carry this forward as a constraint.",
                *[
                    f"Preserve pre-existing untracked entry: {entry}."
                    for entry in preserved_untracked
                ],
                "Do not inspect untracked entries unless separately approved.",
                "Do not stage, commit, or push.",
                "Commit planning must remain a later separate Work Order after post-remediation review evidence exists.",
            ],
        ),
        _section(
            "Objective",
            (
                "Perform an observe-only post-remediation security review of the three Phase 18S.13 "
                "remediated findings. Determine whether each finding can be marked remediated from "
                "file-backed evidence, and recommend whether the release gate remains "
                "REMEDIATE_BEFORE_RELEASE, moves to RUN_ADDITIONAL_SECURITY_REVIEW, or requires "
                "follow-up commit planning."
            ),
        ),
        _section(
            "Capability Boundary",
            [
                "This Handoff Packet is not an execution command.",
                "This phase is observe-only post-remediation security review.",
                "Do not mutate Bill Stack.",
                "Do not mutate target repositories.",
                "Do not stage, commit, or push.",
                "Do not run scans unless a later Work Order separately approves them.",
                "Do not run broad target validation.",
                "Do not read production secrets, real .env values, private keys, or credentials.",
                "Do not inspect untracked entries unless separately approved.",
                "Commit planning must remain a later separate Work Order.",
                *CONSTRAINT_TERMS,
            ],
        ),
        _section("Approval Mode", "approval_required"),
        _section("Risk Level", "medium"),
        _section(
            "Scope Include",
            [
                f"Phase 18S.13 report: {_artifact_path_label(mutation_report_path)}",
                f"Phase 18S.13 mutation evidence: {_artifact_path_label(mutation_evidence_path)}",
                f"PausedWork continuity artifact: {_artifact_path_label(paused_work_path)}",
                f"SecurityReviewReport: {_artifact_path_label(security_report_path)}",
                f"ReleaseGateSummary: {_artifact_path_label(release_gate_path)}",
                f"Finding records directory: {_artifact_path_label(findings_dir)}",
                *[
                    f"Phase 18S.13 changed file for read-only review: {item}"
                    for item in changed_files
                ],
                *[f"Phase 18S.13 focused validation result: {item}" for item in validation_lines],
            ],
        ),
        _section(
            "Scope Exclude",
            [
                "Bill Stack mutation",
                "security remediation execution",
                "security scan execution unless separately approved",
                "broad target validation",
                "dependency updates",
                "lockfile updates",
                "schema migrations",
                "generated artifacts inside Bill Stack",
                "stage, commit, and push",
                "commit planning execution",
                "runtime, CLI, dashboard, profile registry, DB/event, Docker, TORII, cloud, org, global, or enterprise work",
            ],
        ),
        _section(
            "Approved Files If Mutation-Gated",
            [
                "observe-only post-remediation review approves no Bill Stack mutation",
                "no Bill Stack files are approved for mutation in this phase",
                "read-only Bill Stack inspection, if needed, is limited to Phase 18S.13 changed files after a file-backed approval artifact exists",
            ],
        ),
        _section(
            "Forbidden Files",
            [
                "Bill Stack files outside the Phase 18S.13 changed-file review set unless separately approved",
                "billstack-api/migrate_direct.py",
                "billstack-web/dev-dist/",
                "production secrets",
                "real .env values",
                "private keys",
                "credentials",
                "dependency manifests or lockfiles for mutation",
                "schema migration files",
                "runtime dashboard implementation files",
                "DB/event ledger files",
                "Docker files",
                "TORII/cloud/org/global/enterprise files",
                "unrelated Bill Stack files",
                "unrelated Dream Studio files",
            ],
        ),
        _section(
            "Allowed Actions",
            [
                "Produce Handoff Understanding Report before action.",
                "Create a file-backed approval artifact before any Bill Stack read-only inspection.",
                "Inspect Phase 18S.13 report and mutation evidence.",
                "Inspect Phase 18S.11 SecurityReviewReport, ReleaseGateSummary, and included finding records.",
                "Inspect Phase 18S.13 changed files read-only only after approval artifact exists.",
                "Determine whether the three included findings can be marked remediated from evidence.",
                "Recommend whether release gate remains REMEDIATE_BEFORE_RELEASE, moves to RUN_ADDITIONAL_SECURITY_REVIEW, or requires follow-up commit planning.",
                "Write review output only under Dream Studio meta/audit or Work Order storage.",
                "Run Dream Studio status checks.",
            ],
        ),
        _section(
            "Forbidden Actions",
            [
                "Do not mutate Bill Stack.",
                "Do not mutate target repositories.",
                "Do not stage, commit, or push.",
                "Do not run scans unless separately approved.",
                "Do not run broad target validation.",
                "Do not read production secrets, real .env values, private keys, or credentials.",
                "Do not inspect untracked entries unless separately approved.",
                "Do not update dependencies or lockfiles.",
                "Do not add schema migrations.",
                "Do not implement remediation.",
                "Do not perform commit planning inside this review Work Order.",
                "Do not add DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise surfaces.",
            ],
        ),
        _section(
            "Approval Artifact Requirement",
            (
                "Before any Bill Stack read-only inspection, create a file-backed approval artifact under "
                "Dream Studio Work Order storage for Phase 18S.14. The approval scope must be limited to "
                "observe-only review of Phase 18S.13 artifacts and, if needed, read-only inspection of "
                "the Phase 18S.13 changed files. It must explicitly forbid mutation, scans unless "
                "separately approved, broad validation, dependency changes, lockfile changes, secrets, "
                "untracked-entry inspection, stage, commit, push, dashboard/runtime/DB/event/Docker/"
                "TORII/cloud/org/global/enterprise expansion, and commit planning execution."
            ),
        ),
        _section(
            "Before/After Evidence Requirements",
            [
                "Before review: capture Dream Studio branch, HEAD, and status.",
                "Before review: confirm Phase 18S.13 report and mutation evidence exist.",
                "Before review: confirm paused_work.yaml records Phase 18S.13 as completed or resolved.",
                f"Before review: confirm release gate remains {release_decision}.",
                "Before any Bill Stack read-only inspection: confirm approval artifact exists.",
                "During review: cite Phase 18S.13 changed files and validation evidence.",
                "During review: do not claim findings remediated without file-backed evidence.",
                "After review: record finding status recommendations for the three included findings.",
                "After review: record release-gate recommendation.",
                "After review: confirm no target mutation, scans, broad validation, stage, commit, or push occurred.",
                "After review: list any recommended follow-up Work Orders, including commit planning if appropriate.",
            ],
        ),
        _section(
            "Validation Commands",
            [
                "No scans are approved by default.",
                "No broad target validation is approved.",
                "No target mutation, stage, commit, or push is approved.",
                "Run Dream Studio status checks.",
                "Run only explicitly scoped read-only checks named by the Phase 18S.14 reviewer after approval artifact exists.",
            ],
        ),
        _section(
            "Eval Requirements",
            [
                HANDOFF_PROMPT_COMPLETENESS,
                HANDOFF_CONSTRAINT_PRESERVATION,
                HANDOFF_EXECUTION_READINESS,
                HANDOFF_FRESH_SESSION_SUFFICIENCY,
                SECURITY_HANDOFF_FINDING_REFS_PRESENT,
                SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
                SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
                SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
                SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
                SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
                SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
                READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
                "post_remediation_changed_files_preserved",
                "post_remediation_validation_results_preserved",
                "forbidden_action_compliance",
                "target_repo_mutation",
                "result_report_completeness",
                "next_work_order_recommendation",
            ],
        ),
        _section("Report Path", str(output_report_path)),
        _section(
            "Output Artifacts",
            [
                f"Post-remediation review report: {output_report_path}",
                "Finding status recommendations for reviewed remediation items.",
                "Release-gate recommendation with evidence references.",
                "No target mutation, scan execution, broad validation, stage, commit, push, or cleanup.",
            ],
        ),
        _section(
            "Readiness Rules",
            [
                "Proceed only after Handoff Understanding Report.",
                "Proceed only after approval artifact exists before any Bill Stack read-only inspection.",
                "Proceed only if Phase 18S.14 remains observe-only post-remediation review.",
                "Proceed only from file-backed Phase 18S.13 report and mutation evidence.",
                "HOLD if Bill Stack mutation is required.",
                "HOLD if scans or broad validation are required.",
                "HOLD if commit planning or commit execution is requested inside this review Work Order.",
                "FAIL if any forbidden action occurs.",
            ],
        ),
        _section(
            "Expected Verdict",
            [
                "PASS if post-remediation review artifacts are produced, the three finding status recommendations are evidence-backed, release-gate recommendation is bounded, and no forbidden action occurs.",
                "PASS WITH RISKS if review completes but evidence remains incomplete or release gate cannot be upgraded.",
                "HOLD if mutation, scans, broad validation, commit planning, or forbidden target access is required.",
                "FAIL if target mutation, scans without approval, broad validation, stage, commit, push, runtime authority, dashboard authority, or forbidden surfaces are mutated.",
            ],
        ),
        _section(
            "Release-Gate Decision Rules",
            [
                f"Current release gate is {release_decision}.",
                "Decide whether the release gate remains REMEDIATE_BEFORE_RELEASE.",
                "Decide whether the release gate should move to RUN_ADDITIONAL_SECURITY_REVIEW.",
                "Decide whether follow-up commit planning is required before any release-gate upgrade.",
                "SECURITY_CLEAR is not available from this review unless all blocking findings and required approval/evidence gaps are resolved by file-backed evidence.",
                "Commit planning must remain a later separate Work Order.",
            ],
        ),
        _section(
            "Stop Conditions",
            [
                "Handoff Understanding Report is missing.",
                "Approval artifact is missing before Bill Stack read-only inspection.",
                "Bill Stack mutation is requested.",
                "Scan execution is requested without separate approval.",
                "Broad target validation is requested.",
                "Stage, commit, or push is requested.",
                "Commit planning is requested inside this review Work Order.",
                "Production secrets, real .env values, private keys, or credentials are needed.",
                "Untracked entries must be inspected.",
                "Dependency or lockfile changes are requested.",
                "Schema migrations are required.",
                "Dashboard/runtime/DB/event/Docker/TORII/cloud/org/global/enterprise expansion appears.",
                "Validation fails and the failure is not understood.",
            ],
        ),
        _section(
            "Final Response Must Include",
            [
                "final response summarizes reviewed mutation evidence, changed files, finding status recommendations, and release-gate recommendation",
                "final response confirms no mutation, scan, broad validation, stage, commit, push, dependency change, or schema migration occurred",
                "final response states the next handoff, usually commit planning only if review accepts the remediation evidence",
            ],
        ),
        _section(
            "Next Handoff Requirements",
            [
                "next handoff must include required first action, approval artifact, allowed commands, forbidden commands, output artifacts, readiness rules, stop conditions, final response, and next handoff sections",
                "next handoff must preserve mutation evidence, release gate, changed-file list, and explicit cleanup/deletion/archive prohibition unless separately approved",
            ],
        ),
        _section(
            "Phase-Specific Safety Constraints",
            [
                "required first action is a Handoff Understanding Report",
                "approval artifact is required before any Bill Stack read-only inspection",
                "allowed commands are limited to read-only artifact review and explicitly scoped status checks",
                "forbidden commands include scans, broad validation, package managers, git stage, git commit, git push, Docker, and deploy",
                "output artifacts must stay under Dream Studio meta/audit or Work Order storage",
                "exact staged file list is unavailable because this is not a commit execution phase",
                "stage exact file paths only is a future commit execution requirement, not approval for this review",
                "do not stage parent directories wholesale in any later commit execution phase",
                "git diff --cached --name-only is required only in a later approved commit execution phase",
                "git diff --cached --stat is required only in a later approved commit execution phase",
                "git diff --cached --check is required only in a later approved commit execution phase",
                "no push unless separately approved",
                "paused work artifact must be preserved as review evidence",
                "remaining deferred work must stay paused unless a future Work Order explicitly resumes it",
                "do not run deferred phases from this review packet",
                "resume requirements must be carried in any later continuity packet",
                "completed commit hashes are unavailable because this review must not commit",
            ],
        ),
        _section(
            "Handoff Understanding Report Requirement",
            [
                "Before taking action, produce a Handoff Understanding Report with:",
                *UNDERSTANDING_REQUIRED_TERMS,
            ],
        ),
        _section(
            "First Safe Action",
            (
                "Read the Phase 18S.13 report, mutation evidence, paused_work.yaml, Phase 18S.11 "
                "SecurityReviewReport, ReleaseGateSummary, and the three included finding records; "
                "then produce the Handoff Understanding Report before creating any approval artifact "
                "or inspecting Bill Stack."
            ),
        ),
        _section("Reviewed Remediation Findings", selected_refs),
        _section("All Phase 18S.11 Security Finding References", all_finding_refs),
    ]
    return "\n".join(lines).replace("\n\n\n", "\n\n").strip() + "\n"


def _security_eval_result(pass_fail: str, observed: str, evidence: list[str]) -> dict[str, Any]:
    return {
        "pass_fail": pass_fail,
        "observed_behavior": observed,
        "score": 1 if pass_fail == "pass" else 0,
        "evidence": evidence,
    }


def _allowed_commit_authority_leaks(sections: dict[str, str]) -> list[str]:
    allowed_body = sections.get("allowed_actions", "").lower()
    leak_patterns = (
        "commit only",
        "commit scoped",
        "commit changes",
        "stage changes",
        "stage only",
        "stage scoped",
        "stage and commit",
        "stage or commit",
        "git commit",
        "git add",
        "may commit",
        "can commit",
    )
    return [pattern for pattern in leak_patterns if pattern in allowed_body]


def _evaluate_security_no_commit_without_commit_phase(
    prompt_text: str,
    sections: dict[str, str],
) -> dict[str, Any]:
    handoff_type = sections.get("handoff_type", "").strip()
    phase_type = sections.get("phase_type", "").strip()
    is_approved_mutation = (
        handoff_type == HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION
        and phase_type == PHASE_TYPE_APPROVED_MUTATION
    )
    if not is_approved_mutation:
        return _security_eval_result(
            "pass",
            "security commit-boundary eval is not applicable to this non-approved-mutation handoff",
            ["handoff_type", "phase_type"],
        )

    prompt_lower = prompt_text.lower()
    boundary_body = "\n".join(
        sections.get(section, "").lower()
        for section in (
            "capability_boundary",
            "forbidden_actions",
            "approval_artifact_requirement",
            "readiness_rules",
            "before_after_evidence_requirements",
        )
    )
    leaks = _allowed_commit_authority_leaks(sections)
    forbids_stage_commit_push = (
        "do not stage, commit, or push" in boundary_body
        or "forbid stage, commit, and push" in boundary_body
        or (
            "do not stage" in boundary_body
            and "do not commit" in boundary_body
            and "do not push" in boundary_body
        )
    )
    defers_commit_planning = (
        "commit planning" in prompt_lower
        and "later" in prompt_lower
        and "work order" in prompt_lower
    )
    passes = forbids_stage_commit_push and defers_commit_planning and not leaks
    evidence = []
    if not forbids_stage_commit_push:
        evidence.append("missing explicit stage/commit/push prohibition")
    if not defers_commit_planning:
        evidence.append("missing later commit-planning Work Order boundary")
    evidence.extend(f"allowed action leak: {leak}" for leak in leaks)
    return _security_eval_result(
        "pass" if passes else "fail",
        (
            "approved security mutation handoff forbids stage/commit/push and defers commit planning"
            if passes
            else "approved security mutation handoff leaks or omits commit-boundary authority"
        ),
        evidence or ["stage_commit_push_forbidden", "commit_planning_deferred"],
    )


def evaluate_security_review_next_handoff_prompt(
    prompt_text: str,
    *,
    expected_release_gate: str,
    expected_finding_ids: list[str],
    expected_target_branch: str,
    expected_target_head: str,
    expected_untracked_entries: list[str],
) -> dict[str, dict[str, Any]]:
    """Run deterministic security-remediation handoff evals."""
    base = evaluate_handoff_prompt(
        prompt_text,
        readiness=READY_WITH_CONSTRAINTS,
        can_continue=True,
        target_repo_required=True,
        approval_required=False,
    )
    sections = parse_prompt_sections(prompt_text)
    missing_sections = [
        section
        for section in SECURITY_REMEDIATION_REQUIRED_SECTIONS
        if section not in sections
        or _body_missing(sections.get(section, ""), allow_unknown=section.startswith("baseline_"))
    ]
    prompt_lower = prompt_text.lower()

    finding_missing = [
        finding_id
        for finding_id in expected_finding_ids
        if finding_id not in prompt_text and _finding_short_id(finding_id) not in prompt_text
    ]
    release_missing = expected_release_gate not in prompt_text
    target_missing = [
        value
        for value in (expected_target_branch, expected_target_head)
        if value and value not in prompt_text
    ]
    if "target_baseline_constraints" not in sections:
        target_missing.append("target_baseline_constraints")
    target_missing.extend(entry for entry in expected_untracked_entries if entry not in prompt_text)
    forbidden_terms = (
        "do not mutate target repositories",
        "do not run scans",
        "do not run target validation",
        "do not read production secrets",
        "real .env values",
        "private keys",
        "credentials",
        "future remediation must be a separate approved mutation work order",
    )
    forbidden_missing = [term for term in forbidden_terms if term not in prompt_lower]
    remediation_bounded = (
        "remediation planning only" in prompt_lower
        and "separate approved mutation work order" in prompt_lower
        and "do not touch bill stack" in prompt_lower
    )
    no_mutation_without_approval = (
        "no bill stack files are approved for mutation" in prompt_lower
        and "create a new file-backed approval artifact before any later bill stack mutation"
        in prompt_lower
    )

    results = {
        **base,
        SECURITY_HANDOFF_FINDING_REFS_PRESENT: _security_eval_result(
            "pass" if not finding_missing else "fail",
            (
                "security handoff preserves expected finding references"
                if not finding_missing
                else f"security handoff missing finding references: {', '.join(finding_missing)}"
            ),
            finding_missing or expected_finding_ids,
        ),
        SECURITY_HANDOFF_RELEASE_GATE_PRESERVED: _security_eval_result(
            "pass" if not release_missing else "fail",
            (
                "security handoff preserves release-gate decision"
                if not release_missing
                else f"security handoff missing release gate {expected_release_gate}"
            ),
            [expected_release_gate],
        ),
        SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED: _security_eval_result(
            "pass" if not target_missing else "fail",
            (
                "security handoff preserves target branch/head and untracked-entry constraints"
                if not target_missing
                else f"security handoff missing target constraints: {', '.join(target_missing)}"
            ),
            target_missing
            or [expected_target_branch, expected_target_head, *expected_untracked_entries],
        ),
        SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED: _security_eval_result(
            "pass" if remediation_bounded else "fail",
            (
                "security handoff keeps Phase 18S.12 to remediation planning"
                if remediation_bounded
                else "security handoff does not clearly bound remediation planning from mutation"
            ),
            [
                "remediation planning only",
                "separate approved mutation Work Order",
                "do not touch Bill Stack",
            ],
        ),
        SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED: _security_eval_result(
            "pass" if not forbidden_missing else "fail",
            (
                "security handoff preserves forbidden actions"
                if not forbidden_missing
                else f"security handoff missing forbidden actions: {', '.join(forbidden_missing)}"
            ),
            forbidden_missing or list(forbidden_terms),
        ),
        SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL: _security_eval_result(
            "pass" if no_mutation_without_approval else "fail",
            (
                "security handoff blocks target mutation without later file-backed approval"
                if no_mutation_without_approval
                else "security handoff does not clearly block target mutation without later approval"
            ),
            ["approved files", "approval artifact requirement"],
        ),
        SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE: _evaluate_security_no_commit_without_commit_phase(
            prompt_text,
            sections,
        ),
    }
    contract_pass = not missing_sections and all(
        results[key]["pass_fail"] == "pass"
        for key in (
            HANDOFF_PROMPT_COMPLETENESS,
            HANDOFF_CONSTRAINT_PRESERVATION,
            HANDOFF_EXECUTION_READINESS,
            HANDOFF_FRESH_SESSION_SUFFICIENCY,
            SECURITY_HANDOFF_FINDING_REFS_PRESENT,
            SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
            SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
            SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
            SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
            SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
            SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
        )
    )
    results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE] = _security_eval_result(
        "pass" if contract_pass else "fail",
        (
            "ready-to-copy security next handoff satisfies contract and security preservation checks"
            if contract_pass
            else "ready-to-copy security next handoff is incomplete or unsafe"
        ),
        missing_sections or ["security_handoff_required_sections"],
    )
    return results


def evaluate_security_remediation_mutation_handoff_prompt(
    prompt_text: str,
    *,
    expected_release_gate: str,
    expected_finding_ids: list[str],
    expected_target_branch: str,
    expected_target_head: str,
    expected_untracked_entries: list[str],
) -> dict[str, dict[str, Any]]:
    """Run deterministic evals for approved security remediation mutation handoffs."""
    base = evaluate_handoff_prompt(
        prompt_text,
        readiness=READY_WITH_CONSTRAINTS,
        can_continue=True,
        target_repo_required=True,
        approval_required=True,
    )
    sections = parse_prompt_sections(prompt_text)
    missing_sections = [
        section
        for section in SECURITY_REMEDIATION_REQUIRED_SECTIONS
        if section not in sections
        or _body_missing(sections.get(section, ""), allow_unknown=section.startswith("baseline_"))
    ]
    prompt_lower = prompt_text.lower()

    finding_missing = [
        finding_id
        for finding_id in expected_finding_ids
        if finding_id not in prompt_text and _finding_short_id(finding_id) not in prompt_text
    ]
    release_missing = expected_release_gate not in prompt_text
    target_missing = [
        value
        for value in (expected_target_branch, expected_target_head)
        if value and value not in prompt_text
    ]
    if "target_baseline_constraints" not in sections:
        target_missing.append("target_baseline_constraints")
    target_missing.extend(entry for entry in expected_untracked_entries if entry not in prompt_text)
    forbidden_terms = (
        "do not stage, commit, or push",
        "commit planning must occur in a later separate work order",
        "do not run scans",
        "do not run target validation",
        "do not update dependencies or lockfiles",
        "do not add schema migrations",
        "do not implement browser token/session architecture changes",
        "do not implement durable auth-state storage",
        "do not inspect untracked entries",
        "real .env values",
        "private keys",
        "credentials",
    )
    forbidden_missing = [term for term in forbidden_terms if term not in prompt_lower]
    remediation_bounded = (
        "approved mutation work order" in prompt_lower
        and "revenuecat webhook authentication" in prompt_lower
        and "household invite-code" in prompt_lower
        and "server-side password policy" in prompt_lower
        and "later work orders" in prompt_lower
    )
    no_mutation_without_approval = (
        "approval artifact exists before bill stack source inspection or mutation" in prompt_lower
        or "before inspecting or mutating bill stack source, create a file-backed approval artifact"
        in prompt_lower
    )
    no_commit_result = _evaluate_security_no_commit_without_commit_phase(prompt_text, sections)

    results = {
        **base,
        SECURITY_HANDOFF_FINDING_REFS_PRESENT: _security_eval_result(
            "pass" if not finding_missing else "fail",
            (
                "security mutation handoff preserves expected finding references"
                if not finding_missing
                else f"security mutation handoff missing finding references: {', '.join(finding_missing)}"
            ),
            finding_missing or expected_finding_ids,
        ),
        SECURITY_HANDOFF_RELEASE_GATE_PRESERVED: _security_eval_result(
            "pass" if not release_missing else "fail",
            (
                "security mutation handoff preserves release-gate decision"
                if not release_missing
                else f"security mutation handoff missing release gate {expected_release_gate}"
            ),
            [expected_release_gate],
        ),
        SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED: _security_eval_result(
            "pass" if not target_missing else "fail",
            (
                "security mutation handoff preserves target branch/head and untracked-entry constraints"
                if not target_missing
                else f"security mutation handoff missing target constraints: {', '.join(target_missing)}"
            ),
            target_missing
            or [expected_target_branch, expected_target_head, *expected_untracked_entries],
        ),
        SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED: _security_eval_result(
            "pass" if remediation_bounded else "fail",
            (
                "security mutation handoff keeps remediation scope bounded to priority findings"
                if remediation_bounded
                else "security mutation handoff does not clearly bound priority remediation scope"
            ),
            [
                "RevenueCat webhook authentication",
                "household invite-code",
                "server-side password policy",
                "later Work Orders",
            ],
        ),
        SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED: _security_eval_result(
            "pass" if not forbidden_missing else "fail",
            (
                "security mutation handoff preserves forbidden actions"
                if not forbidden_missing
                else f"security mutation handoff missing forbidden actions: {', '.join(forbidden_missing)}"
            ),
            forbidden_missing or list(forbidden_terms),
        ),
        SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL: _security_eval_result(
            "pass" if no_mutation_without_approval else "fail",
            (
                "security mutation handoff requires approval artifact before target source inspection or mutation"
                if no_mutation_without_approval
                else "security mutation handoff does not require approval before target source inspection or mutation"
            ),
            ["approval artifact requirement", "before/after evidence requirements"],
        ),
        SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE: no_commit_result,
    }
    contract_pass = not missing_sections and all(
        results[key]["pass_fail"] == "pass"
        for key in (
            HANDOFF_PROMPT_COMPLETENESS,
            HANDOFF_CONSTRAINT_PRESERVATION,
            HANDOFF_EXECUTION_READINESS,
            HANDOFF_FRESH_SESSION_SUFFICIENCY,
            SECURITY_HANDOFF_FINDING_REFS_PRESENT,
            SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
            SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
            SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
            SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
            SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
            SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
        )
    )
    results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE] = _security_eval_result(
        "pass" if contract_pass else "fail",
        (
            "ready-to-copy security mutation handoff satisfies contract and commit-boundary checks"
            if contract_pass
            else "ready-to-copy security mutation handoff is incomplete or unsafe"
        ),
        missing_sections or ["security_mutation_handoff_required_sections"],
    )
    return results


def evaluate_security_post_remediation_review_handoff_prompt(
    prompt_text: str,
    *,
    expected_release_gate: str,
    expected_finding_ids: list[str],
    expected_target_branch: str,
    expected_target_head: str,
    expected_untracked_entries: list[str],
    expected_changed_files: list[str],
    expected_validation_terms: list[str],
) -> dict[str, dict[str, Any]]:
    """Run deterministic evals for post-remediation security review handoffs."""
    base = evaluate_handoff_prompt(
        prompt_text,
        readiness=READY_WITH_CONSTRAINTS,
        can_continue=True,
        target_repo_required=True,
        approval_required=True,
    )
    sections = parse_prompt_sections(prompt_text)
    missing_sections = [
        section
        for section in SECURITY_REMEDIATION_REQUIRED_SECTIONS
        if section not in sections
        or _body_missing(sections.get(section, ""), allow_unknown=section.startswith("baseline_"))
    ]
    prompt_lower = prompt_text.lower()

    finding_missing = [
        finding_id
        for finding_id in expected_finding_ids
        if finding_id not in prompt_text and _finding_short_id(finding_id) not in prompt_text
    ]
    release_missing = expected_release_gate not in prompt_text
    target_missing = [
        value
        for value in (expected_target_branch, expected_target_head)
        if value and value not in prompt_text
    ]
    if "target_baseline_constraints" not in sections:
        target_missing.append("target_baseline_constraints")
    target_missing.extend(entry for entry in expected_untracked_entries if entry not in prompt_text)
    changed_missing = [
        changed_file for changed_file in expected_changed_files if changed_file not in prompt_text
    ]
    validation_missing = [
        term for term in expected_validation_terms if term and term not in prompt_text
    ]
    forbidden_terms = (
        "do not mutate bill stack",
        "do not mutate target repositories",
        "do not stage, commit, or push",
        "do not run scans unless a later work order separately approves them",
        "do not run broad target validation",
        "do not read production secrets",
        "real .env values",
        "private keys",
        "credentials",
        "commit planning must remain a later separate work order",
        "do not inspect untracked entries unless separately approved",
    )
    forbidden_missing = [term for term in forbidden_terms if term not in prompt_lower]
    review_bounded = (
        "observe-only post-remediation security review" in prompt_lower
        and "determine whether each finding can be marked remediated" in prompt_lower
        and "run_additional_security_review" in prompt_lower
    )
    no_mutation_without_approval = (
        "no bill stack files are approved for mutation" in prompt_lower
        and "approval artifact" in prompt_lower
        and "read-only" in prompt_lower
    )

    results = {
        **base,
        SECURITY_HANDOFF_FINDING_REFS_PRESENT: _security_eval_result(
            "pass" if not finding_missing else "fail",
            (
                "post-remediation handoff preserves expected finding references"
                if not finding_missing
                else f"post-remediation handoff missing finding references: {', '.join(finding_missing)}"
            ),
            finding_missing or expected_finding_ids,
        ),
        SECURITY_HANDOFF_RELEASE_GATE_PRESERVED: _security_eval_result(
            "pass" if not release_missing else "fail",
            (
                "post-remediation handoff preserves release-gate decision"
                if not release_missing
                else f"post-remediation handoff missing release gate {expected_release_gate}"
            ),
            [expected_release_gate],
        ),
        SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED: _security_eval_result(
            "pass" if not target_missing else "fail",
            (
                "post-remediation handoff preserves target branch/head and untracked-entry constraints"
                if not target_missing
                else f"post-remediation handoff missing target constraints: {', '.join(target_missing)}"
            ),
            target_missing
            or [expected_target_branch, expected_target_head, *expected_untracked_entries],
        ),
        SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED: _security_eval_result(
            "pass" if review_bounded and not changed_missing and not validation_missing else "fail",
            (
                "post-remediation handoff bounds review to remediated findings and preserves mutation evidence"
                if review_bounded and not changed_missing and not validation_missing
                else "post-remediation handoff is missing review scope, changed files, or validation evidence"
            ),
            changed_missing + validation_missing
            or [
                "observe-only post-remediation security review",
                "changed files",
                "focused validation",
            ],
        ),
        SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED: _security_eval_result(
            "pass" if not forbidden_missing else "fail",
            (
                "post-remediation handoff preserves forbidden actions"
                if not forbidden_missing
                else f"post-remediation handoff missing forbidden actions: {', '.join(forbidden_missing)}"
            ),
            forbidden_missing or list(forbidden_terms),
        ),
        SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL: _security_eval_result(
            "pass" if no_mutation_without_approval else "fail",
            (
                "post-remediation handoff forbids mutation and requires approval before read-only inspection"
                if no_mutation_without_approval
                else "post-remediation handoff does not clearly forbid mutation before approval"
            ),
            ["approved files", "approval artifact requirement", "read-only"],
        ),
        SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE: _evaluate_security_no_commit_without_commit_phase(
            prompt_text,
            sections,
        ),
    }
    contract_pass = not missing_sections and all(
        results[key]["pass_fail"] == "pass"
        for key in (
            HANDOFF_PROMPT_COMPLETENESS,
            HANDOFF_CONSTRAINT_PRESERVATION,
            HANDOFF_EXECUTION_READINESS,
            HANDOFF_FRESH_SESSION_SUFFICIENCY,
            SECURITY_HANDOFF_FINDING_REFS_PRESENT,
            SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
            SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
            SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
            SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
            SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
            SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
        )
    )
    results[READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE] = _security_eval_result(
        "pass" if contract_pass else "fail",
        (
            "ready-to-copy post-remediation security review handoff satisfies contract"
            if contract_pass
            else "ready-to-copy post-remediation security review handoff is incomplete or unsafe"
        ),
        missing_sections or ["security_post_remediation_review_required_sections"],
    )
    return results
