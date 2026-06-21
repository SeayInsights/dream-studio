"""File-backed Work Order eval artifacts."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from compat import UTC

from .handoff import (
    HANDOFF_CONSTRAINT_PRESERVATION,
    HANDOFF_CURRENT_STATE_COMPLETENESS,
    HANDOFF_EVAL_TYPES,
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
    evaluate_handoff_prompt,
)
from .models import SKILL_ID_RE, WorkOrderError
from .storage import work_order_dir

RENDER_COMPLETENESS = "work_order_render_completeness"
SKILL_IDENTIFIER_SAFETY = "skill_identifier_safety"
OBSERVE_ONLY_COMPLIANCE = "observe_only_compliance"
FORBIDDEN_ACTION_COMPLIANCE = "forbidden_action_compliance"
TARGET_REPO_MUTATION = "target_repo_mutation"
APPROVED_MUTATION_COMPLIANCE = "approved_mutation_compliance"
RESULT_REPORT_COMPLETENESS = "result_report_completeness"
NEXT_WORK_ORDER_RECOMMENDATION = "next_work_order_recommendation"
OPERATOR_DECISION_REQUEST_COMPLETENESS = "operator_decision_request_completeness"
OPERATOR_DECISION_VALIDITY = "operator_decision_validity"
OPERATOR_DECISION_REQUIRED_BEFORE_EXECUTION = "operator_decision_required_before_execution"
OPERATOR_DECISION_REASON_COMPLETENESS = "operator_decision_reason_completeness"
PHASE16_RENDER_EVALS = frozenset({RENDER_COMPLETENESS, SKILL_IDENTIFIER_SAFETY})
PHASE16_RESULT_EVALS = frozenset(
    {
        OBSERVE_ONLY_COMPLIANCE,
        APPROVED_MUTATION_COMPLIANCE,
        FORBIDDEN_ACTION_COMPLIANCE,
        TARGET_REPO_MUTATION,
        RESULT_REPORT_COMPLETENESS,
        NEXT_WORK_ORDER_RECOMMENDATION,
    }
)
PHASE17_HANDOFF_EVALS = HANDOFF_EVAL_TYPES
PHASE17_OPERATOR_DECISION_EVALS = frozenset(
    {
        OPERATOR_DECISION_REQUEST_COMPLETENESS,
        OPERATOR_DECISION_VALIDITY,
        OPERATOR_DECISION_REQUIRED_BEFORE_EXECUTION,
        OPERATOR_DECISION_REASON_COMPLETENESS,
    }
)

REQUIRED_PACKET_TERMS = (
    "Work Order ID",
    "Project Name",
    "Target Project Path",
    "Objective",
    "Approval Mode",
    "Risk Level",
    "Render-Only Posture",
    "Scope Include",
    "Scope Exclude",
    "Allowed Skills",
    "Workflow",
    "Forbidden Actions",
    "Validation Commands",
    "Stop Conditions",
    "Expected Output",
    "Do not edit",
    "Do not delete",
    "Do not commit",
    "Do not change dependencies",
    "Do not change schema",
)


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _legacy_skill_prefixes() -> tuple[str, str]:
    return ("dream" "-studio" + ":", "d" "s" + ":")


def _eval_dir(work_order_id: str, *, storage_root: Path | str | None = None) -> Path:
    return work_order_dir(work_order_id, storage_root=storage_root) / "evals"


def _approval_path(work_order_id: str, *, storage_root: Path | str | None = None) -> Path:
    return work_order_dir(work_order_id, storage_root=storage_root) / "approvals" / "approval.json"


def load_approval_evidence(
    work_order: dict[str, Any],
    *,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any] | None, Path]:
    """Load file-backed approval evidence without inspecting target repos."""
    path = _approval_path(
        str(work_order.get("work_order_id", "unknown")), storage_root=storage_root
    )
    if not path.is_file():
        return None, path
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"_invalid": "approval evidence could not be parsed."}, path
    if not isinstance(data, dict):
        return {"_invalid": "approval evidence must be a mapping."}, path
    return data, path


def _write_eval(
    artifact: dict[str, Any],
    *,
    storage_root: Path | str | None = None,
) -> Path:
    work_order_id = str(artifact["linked_work_order_id"])
    target_dir = _eval_dir(work_order_id, storage_root=storage_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{artifact['eval_type']}.json"
    tmp_path = target_dir / f".{artifact['eval_type']}.json.tmp"
    tmp_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(target_path)
    _emit_eval_telemetry(artifact, target_path)
    return target_path


def _emit_eval_telemetry(artifact: dict[str, Any], target_path: Path) -> None:
    """Best-effort dual-write for file-backed eval artifacts."""

    if os.environ.get(
        "DREAM_STUDIO_ENABLE_WORK_ORDER_EVAL_TELEMETRY"
    ) != "1" and not os.environ.get("DREAM_STUDIO_TELEMETRY_DB"):
        return
    try:
        from core.telemetry.emitters import TelemetryContext, emit_validation_result

        pass_fail = str(artifact.get("pass_fail", "unknown"))
        evidence = [str(target_path), *[str(item) for item in artifact.get("evidence", [])]]
        emit_validation_result(
            validation_type=str(artifact.get("eval_type", "work_order_eval")),
            status=pass_fail,
            command=None,
            scope=str(artifact.get("subject_type", "work_order")),
            summary=str(artifact.get("observed_behavior", "")) or None,
            pass_count=1 if pass_fail == "pass" else 0,
            fail_count=1 if pass_fail == "fail" else 0,
            error_count=0,
            warning_count=0,
            context=TelemetryContext(
                project_id="dream-studio",
                milestone_id=str(artifact.get("milestone_id", "work_order_eval"))
                or "work_order_eval",
                task_id=str(artifact.get("linked_work_order_id", "")) or None,
                process_run_id=str(artifact.get("linked_work_order_id", "")) or None,
                source_refs=("core/work_orders/evals.py",),
                evidence_refs=tuple(evidence),
            ),
        )
    except Exception:
        return


def _base_artifact(
    *,
    work_order: dict[str, Any],
    eval_type: str,
    expected_behavior: str,
    observed_behavior: str,
    pass_fail: str,
    evidence: list[str],
    score: int | str,
) -> dict[str, Any]:
    work_order_id = str(work_order.get("work_order_id", "unknown"))
    return {
        "eval_id": f"{work_order_id}.{eval_type}",
        "eval_type": eval_type,
        "subject_type": "work_order",
        "subject_id": work_order_id,
        "linked_work_order_id": work_order_id,
        "input_artifact": evidence[0] if evidence else "unavailable",
        "expected_behavior": expected_behavior,
        "observed_behavior": observed_behavior,
        "score": score,
        "pass_fail": pass_fail,
        "evaluator": "deterministic",
        "evidence": evidence or ["unavailable"],
        "privacy_export_classification": "local_only",
        "created_at": _now(),
    }


def create_render_completeness_eval(
    *,
    work_order: dict[str, Any],
    target: str,
    packet_path: Path,
    packet_text: str,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Write a deterministic render completeness eval artifact."""
    missing = [term for term in REQUIRED_PACKET_TERMS if term not in packet_text]
    pass_fail = "pass" if not missing and packet_path.is_file() else "fail"
    observed = (
        f"{target} packet includes required render fields and prohibitions."
        if pass_fail == "pass"
        else f"{target} packet missing evidence: {', '.join(missing) or 'packet file unavailable'}."
    )
    artifact = _base_artifact(
        work_order=work_order,
        eval_type=RENDER_COMPLETENESS,
        expected_behavior="Rendered packet includes required fields, scope, validation, stop conditions, and render-only prohibitions.",
        observed_behavior=observed,
        pass_fail=pass_fail,
        evidence=[str(packet_path)],
        score=1 if pass_fail == "pass" else 0,
    )
    path = _write_eval(artifact, storage_root=storage_root)
    return artifact, path


