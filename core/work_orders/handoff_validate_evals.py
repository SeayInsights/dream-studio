"""WO-SPLIT-HANDOFF: handoff prompt eval module."""

from __future__ import annotations
from typing import Any

from .handoff_constants import (
    CONSTRAINT_TERMS,
    DECISION_TAXONOMIES,
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
    HANDOFF_TYPE_HOLD_REVIEW,
    HANDOFF_TYPE_RECOVERY_DECISION,
    PUSH_EXECUTION_REQUIRED_SECTIONS,
    READY,
    READY_WITH_CONSTRAINTS,
    RECOVERY_DECISION_REQUIRED_SECTIONS,
)
from .handoff_helpers import _body_missing
from .handoff_validate_sections import parse_prompt_sections
from .handoff_validate_dryrun import dry_run_handoff_prompt, _is_push_execution_sections


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
