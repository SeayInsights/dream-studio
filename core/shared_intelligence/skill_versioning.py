"""Derived skill/workflow/hook version evaluation policy.

This module evaluates hardening candidates that already live in SQLite
authority. It never promotes, rewrites, or executes a component update.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import sqlite3
from typing import Any

from core.shared_intelligence.authority import require_shared_intelligence_tables

VERSIONED_COMPONENT_TYPES: frozenset[str] = frozenset({"skill", "workflow", "hook"})
ALLOWED_VERSION_EVALUATION_STATUSES: frozenset[str] = frozenset(
    {
        "promotion_ready",
        "needs_version",
        "needs_validation_plan",
        "needs_validation",
        "needs_rollback_plan",
        "needs_more_validation",
        "manual_review_required",
        "not_ready",
        "already_promoted",
    }
)
_HIGH_RISK_SEVERITIES: frozenset[str] = frozenset({"high", "critical"})


def skill_version_evaluation_report(
    conn: sqlite3.Connection,
    *,
    component_type: str | None = None,
    component_id: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return a non-executing readiness view for versioned hardening candidates."""

    require_shared_intelligence_tables(conn)
    candidates = _versioned_candidates(
        conn,
        component_type=component_type,
        component_id=component_id,
        limit=limit,
    )
    evaluations = [skill_version_evaluation_policy(candidate) for candidate in candidates]
    status_counts = Counter(evaluation["evaluation_status"] for evaluation in evaluations)
    type_counts = Counter(evaluation["component_type"] for evaluation in evaluations)

    return _with_authority(
        "shared_intelligence_skill_version_evaluation_report",
        {
            "source_tables": ["hardening_candidate_records", "learning_event_records"],
            "versioned_component_types": sorted(VERSIONED_COMPONENT_TYPES),
            "candidate_count": len(evaluations),
            "component_type_counts": dict(sorted(type_counts.items())),
            "evaluation_status_counts": dict(sorted(status_counts.items())),
            "ready_for_operator_approval": [
                item for item in evaluations if item["evaluation_status"] == "promotion_ready"
            ],
            "manual_review_required": [
                item
                for item in evaluations
                if item["evaluation_status"] == "manual_review_required"
            ],
            "evaluations": evaluations,
            "promotion_execution_authorized": False,
            "empty_state": (
                "No skill, workflow, or hook hardening candidates are ready for version evaluation."
                if not evaluations
                else None
            ),
        },
    )


def skill_version_evaluation_policy(candidate: dict[str, Any]) -> dict[str, Any]:
    """Evaluate a single hardening candidate without authorizing promotion."""

    component_type = str(candidate.get("component_type") or "")
    status = str(candidate.get("status") or "")
    recurrence_check = candidate.get("recurrence_check") or {}
    validation_plan = candidate.get("validation_plan") or []
    validation_refs = list(recurrence_check.get("validation_refs") or [])
    recurrence_event_count = int(recurrence_check.get("recurrence_event_count") or 0)
    current_version = candidate.get("current_version")
    proposed_version = candidate.get("proposed_version")
    rollback_plan_present = bool(str(candidate.get("rollback_plan") or "").strip())
    version_change_required = _version_change_required(current_version, proposed_version)
    risk_level = _risk_level(candidate, recurrence_event_count)

    evaluation_status, reason, proposed_action = _evaluation_outcome(
        candidate,
        component_type=component_type,
        status=status,
        validation_plan=validation_plan,
        validation_refs=validation_refs,
        rollback_plan_present=rollback_plan_present,
        version_change_required=version_change_required,
    )

    return {
        "candidate_id": candidate["candidate_id"],
        "learning_event_id": candidate.get("learning_event_id"),
        "component_type": component_type,
        "component_id": candidate["component_id"],
        "current_version": current_version,
        "proposed_version": proposed_version,
        "version_change_required": version_change_required,
        "hardening_type": candidate["hardening_type"],
        "candidate_status": status,
        "evaluation_status": evaluation_status,
        "proposed_action": proposed_action,
        "reason": reason,
        "risk_level": risk_level,
        "validation_plan": validation_plan,
        "validation_refs": validation_refs,
        "validation_summary": recurrence_check.get("validation_summary"),
        "rollback_plan_present": rollback_plan_present,
        "recurrence_event_count": recurrence_event_count,
        "recurrence_detected": recurrence_event_count > 1,
        "requires_operator_approval": evaluation_status == "promotion_ready"
        or risk_level in {"high", "critical"},
        "requires_future_work_order": evaluation_status
        in {
            "promotion_ready",
            "needs_version",
            "needs_validation_plan",
            "needs_validation",
            "needs_rollback_plan",
            "needs_more_validation",
            "manual_review_required",
        },
        "promotion_execution_authorized": False,
        "source_refs": candidate.get("source_refs", []),
        "evidence_refs": candidate.get("evidence_refs", []),
        "learning_event": {
            "event_class": candidate.get("learning_event_class"),
            "severity": candidate.get("learning_severity"),
            "promotion_status": candidate.get("learning_promotion_status"),
            "summary": candidate.get("learning_summary"),
        },
    }


