"""WO-SPLIT-HANDOFF: handoff validate module."""

from __future__ import annotations
import re
from typing import Any
from .milestones import (
    ALLOWED_HANDOFF_REASONS,
    INVALID_HANDOFF_REASONS,
)

from .handoff_constants import (
    CONSTRAINT_TERMS,
    DECISION_TAXONOMIES,
    FAIL,
    FRESH_SESSION_RULE,
    HANDOFF_CONSTRAINT_PRESERVATION,
    HANDOFF_CURRENT_STATE_COMPLETENESS,
    HANDOFF_EXECUTION_READINESS,
    HANDOFF_FRESH_SESSION_SUFFICIENCY,
    HANDOFF_HOOK_BEHAVIOR_AWARENESS,
    HANDOFF_INDEX_STATE_REQUIREMENTS,
    HANDOFF_OPERATOR_DECISION_GATE,
    HANDOFF_PATH_INTEGRITY,
    HANDOFF_PROMPT_COMPLETENESS,
    HANDOFF_PUSH_EVIDENCE_REQUIREMENTS,
    HANDOFF_PUSH_EXECUTION_COMPLETENESS,
    HANDOFF_PUSH_TARGET_CONSTRAINTS,
    HANDOFF_RECOVERY_MODE_COMPLETENESS,
    HANDOFF_RECOVERY_OPTION_CLARITY,
    HANDOFF_SELF_VALIDATION,
    HANDOFF_TYPES,
    HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
    HANDOFF_TYPE_COMMIT_EXECUTION,
    HANDOFF_TYPE_HOLD_REVIEW,
    HANDOFF_TYPE_RECOVERY_DECISION,
    HOLD,
    PHASE_TYPE_PUSH_PLANNING,
    PUSH_EXECUTION_REQUIRED_SECTIONS,
    READY,
    READY_WITH_CONSTRAINTS,
    RECOVERY_DECISION_REQUIRED_SECTIONS,
    REQUIRED_HANDOFF_SECTIONS,
    UNDERSTANDING_REQUIRED_TERMS,
    _MALFORMED_DREAM_STUDIO_META_ROOT_RE,
    _WINDOWS_ABSOLUTE_PATH_RE,
)
from .handoff_helpers import _body_missing, _section_list, _section_text
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
