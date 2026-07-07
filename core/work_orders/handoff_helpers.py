"""WO-SPLIT-HANDOFF: handoff helpers module."""

from __future__ import annotations
import re
from typing import Any

from .handoff_constants import (
    FAIL,
    HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
    HANDOFF_TYPE_COMMIT_EXECUTION,
    HANDOFF_TYPE_HOLD_REVIEW,
    HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER,
    HANDOFF_TYPE_RECOVERY_DECISION,
    HOLD,
    PHASE_TYPE_APPROVED_MUTATION,
    PHASE_TYPE_COMMIT_PLANNING,
    PHASE_TYPE_NORMAL_NEXT_WORK_ORDER,
    PHASE_TYPE_PRODUCT_CLOSEOUT,
    PHASE_TYPE_PUSH_PLANNING,
    PHASE_TYPE_RECOVERY_DECISION,
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


def _next_recommendation(result_metadata: dict[str, Any] | None) -> str:
    if not result_metadata:
        return "unavailable"
    return str(result_metadata.get("next_work_order_recommendation") or "unavailable")


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


def _next_mode(work_order: dict[str, Any], recommendation: str) -> str:
    return _extract_prefixed(recommendation, "Approval") or str(
        work_order.get("approval_mode", "unavailable")
    )


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


def _body_missing(value: str, *, allow_unknown: bool = False) -> bool:
    text = value.strip()
    if not text:
        return True
    lowered = text.lower()
    if allow_unknown and lowered == "unknown":
        return False
    return lowered in {"unavailable", "- unavailable"}


def _nested_get(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current
