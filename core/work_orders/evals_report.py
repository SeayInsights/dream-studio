"""Result-report completeness and next-work-order-recommendation evals.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/evals.py``. No logic
changes — extracted verbatim from the original module.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .evals_shared import (
    NEXT_WORK_ORDER_RECOMMENDATION,
    REQUIRED_REPORT_TERMS,
    RESULT_REPORT_COMPLETENESS,
    _base_artifact,
    _has_any,
    _write_eval,
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