def validate_skill_version_evaluation_report(report: dict[str, Any]) -> list[str]:
    """Validate that a skill version evaluation report remains advisory only."""

    errors: list[str] = []
    if report.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if report.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if report.get("routing_authority") is not False:
        errors.append("routing_authority must be false")
    if report.get("promotion_execution_authorized") is not False:
        errors.append("promotion_execution_authorized must be false")
    if "hardening_candidate_records" not in report.get("source_tables", []):
        errors.append("hardening_candidate_records must be a source table")
    for evaluation in report.get("evaluations", []):
        if evaluation.get("evaluation_status") not in ALLOWED_VERSION_EVALUATION_STATUSES:
            errors.append(f"unsupported evaluation status: {evaluation.get('evaluation_status')}")
        if evaluation.get("promotion_execution_authorized") is not False:
            errors.append(
                f"candidate {evaluation.get('candidate_id')} authorizes promotion execution"
            )
    return errors


def _versioned_candidates(
    conn: sqlite3.Connection,
    *,
    component_type: str | None,
    component_id: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    clauses = ["hc.component_type IN (?, ?, ?)"]
    params: list[Any] = sorted(VERSIONED_COMPONENT_TYPES)
    if component_type is not None:
        clauses.append("hc.component_type = ?")
        params.append(component_type)
    if component_id is not None:
        clauses.append("hc.component_id = ?")
        params.append(component_id)
    params.append(max(1, int(limit)))

    rows = conn.execute(
        f"""
        SELECT
            hc.candidate_id,
            hc.learning_event_id,
            hc.component_type,
            hc.component_id,
            hc.current_version,
            hc.proposed_version,
            hc.hardening_type,
            hc.status,
            hc.validation_plan_json,
            hc.recurrence_check_json,
            hc.rollback_plan,
            hc.source_refs_json,
            hc.evidence_refs_json,
            hc.created_at,
            hc.updated_at,
            le.event_class AS learning_event_class,
            le.severity AS learning_severity,
            le.promotion_status AS learning_promotion_status,
            le.summary AS learning_summary
        FROM hardening_candidate_records hc
        LEFT JOIN learning_event_records le
          ON le.learning_event_id = hc.learning_event_id
        WHERE {" AND ".join(clauses)}
        ORDER BY hc.updated_at DESC, hc.candidate_id DESC
        LIMIT ?
        """,
        tuple(params),
    ).fetchall()
    return [_decode_candidate(row) for row in rows]


def _evaluation_outcome(
    candidate: dict[str, Any],
    *,
    component_type: str,
    status: str,
    validation_plan: list[Any],
    validation_refs: list[Any],
    rollback_plan_present: bool,
    version_change_required: bool,
) -> tuple[str, str, str]:
    if component_type not in VERSIONED_COMPONENT_TYPES:
        return (
            "manual_review_required",
            "Only skills, workflows, and hooks are handled by this evaluation policy.",
            "Route to component-specific manual review.",
        )
    if status in {"rejected", "deferred"}:
        return (
            "not_ready",
            f"Candidate status is {status}.",
            "Do not promote unless a future Work Order reopens the candidate.",
        )
    if status == "promoted":
        return (
            "already_promoted",
            "Candidate already records promoted status.",
            "Track recurrence and preserve rollback evidence.",
        )
    if not candidate.get("proposed_version") or not version_change_required:
        return (
            "needs_version",
            "Candidate needs an explicit proposed version different from the current version.",
            "Create or correct the proposed component version.",
        )
    if not validation_plan:
        return (
            "needs_validation_plan",
            "Candidate has no validation plan.",
            "Add focused evaluation criteria before validation.",
        )
    if not rollback_plan_present:
        return (
            "needs_rollback_plan",
            "Candidate has no rollback plan.",
            "Add rollback instructions before promotion review.",
        )
    if not validation_refs:
        return (
            "needs_validation",
            "Candidate has not recorded validation evidence.",
            "Run focused evaluation and record validation refs.",
        )
    if status != "validated":
        return (
            "needs_more_validation",
            f"Candidate status is {status}, not validated.",
            "Advance through rehearsal or validation before promotion review.",
        )
    return (
        "promotion_ready",
        "Candidate has a version change, validation evidence, and rollback plan.",
        "Create an operator-approved promotion Work Order; do not auto-promote.",
    )


def _version_change_required(current_version: Any, proposed_version: Any) -> bool:
    proposed = str(proposed_version or "").strip()
    current = str(current_version or "").strip()
    return bool(proposed) and proposed != current


def _risk_level(candidate: dict[str, Any], recurrence_event_count: int) -> str:
    severity = str(candidate.get("learning_severity") or "").lower()
    if severity == "critical":
        return "critical"
    if candidate.get("component_type") == "hook" or severity in _HIGH_RISK_SEVERITIES:
        return "high"
    if recurrence_event_count > 1 or candidate.get("component_type") == "workflow":
        return "medium"
    return "low"


def _decode_candidate(row: sqlite3.Row) -> dict[str, Any]:
    candidate = dict(row)
    candidate["validation_plan"] = _loads(candidate.pop("validation_plan_json"), [])
    candidate["recurrence_check"] = _loads(candidate.pop("recurrence_check_json"), {})
    candidate["source_refs"] = _loads(candidate.pop("source_refs_json"), [])
    candidate["evidence_refs"] = _loads(candidate.pop("evidence_refs_json"), [])
    return candidate


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _with_authority(model_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_name": model_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        **payload,
    }
