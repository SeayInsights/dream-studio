"""File-backed operator decision artifacts for Work Orders.

Decision artifacts are local evidence only. They do not execute selected work,
inspect target repositories, or open Dream Studio runtime state.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from compat import UTC

from .handoff import DECISION_TAXONOMIES
from .models import WorkOrderError
from .storage import load_work_order, work_order_dir

DECISION_REQUEST_JSON = "request.json"
OPERATOR_DECISION_JSON = "operator_decision.json"
PENDING_OPERATOR_DECISION = "pending_operator_decision"
PRIVACY_EXPORT_CLASSIFICATION = "local_only"


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def decisions_dir(work_order_id: str, *, storage_root: Path | str | None = None) -> Path:
    return work_order_dir(work_order_id, storage_root=storage_root) / "decisions"


def decision_request_path(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> Path:
    return decisions_dir(work_order_id, storage_root=storage_root) / DECISION_REQUEST_JSON


def operator_decision_path(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> Path:
    return decisions_dir(work_order_id, storage_root=storage_root) / OPERATOR_DECISION_JSON


def allowed_decisions_for_phase(phase_type: str) -> tuple[str, ...]:
    allowed = DECISION_TAXONOMIES.get(str(phase_type))
    if not allowed:
        raise WorkOrderError(f"Unknown phase_type for operator decision: {phase_type}")
    return allowed


def _set_decision_artifact(
    work_order_id: str,
    kind: str,
    payload: dict[str, Any],
    *,
    storage_root: Path | str | None = None,
) -> None:
    """WO-FILESDB-C4: persist a decision artifact into the authority-free packet store.

    Decisions are file-backed PACKET-system artifacts (created in the report flow), not
    Dream Studio authority state — stored in packets.db (kind=decision_request /
    operator_decision), never in loose decisions/*.json files and never in studio.db.
    """
    from core.work_orders.packet_store import set_packet_artifact

    set_packet_artifact(
        work_order_id,
        kind,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        storage_root=storage_root,
    )


def _load_decision_artifact(
    work_order_id: str,
    kind: str,
    label: str,
    *,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any] | None, Path]:
    """Load a decision artifact from the packet store (WO-FILESDB-C4).

    The returned Path is the logical location (used as an evidence ref); the content
    comes from packets.db.
    """
    from core.work_orders.packet_store import get_packet_artifact

    path = (
        decision_request_path(work_order_id, storage_root=storage_root)
        if kind == "decision_request"
        else operator_decision_path(work_order_id, storage_root=storage_root)
    )
    content = get_packet_artifact(work_order_id, kind, storage_root=storage_root)
    if content is None:
        return None, path
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return {"_invalid": f"{label} could not be parsed."}, path
    if not isinstance(data, dict):
        return {"_invalid": f"{label} must be a mapping."}, path
    return data, path


def load_decision_request(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any] | None, Path]:
    return _load_decision_artifact(
        work_order_id, "decision_request", "decision request", storage_root=storage_root
    )


def load_operator_decision(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> tuple[dict[str, Any] | None, Path]:
    return _load_decision_artifact(
        work_order_id, "operator_decision", "operator decision", storage_root=storage_root
    )


def create_decision_request(
    work_order_id: str,
    *,
    phase_type: str,
    question: str,
    recommended_decision: str,
    risk_summary: str = "operator decision required before execution handoff",
    required_evidence: list[str] | None = None,
    requires_reason: bool = True,
    storage_root: Path | str | None = None,
) -> dict[str, Any]:
    """Create or replace the decision request artifact for a Work Order."""
    work_order, _ = load_work_order(work_order_id, storage_root=storage_root)
    canonical_id = str(work_order["work_order_id"])
    allowed = allowed_decisions_for_phase(phase_type)
    if recommended_decision not in allowed:
        raise WorkOrderError(
            f"recommended decision {recommended_decision} is not allowed for {phase_type}"
        )
    if not question.strip():
        raise WorkOrderError("decision question is required.")

    request = {
        "decision_request_id": f"{canonical_id}.{phase_type}.decision",
        "work_order_id": canonical_id,
        "phase_type": phase_type,
        "required_decision_taxonomy": list(allowed),
        "status": PENDING_OPERATOR_DECISION,
        "question": question.strip(),
        "allowed_decisions": list(allowed),
        "recommended_decision": recommended_decision,
        "risk_summary": risk_summary.strip() or "operator decision required",
        "required_evidence": required_evidence
        or [
            "source Work Order report",
            "current readiness and next action decision",
            "operator-selected decision reason",
        ],
        "requires_reason": bool(requires_reason),
        "created_at": _now(),
        "privacy_export_classification": PRIVACY_EXPORT_CLASSIFICATION,
    }
    _set_decision_artifact(canonical_id, "decision_request", request, storage_root=storage_root)
    return request


def _handoff_type_for_decision(decision: str) -> str:
    if decision in {"LINT_REMEDIATION", "NO_VERIFY_CONTINUATION", "ROLLBACK"}:
        return "recovery_execution"
    if decision == "UNSTAGE_AND_HOLD":
        return "hold_review"
    if decision in {"PUSH_READY_WITH_APPROVAL", "REQUEST_HUMAN_APPROVAL"}:
        return "approved_mutation_execution"
    if decision == "READY_FOR_COMMIT_PLANNING":
        return "commit_execution"
    if decision in {
        "RUN_BROADER_VALIDATION_FIRST",
        "READY_FOR_HUMAN_REVIEW",
        "READY_FOR_COMMIT_PLANNING",
        "MUTATION_COMPLETE",
        "CONTINUE_TO_NEXT_WORK_ORDER",
    }:
        return "normal_next_work_order"
    return "hold_review"


def record_operator_decision(
    work_order_id: str,
    *,
    decision: str,
    reason: str,
    decided_by: str = "operator",
    constraints: list[str] | None = None,
    storage_root: Path | str | None = None,
) -> dict[str, Any]:
    """Record the operator's decision after validating it against the request."""
    request, request_path = load_decision_request(work_order_id, storage_root=storage_root)
    if request is None:
        raise WorkOrderError(f"Decision request not found: {request_path}")
    if request.get("_invalid"):
        raise WorkOrderError(str(request["_invalid"]))
    allowed = tuple(str(item) for item in request.get("allowed_decisions", []))
    if decision not in allowed:
        raise WorkOrderError(f"decision {decision} is not allowed for {request.get('phase_type')}")
    if request.get("requires_reason", False) and not reason.strip():
        raise WorkOrderError("decision reason is required.")
    if not decided_by.strip():
        raise WorkOrderError("decided_by is required.")

    artifact = {
        "decision_request_id": request["decision_request_id"],
        "work_order_id": request["work_order_id"],
        "decision": decision,
        "decided_by": decided_by.strip(),
        "decided_at": _now(),
        "reason": reason.strip(),
        "approved_next_handoff_type": _handoff_type_for_decision(decision),
        "constraints": constraints
        or [
            "operator decision is file-backed evidence only",
            "operator decision does not execute work",
            "next handoff must preserve Work Order authority boundaries",
        ],
        "privacy_export_classification": PRIVACY_EXPORT_CLASSIFICATION,
    }
    _set_decision_artifact(work_order_id, "operator_decision", artifact, storage_root=storage_root)
    return artifact


def decision_status(
    work_order_id: str,
    *,
    storage_root: Path | str | None = None,
) -> dict[str, Any]:
    request, request_path = load_decision_request(work_order_id, storage_root=storage_root)
    decision, decision_path = load_operator_decision(work_order_id, storage_root=storage_root)
    status = "not_requested"
    if request is not None:
        status = "pending_operator_decision"
    if decision is not None:
        status = "decided"
    return {
        "work_order_id": work_order_id,
        "status": status,
        "decision_request_path": str(request_path),
        "operator_decision_path": str(decision_path),
        "decision_request": request,
        "operator_decision": decision,
    }