def create_skill_identifier_safety_eval(
    *,
    work_order: dict[str, Any],
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Write a deterministic skill identifier safety eval artifact."""
    skills = work_order.get("allowed_skills")
    legacy_product, legacy_ds = _legacy_skill_prefixes()
    bad: list[str] = []
    if not isinstance(skills, list):
        bad.append("allowed_skills unavailable")
    else:
        for skill in skills:
            if not isinstance(skill, str):
                bad.append("<non-string>")
            elif skill.startswith(legacy_product) or skill.startswith(legacy_ds):
                bad.append(skill)
            elif not SKILL_ID_RE.fullmatch(skill):
                bad.append(skill)

    pass_fail = "pass" if not bad else "fail"
    observed = (
        "All allowed skills use ds-<slug> identifiers."
        if pass_fail == "pass"
        else f"Unsafe skill identifiers found: {', '.join(bad)}."
    )
    artifact = _base_artifact(
        work_order=work_order,
        eval_type=SKILL_IDENTIFIER_SAFETY,
        expected_behavior="allowed_skills use ds-<slug> and reject legacy product-name or colon-delimited forms.",
        observed_behavior=observed,
        pass_fail=pass_fail,
        evidence=["allowed_skills"],
        score=1 if pass_fail == "pass" else 0,
    )
    path = _write_eval(artifact, storage_root=storage_root)
    return artifact, path


def _result_evidence_text(result_text: str | None, result_metadata: dict[str, Any] | None) -> str:
    pieces = [result_text or ""]
    if result_metadata:
        pieces.append(json.dumps(result_metadata, sort_keys=True))
    return "\n".join(pieces).lower()


def _has_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _normalize_file_path(value: Any) -> str:
    text = str(value).strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.strip("/")


_NO_CHANGE_MARKERS = {"none", "no files changed", "files changed: none"}
_MISSING_CHANGE_MARKERS = {"", "n/a", "not run", "unavailable", "unknown"}


def _normalize_changed_files(changed_files: list[Any] | tuple[Any, ...] | None) -> list[str] | None:
    if changed_files is None:
        return None
    normalized: list[str] = []
    saw_explicit_no_change = False
    for item in changed_files:
        text = str(item).strip()
        lowered = text.lower()
        if lowered in _NO_CHANGE_MARKERS:
            saw_explicit_no_change = True
            continue
        if lowered in _MISSING_CHANGE_MARKERS:
            return None
        if "," in text:
            split = [part.strip() for part in text.split(",") if part.strip()]
            nested = _normalize_changed_files(split)
            if nested is None:
                return None
            normalized.extend(nested)
            continue
        normalized.append(_normalize_file_path(text))
    if normalized:
        return sorted(set(normalized))
    if saw_explicit_no_change or not changed_files:
        return []
    return None


def _changed_files_from_snapshots(
    before_snapshot: dict[str, str] | None,
    after_snapshot: dict[str, str] | None,
) -> list[str] | None:
    if before_snapshot is None or after_snapshot is None:
        return None
    changed = sorted(set(before_snapshot) ^ set(after_snapshot))
    changed.extend(
        sorted(
            path
            for path in set(before_snapshot).intersection(after_snapshot)
            if before_snapshot[path] != after_snapshot[path]
        )
    )
    return [_normalize_file_path(path) for path in changed]


def _approval_problem(approval: dict[str, Any] | None) -> str | None:
    if approval is None:
        return "approval evidence unavailable."
    if approval.get("_invalid"):
        return str(approval["_invalid"])
    required = (
        "approval_status",
        "approved_by",
        "approved_at",
        "approval_mode",
        "approved_files",
        "forbidden_files",
        "approval_scope",
    )
    missing = [
        field for field in required if field not in approval or approval.get(field) in (None, "")
    ]
    if missing:
        return f"approval evidence missing required fields: {', '.join(missing)}."
    if approval.get("approval_status") != "approved":
        return "approval_status is not approved."
    if approval.get("approval_mode") != "approval_required":
        return "approval_mode is not approval_required."
    if not isinstance(approval.get("approved_files"), list):
        return "approved_files must be a list."
    if not isinstance(approval.get("forbidden_files"), list):
        return "forbidden_files must be a list."
    return None


def _approved_file_sets(approval: dict[str, Any]) -> tuple[set[str], set[str]]:
    approved = {
        _normalize_file_path(path)
        for path in approval.get("approved_files", [])
        if str(path).strip()
    }
    forbidden = {
        _normalize_file_path(path)
        for path in approval.get("forbidden_files", [])
        if str(path).strip()
    }
    return approved, forbidden


def _evaluate_approved_mutation(
    *,
    approval: dict[str, Any] | None,
    changed_files: list[Any] | tuple[Any, ...] | None,
) -> tuple[str, str, int | str, list[str]]:
    normalized_changes = _normalize_changed_files(changed_files)
    approval_issue = _approval_problem(approval)
    if normalized_changes is None:
        if approval_issue:
            return (
                "incomplete",
                f"{approval_issue} changed-file evidence unavailable.",
                "not_scored",
                ["approval_evidence", "changed_files_unavailable"],
            )
        return (
            "incomplete",
            "approval evidence exists, but changed-file evidence unavailable.",
            "not_scored",
            ["approval_evidence", "changed_files_unavailable"],
        )

    if approval_issue:
        if normalized_changes:
            return (
                "fail",
                f"mutation evidence exists without valid approval evidence: {approval_issue}",
                0,
                ["approval_evidence", "changed_files"],
            )
        return (
            "incomplete",
            f"{approval_issue} no changed files were explicitly recorded.",
            "not_scored",
            ["approval_evidence", "changed_files"],
        )

    assert approval is not None
    approved_files, forbidden_files = _approved_file_sets(approval)
    forbidden_changed = sorted(set(normalized_changes).intersection(forbidden_files))
    unapproved = sorted(path for path in normalized_changes if path not in approved_files)

    if forbidden_changed:
        return (
            "fail",
            f"forbidden file changed under approval_required mode: {', '.join(forbidden_changed)}.",
            0,
            ["approval_evidence", "changed_files"],
        )
    if unapproved:
        return (
            "fail",
            f"unapproved file changed under approval_required mode: {', '.join(unapproved)}.",
            0,
            ["approval_evidence", "changed_files"],
        )
    return (
        "pass",
        "approval evidence is valid and explicit changed-file evidence is wholly within approved_files.",
        1,
        ["approval_evidence", "changed_files"],
    )


def create_observe_only_compliance_eval(
    *,
    work_order: dict[str, Any],
    result_text: str | None,
    result_metadata: dict[str, Any] | None,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Evaluate explicit observe-only evidence without inspecting target paths."""
    if work_order.get("approval_mode") != "observe_only":
        artifact = _base_artifact(
            work_order=work_order,
            eval_type=OBSERVE_ONLY_COMPLIANCE,
            expected_behavior="observe_only_compliance applies only to observe_only Work Orders.",
            observed_behavior=(
                f"Work Order approval_mode is {work_order.get('approval_mode', 'unavailable')}; "
                "approved_mutation_compliance is the applicable eval for approval_required mutation slices."
            ),
            pass_fail="incomplete",
            evidence=[str((result_metadata or {}).get("raw_output_ref", "mode_not_applicable"))],
            score="not_scored",
        )
        path = _write_eval(artifact, storage_root=storage_root)
        return artifact, path

    evidence_text = _result_evidence_text(result_text, result_metadata)
    violation_markers = (
        "files changed:",
        "file changed:",
        "edited",
        "committed",
        "pushed",
        "deleted",
        "schema changed",
        "dependency changed",
        "db write",
        "external action",
        "target mutation: yes",
    )
    explicit_clean_markers = (
        "files changed: none",
        "target mutation: no",
        "observe-only compliance: pass",
        "no target repo mutation",
    )

    if not evidence_text.strip():
        pass_fail = "incomplete"
        observed = "observe-only evidence unavailable."
        score: int | str = "not_scored"
    elif _has_any(evidence_text, violation_markers) and "files changed: none" not in evidence_text:
        pass_fail = "fail"
        observed = "explicit mutation or forbidden side-effect evidence was recorded."
        score = 0
    elif _has_any(evidence_text, explicit_clean_markers):
        pass_fail = "pass"
        observed = "explicit observe-only evidence reports no mutation or forbidden side effects."
        score = 1
    else:
        pass_fail = "incomplete"
        observed = "observe-only evidence is present but does not explicitly prove no mutation."
        score = "not_scored"

    artifact = _base_artifact(
        work_order=work_order,
        eval_type=OBSERVE_ONLY_COMPLIANCE,
        expected_behavior="Result evidence explicitly shows observe-only behavior with no edits, commits, schema changes, dependency changes, DB writes, external actions, or target mutation.",
        observed_behavior=observed,
        pass_fail=pass_fail,
        evidence=[str((result_metadata or {}).get("raw_output_ref", "evidence_unavailable"))],
        score=score,
    )
    path = _write_eval(artifact, storage_root=storage_root)
    return artifact, path


def create_approved_mutation_compliance_eval(
    *,
    work_order: dict[str, Any],
    changed_files: list[Any] | tuple[Any, ...] | None = None,
    approval_evidence: dict[str, Any] | None = None,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Evaluate approved mutation using file-backed approval and explicit file evidence."""
    loaded_approval, approval_path = (
        (
            approval_evidence,
            _approval_path(
                str(work_order.get("work_order_id", "unknown")), storage_root=storage_root
            ),
        )
        if approval_evidence is not None
        else load_approval_evidence(work_order, storage_root=storage_root)
    )

    pass_fail, observed, score, evidence = _evaluate_approved_mutation(
        approval=loaded_approval,
        changed_files=changed_files,
    )
    evidence_refs = [
        str(approval_path) if approval_path.is_file() else "approval_evidence_unavailable",
        *evidence,
    ]
    artifact = _base_artifact(
        work_order=work_order,
        eval_type=APPROVED_MUTATION_COMPLIANCE,
        expected_behavior="approval_required Work Orders may mutate only with valid approval evidence and explicit changed-file evidence wholly within approved_files.",
        observed_behavior=observed,
        pass_fail=pass_fail,
        evidence=evidence_refs,
        score=score,
    )
    path = _write_eval(artifact, storage_root=storage_root)
    return artifact, path


def create_forbidden_action_compliance_eval(
    *,
    work_order: dict[str, Any],
    result_text: str | None,
    result_metadata: dict[str, Any] | None,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Evaluate forbidden-action evidence without executing anything."""
    evidence_text = _result_evidence_text(result_text, result_metadata)
    violation_markers = (
        "forbidden action: violated",
        "forbidden actions: violated",
        "committed",
        "pushed",
        "deleted",
        "schema changed",
        "dependency changed",
        "target mutation: yes",
    )
    clean_markers = (
        "forbidden actions: complied",
        "forbidden action compliance: pass",
        "no forbidden actions",
    )

    if not evidence_text.strip():
        pass_fail = "incomplete"
        observed = "forbidden-action evidence unavailable."
        score: int | str = "not_scored"
    elif _has_any(evidence_text, violation_markers):
        pass_fail = "fail"
        observed = "explicit forbidden-action violation evidence was recorded."
        score = 0
    elif _has_any(evidence_text, clean_markers):
        pass_fail = "pass"
        observed = "result evidence explicitly records forbidden-action compliance."
        score = 1
    else:
        pass_fail = "incomplete"
        observed = "result evidence does not explicitly address forbidden actions."
        score = "not_scored"

    artifact = _base_artifact(
        work_order=work_order,
        eval_type=FORBIDDEN_ACTION_COMPLIANCE,
        expected_behavior="Recorded result evidence addresses the Work Order forbidden_actions and proves no listed forbidden action occurred.",
        observed_behavior=observed,
        pass_fail=pass_fail,
        evidence=[str((result_metadata or {}).get("raw_output_ref", "evidence_unavailable"))],
        score=score,
    )
    path = _write_eval(artifact, storage_root=storage_root)
    return artifact, path


def create_target_repo_mutation_eval(
    *,
    work_order: dict[str, Any],
    before_snapshot: dict[str, str] | None = None,
    after_snapshot: dict[str, str] | None = None,
    changed_files: list[Any] | tuple[Any, ...] | None = None,
    approval_evidence: dict[str, Any] | None = None,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    """Evaluate target mutation only from explicit snapshot evidence."""
    if work_order.get("approval_mode") == "approval_required":
        explicit_changes = (
            _normalize_changed_files(changed_files)
            if changed_files is not None
            else _changed_files_from_snapshots(before_snapshot, after_snapshot)
        )
        loaded_approval, approval_path = (
            (
                approval_evidence,
                _approval_path(
                    str(work_order.get("work_order_id", "unknown")),
                    storage_root=storage_root,
                ),
            )
            if approval_evidence is not None
            else load_approval_evidence(work_order, storage_root=storage_root)
        )
        pass_fail, observed, score, evidence = _evaluate_approved_mutation(
            approval=loaded_approval,
            changed_files=explicit_changes,
        )
        artifact = _base_artifact(
            work_order=work_order,
            eval_type=TARGET_REPO_MUTATION,
            expected_behavior="approval_required target mutation passes only with valid approval evidence and explicit changed-file or before/after evidence wholly within approved_files.",
            observed_behavior=observed,
            pass_fail=pass_fail,
            evidence=[
                str(approval_path) if approval_path.is_file() else "approval_evidence_unavailable",
                *evidence,
            ],
            score=score,
        )
        path = _write_eval(artifact, storage_root=storage_root)
        return artifact, path

    if before_snapshot is None or after_snapshot is None:
        pass_fail = "incomplete"
        observed = "target repo snapshot evidence_unavailable; live target_path was not inspected."
        evidence = ["evidence_unavailable"]
        score: int | str = "not_scored"
    elif before_snapshot == after_snapshot:
        pass_fail = "pass"
        observed = "explicit before/after snapshot evidence is unchanged."
        evidence = ["before_snapshot", "after_snapshot"]
        score = 1
    else:
        pass_fail = "fail"
        changed = sorted(set(before_snapshot) ^ set(after_snapshot))
        changed.extend(
            sorted(
                path
                for path in set(before_snapshot).intersection(after_snapshot)
                if before_snapshot[path] != after_snapshot[path]
            )
        )
        observed = f"explicit before/after snapshot evidence changed: {', '.join(changed)}."
        evidence = ["before_snapshot", "after_snapshot"]
        score = 0

    artifact = _base_artifact(
        work_order=work_order,
        eval_type=TARGET_REPO_MUTATION,
        expected_behavior="Target repo mutation is evaluated only from explicit before/after snapshot evidence, never by inspecting live target_path by default.",
        observed_behavior=observed,
        pass_fail=pass_fail,
        evidence=evidence,
        score=score,
    )
    path = _write_eval(artifact, storage_root=storage_root)
    return artifact, path


REQUIRED_REPORT_TERMS = (
    "Objective",
    "Project Name",
    "Target Path",
    "Approval Mode",
    "Risk Level",
    "Scope Include",
    "Scope Exclude",
    "Rendered Packet Paths",
    "Raw Result Reference",
    "Structured Result Metadata",
    "Files Inspected",
    "Files Changed",
    "Commands And Tests",
    "Risks And Warnings",
    "Eval Artifact Summary",
    "Approved Mutation Compliance",
    "Next Recommended Work Order",
    "Remaining Gaps",
    "Proven",
    "Failed",
    "Incomplete / Unavailable",
    "Sequential Execution Readiness",
    "Next Action Decision",
    "Ready-To-Copy Next Prompt",
)


def create_result_report_completeness_eval(
    *,
    work_order: dict[str, Any],
    report_path: Path,
    report_text: str,
    result_exists: bool,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    missing = [term for term in REQUIRED_REPORT_TERMS if term not in report_text]
    if missing or not result_exists:
        pass_fail = "fail"
        observed = (
            f"report missing required evidence: {', '.join(missing) or 'raw result reference'}."
        )
        score: int | str = 0
    else:
        pass_fail = "pass"
        observed = "report includes required sections and raw result reference."
        score = 1

    artifact = _base_artifact(
        work_order=work_order,
        eval_type=RESULT_REPORT_COMPLETENESS,
        expected_behavior="Report includes required sections, raw result reference, eval summary, and remaining gaps.",
        observed_behavior=observed,
        pass_fail=pass_fail,
        evidence=[str(report_path)],
        score=score,
    )
    path = _write_eval(artifact, storage_root=storage_root)
    return artifact, path


def create_next_work_order_recommendation_eval(
    *,
    work_order: dict[str, Any],
    recommendation: str | None,
    evidence_ref: str,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any], Path]:
    text = (recommendation or "").strip()
    lowered = text.lower()
    if not text or lowered == "unavailable":
        pass_fail = "incomplete"
        observed = "next Work Order recommendation unavailable."
        score: int | str = "not_scored"
    elif _has_any(lowered, ("autonomous", "mutate everything", "unbounded", "without approval")):
        pass_fail = "fail"
        observed = "next Work Order recommendation is unbounded or unsafe."
        score = 0
    elif _has_any(lowered, ("objective", "risk", "approval", "validation", "non-goal")):
        pass_fail = "pass"
        observed = "bounded next Work Order recommendation is recorded."
        score = 1
    else:
        pass_fail = "incomplete"
        observed = "recommendation exists but lacks bounded objective, risk, approval, validation, or non-goal details."
        score = "not_scored"

    artifact = _base_artifact(
        work_order=work_order,
        eval_type=NEXT_WORK_ORDER_RECOMMENDATION,
        expected_behavior="Result or report records a bounded follow-up Work Order recommendation or explicitly marks it unavailable.",
        observed_behavior=observed,
        pass_fail=pass_fail,
        evidence=[evidence_ref],
        score=score,
    )
    path = _write_eval(artifact, storage_root=storage_root)
    return artifact, path


def create_handoff_prompt_evals(
    *,
    work_order: dict[str, Any],
    prompt_text: str,
    readiness: str,
    can_continue: bool,
    report_path: Path,
    storage_root: Path | str | None = None,
) -> tuple[list[dict[str, Any]], list[Path]]:
    """Write deterministic Handoff Packet eval artifacts."""
    results = evaluate_handoff_prompt(
        prompt_text,
        readiness=readiness,
        can_continue=can_continue,
        target_repo_required=bool(str(work_order.get("target_path", "")).strip()),
    )
    expected = {
        HANDOFF_PROMPT_COMPLETENESS: "Handoff prompt includes required context and safety fields.",
        HANDOFF_CONSTRAINT_PRESERVATION: "Handoff prompt preserves Work Order authority constraints.",
        HANDOFF_EXECUTION_READINESS: "READY reports include execution prompts; HOLD/FAIL reports include decision-only recovery or hold prompts.",
        HANDOFF_FRESH_SESSION_SUFFICIENCY: "Handoff prompt is usable without prior chat context and requires a Handoff Understanding Report.",
        HANDOFF_RECOVERY_MODE_COMPLETENESS: "Recovery handoffs include recovery_decision fields and do not blend decision with execution.",
        HANDOFF_CURRENT_STATE_COMPLETENESS: "Recovery handoffs model current local commit, branch, staged/index, no-push, and forbidden-file state.",
        HANDOFF_RECOVERY_OPTION_CLARITY: "Recovery handoffs list options and recommend the safest option.",
        HANDOFF_OPERATOR_DECISION_GATE: "Recovery handoffs require an operator decision before mutation or index changes.",
        HANDOFF_PATH_INTEGRITY: "Handoff prompt preserves valid Dream Studio artifact path separators.",
        HANDOFF_INDEX_STATE_REQUIREMENTS: "Recovery handoffs with git staging require explicit index-state evidence.",
        HANDOFF_HOOK_BEHAVIOR_AWARENESS: "Recovery handoffs account for potentially mutating hook and lint-staged behavior.",
        HANDOFF_PUSH_EXECUTION_COMPLETENESS: "Push execution handoffs include push target, forbidden target, before/after evidence, command, readiness, verdict, and report sections.",
        HANDOFF_PUSH_TARGET_CONSTRAINTS: "Push execution handoffs constrain remote, branch, command, force-push, tags, other branches, other remotes, deletes, and extra refspecs.",
        HANDOFF_PUSH_EVIDENCE_REQUIREMENTS: "Push execution handoffs require approval, fetch, HEAD, ahead/behind, index, before-push, after-push, and no-forbidden-action evidence.",
    }
    artifacts: list[dict[str, Any]] = []
    paths: list[Path] = []
    for eval_type in sorted(HANDOFF_EVAL_TYPES):
        result = results[eval_type]
        artifact = _base_artifact(
            work_order=work_order,
            eval_type=eval_type,
            expected_behavior=expected.get(
                eval_type, "Handoff prompt eval passes deterministically."
            ),
            observed_behavior=str(result["observed_behavior"]),
            pass_fail=str(result["pass_fail"]),
            evidence=[str(report_path), *[str(item) for item in result.get("evidence", [])]],
            score=result["score"],
        )
        path = _write_eval(artifact, storage_root=storage_root)
        artifacts.append(artifact)
        paths.append(path)
    return artifacts, paths


_DECISION_REQUEST_REQUIRED_FIELDS = (
    "decision_request_id",
    "work_order_id",
    "phase_type",
    "required_decision_taxonomy",
    "status",
    "question",
    "allowed_decisions",
    "recommended_decision",
    "risk_summary",
    "required_evidence",
    "requires_reason",
    "created_at",
)

_OPERATOR_DECISION_REQUIRED_FIELDS = (
    "decision_request_id",
    "work_order_id",
    "decision",
    "decided_by",
    "decided_at",
    "reason",
    "approved_next_handoff_type",
    "constraints",
    "privacy_export_classification",
)


def _missing_fields(data: dict[str, Any] | None, fields: tuple[str, ...]) -> list[str]:
    if data is None:
        return list(fields)
    return [field for field in fields if data.get(field) in (None, "", [])]


def create_operator_decision_evals(
    *,
    work_order: dict[str, Any],
    decision_required: bool,
    execution_handoff_requested: bool,
    decision_request: dict[str, Any] | None,
    decision_request_path: Path,
    operator_decision: dict[str, Any] | None,
    operator_decision_path: Path,
    storage_root: Path | str | None = None,
) -> tuple[list[dict[str, Any]], list[Path]]:
    """Write deterministic evals for file-backed operator decision gating."""
    artifacts: list[dict[str, Any]] = []
    paths: list[Path] = []

    if not decision_required:
        request_status = "pass"
        request_observed = "operator decision request is not required for this report state."
        request_score: int | str = 1
        request_evidence = ["decision_not_required"]
    elif decision_request is None:
        request_status = "fail"
        request_observed = "operator decision is required, but request.json is unavailable."
        request_score = 0
        request_evidence = [str(decision_request_path)]
    elif decision_request.get("_invalid"):
        request_status = "fail"
        request_observed = str(decision_request["_invalid"])
        request_score = 0
        request_evidence = [str(decision_request_path)]
    else:
        missing = _missing_fields(decision_request, _DECISION_REQUEST_REQUIRED_FIELDS)
        allowed = decision_request.get("allowed_decisions")
        recommended = decision_request.get("recommended_decision")
        if not isinstance(allowed, list) or recommended not in allowed:
            missing.append("allowed_decisions/recommended_decision")
        request_status = "pass" if not missing else "fail"
        request_observed = (
            "operator decision request includes required file-backed fields."
            if request_status == "pass"
            else f"operator decision request missing fields: {', '.join(missing)}."
        )
        request_score = 1 if request_status == "pass" else 0
        request_evidence = [str(decision_request_path), *missing]

    request_artifact = _base_artifact(
        work_order=work_order,
        eval_type=OPERATOR_DECISION_REQUEST_COMPLETENESS,
        expected_behavior="When an operator decision is required, request.json exists and includes the decision taxonomy, question, recommendation, risk, evidence, and reason requirement.",
        observed_behavior=request_observed,
        pass_fail=request_status,
        evidence=request_evidence,
        score=request_score,
    )
    request_path = _write_eval(request_artifact, storage_root=storage_root)
    artifacts.append(request_artifact)
    paths.append(request_path)

    if not decision_required:
        validity_status = "pass"
        validity_observed = "operator decision is not required for this report state."
        validity_score: int | str = 1
        validity_evidence = ["decision_not_required"]
    elif decision_request is None:
        validity_status = "incomplete"
        validity_observed = "operator decision validity cannot be checked without request.json."
        validity_score = "not_scored"
        validity_evidence = [str(decision_request_path)]
    elif operator_decision is None:
        validity_status = "incomplete"
        validity_observed = "operator_decision.json has not been recorded yet."
        validity_score = "not_scored"
        validity_evidence = [str(operator_decision_path)]
    elif operator_decision.get("_invalid"):
        validity_status = "fail"
        validity_observed = str(operator_decision["_invalid"])
        validity_score = 0
        validity_evidence = [str(operator_decision_path)]
    else:
        allowed = tuple(str(item) for item in decision_request.get("allowed_decisions", []))
        selected = str(operator_decision.get("decision", ""))
        missing_decision = _missing_fields(operator_decision, _OPERATOR_DECISION_REQUIRED_FIELDS)
        if selected not in allowed:
            missing_decision.append("decision")
        validity_status = "pass" if not missing_decision else "fail"
        validity_observed = (
            "operator decision is recorded and belongs to the requested decision taxonomy."
            if validity_status == "pass"
            else f"operator decision invalid or missing fields: {', '.join(missing_decision)}."
        )
        validity_score = 1 if validity_status == "pass" else 0
        validity_evidence = [str(operator_decision_path), *missing_decision]

    validity_artifact = _base_artifact(
        work_order=work_order,
        eval_type=OPERATOR_DECISION_VALIDITY,
        expected_behavior="Recorded operator decision must belong to the request's allowed_decisions and include required fields.",
        observed_behavior=validity_observed,
        pass_fail=validity_status,
        evidence=validity_evidence,
        score=validity_score,
    )
    validity_path = _write_eval(validity_artifact, storage_root=storage_root)
    artifacts.append(validity_artifact)
    paths.append(validity_path)

    if not execution_handoff_requested:
        execution_status = "pass"
        execution_observed = "execution handoff is not requested for this report state."
        execution_score: int | str = 1
        execution_evidence = ["execution_handoff_not_requested"]
    elif decision_required and operator_decision is None:
        execution_status = "fail"
        execution_observed = "execution handoff is blocked until operator_decision.json exists."
        execution_score = 0
        execution_evidence = [str(decision_request_path), str(operator_decision_path)]
    elif decision_required and operator_decision and validity_status != "pass":
        execution_status = "fail"
        execution_observed = "execution handoff is blocked by invalid operator_decision.json."
        execution_score = 0
        execution_evidence = [str(operator_decision_path)]
    else:
        execution_status = "pass"
        execution_observed = "operator decision gate permits the current handoff state."
        execution_score = 1
        execution_evidence = [str(operator_decision_path)]

    execution_artifact = _base_artifact(
        work_order=work_order,
        eval_type=OPERATOR_DECISION_REQUIRED_BEFORE_EXECUTION,
        expected_behavior="Execution handoffs that require an operator decision must not be generated until a valid file-backed operator_decision.json exists.",
        observed_behavior=execution_observed,
        pass_fail=execution_status,
        evidence=execution_evidence,
        score=execution_score,
    )
    execution_path = _write_eval(execution_artifact, storage_root=storage_root)
    artifacts.append(execution_artifact)
    paths.append(execution_path)

    requires_reason = bool((decision_request or {}).get("requires_reason", False))
    if not requires_reason:
        reason_status = "pass"
        reason_observed = "operator decision reason is not required for this request."
        reason_score: int | str = 1
        reason_evidence = ["reason_not_required"]
    elif operator_decision is None:
        reason_status = "incomplete"
        reason_observed = "operator decision reason unavailable because decision is not recorded."
        reason_score = "not_scored"
        reason_evidence = [str(operator_decision_path)]
    elif str(operator_decision.get("reason", "")).strip():
        reason_status = "pass"
        reason_observed = "operator decision includes a reason."
        reason_score = 1
        reason_evidence = [str(operator_decision_path)]
    else:
        reason_status = "fail"
        reason_observed = "operator decision reason is required but empty."
        reason_score = 0
        reason_evidence = [str(operator_decision_path)]

    reason_artifact = _base_artifact(
        work_order=work_order,
        eval_type=OPERATOR_DECISION_REASON_COMPLETENESS,
        expected_behavior="When request.requires_reason is true, operator_decision.json must include a non-empty reason.",
        observed_behavior=reason_observed,
        pass_fail=reason_status,
        evidence=reason_evidence,
        score=reason_score,
    )
    reason_path = _write_eval(reason_artifact, storage_root=storage_root)
    artifacts.append(reason_artifact)
    paths.append(reason_path)

    return artifacts, paths
