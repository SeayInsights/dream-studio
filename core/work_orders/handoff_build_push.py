"""WO-SPLIT-HANDOFF: handoff build push-execution helper module."""

from __future__ import annotations
from pathlib import Path
from typing import Any

from .handoff_constants import (
    HANDOFF_CONSTRAINT_PRESERVATION,
    HANDOFF_EXECUTION_READINESS,
    HANDOFF_FRESH_SESSION_SUFFICIENCY,
    HANDOFF_PROMPT_COMPLETENESS,
    HANDOFF_PUSH_EVIDENCE_REQUIREMENTS,
    HANDOFF_PUSH_EXECUTION_COMPLETENESS,
    HANDOFF_PUSH_TARGET_CONSTRAINTS,
    HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
    PHASE_TYPE_PUSH_PLANNING,
)
from .handoff_helpers import _as_list, _handoff_context


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
