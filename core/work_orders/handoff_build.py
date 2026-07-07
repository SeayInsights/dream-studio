"""WO-SPLIT-HANDOFF: handoff build module."""

from __future__ import annotations
import re
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
    HANDOFF_PUSH_EVIDENCE_REQUIREMENTS,
    HANDOFF_PUSH_EXECUTION_COMPLETENESS,
    HANDOFF_PUSH_TARGET_CONSTRAINTS,
    HANDOFF_TYPES,
    HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
    HANDOFF_TYPE_COMMIT_EXECUTION,
    HANDOFF_TYPE_RECOVERY_DECISION,
    HANDOFF_TYPE_RECOVERY_EXECUTION,
    HOLD,
    PHASE_TYPE_COMMIT_PLANNING,
    PHASE_TYPE_PRODUCT_CLOSEOUT,
    PHASE_TYPE_PUSH_PLANNING,
    PHASE_TYPE_RECOVERY_DECISION,
    READY,
    READY_WITH_CONSTRAINTS,
    UNDERSTANDING_REQUIRED_TERMS,
)
from .handoff_helpers import (
    _as_list,
    _decision_rationale,
    _extract_prefixed,
    _extract_work_order_id,
    _final_decision,
    _format_list,
    _handoff_context,
    _handoff_type,
    _milestone_state,
    _next_mode,
    _next_recommendation,
    _phase_type,
    _section,
    _transition_recommendation,
)
from .handoff_decision import determine_next_action_decision, determine_sequential_readiness


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
