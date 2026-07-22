"""Operator-decision-gate evals for file-backed Work Orders.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/evals.py``. No logic
changes — extracted verbatim from the original module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .evals_shared import (
    OPERATOR_DECISION_REASON_COMPLETENESS,
    OPERATOR_DECISION_REQUEST_COMPLETENESS,
    OPERATOR_DECISION_REQUIRED_BEFORE_EXECUTION,
    OPERATOR_DECISION_VALIDITY,
    _base_artifact,
    _write_eval,
)

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
