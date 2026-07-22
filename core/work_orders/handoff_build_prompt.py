"""WO-SPLIT-HANDOFF: handoff build prompt-assembly module.

_operator_decision_request_summary and _operator_decision_summary are
relocated here (their original position was after build_handoff_prompt in the
monolithic handoff_build.py) because build_handoff_prompt calls them; keeping
them in the same module as their only caller avoids a needless import hop.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

from .handoff_constants import (
    CONSTRAINT_TERMS,
    DECISION_TAXONOMIES,
    FRESH_SESSION_RULE,
    HANDOFF_CONSTRAINT_PRESERVATION,
    HANDOFF_EXECUTION_READINESS,
    HANDOFF_FRESH_SESSION_SUFFICIENCY,
    HANDOFF_PROMPT_COMPLETENESS,
    HANDOFF_TYPE_RECOVERY_DECISION,
    HOLD,
    PHASE_TYPE_PRODUCT_CLOSEOUT,
    READY,
    READY_WITH_CONSTRAINTS,
    UNDERSTANDING_REQUIRED_TERMS,
)
from .handoff_helpers import (
    _as_list,
    _decision_rationale,
    _extract_work_order_id,
    _final_decision,
    _format_list,
    _handoff_context,
    _handoff_type,
    _next_mode,
    _next_recommendation,
    _phase_type,
    _section,
)
from .handoff_build_helpers import (
    _current_state_for_recovery,
    _database_relationship_context,
    _evidence_refs,
    _executable_design_boundary,
    _expected_verdict,
    _final_response_requirements,
    _forbidden_recovery_actions,
    _known_safe_recovery_actions,
    _next_allowed_action_after_operator_approval,
    _next_handoff_requirements,
    _next_objective,
    _next_risk,
    _phase_name,
    _phase_specific_safety_constraints,
    _prior_attempt_summary,
    _product_closeout_allowed_actions,
    _product_closeout_forbidden_files,
    _output_artifacts,
    _readiness_rules,
    _recovery_options,
    _source_authority_refs,
    _source_failure,
    _transition_rationale,
    _validation_refs,
)
from .handoff_build_push import (
    _is_push_execution_handoff,
    _push_after_evidence,
    _push_allowed_actions,
    _push_approved_files,
    _push_approved_target,
    _push_before_evidence,
    _push_eval_requirements,
    _push_execution_context,
    _push_first_safe_action,
    _push_forbidden_actions,
    _push_forbidden_files,
    _push_stop_conditions,
)


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
