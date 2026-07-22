"""WO-SPLIT-HANDOFF: handoff build helper module (pure section-content builders)."""

from __future__ import annotations
import re
from pathlib import Path
from typing import Any

from .handoff_constants import (
    HANDOFF_TYPE_COMMIT_EXECUTION,
    PHASE_TYPE_COMMIT_PLANNING,
    PHASE_TYPE_PRODUCT_CLOSEOUT,
    PHASE_TYPE_RECOVERY_DECISION,
)
from .handoff_helpers import _as_list, _extract_prefixed, _transition_recommendation


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
