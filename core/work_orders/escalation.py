"""Escalation ladder (WO-ESCALATION-LADDER).

When the DETERMINISTIC verifier/outcome-eval says NOT FIXED, the platform must
not silently re-close. Per AD-8 the deterministic layer owns the escalate
DECISION; the AI owns the retry CONTENT. This module provides the decision half:

  compute_not_fixed_signal(...) — pure predicate over three deterministic inputs:
    AC fail OR symptom persists OR grader high-confidence-not-fixed.
  not_fixed_for_work_order(...) — derives those inputs for a specific WO by
    re-running its outcome (symptom + executable ACs) and folding in an optional
    grader verdict.

Downstream tasks (T2–T5) consume the signal to: route the retry to Opus, require
an independent adversarial review before re-close, and cap retries before
escalating to the operator.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# A grader "not fixed" verdict only counts when the grader was confident. An
# unreviewable / low-signal grader must NOT by itself trip the ladder (precedent:
# WO-VERIFY-NOSUMMARY — empty grader output is unreviewable, not not-fixed).
GRADER_NOT_FIXED_CONFIDENCE_THRESHOLD = 0.7


def compute_not_fixed_signal(
    *,
    ac_failed: bool = False,
    symptom_persists: bool = False,
    grader_not_fixed: bool = False,
    grader_confidence: float = 0.0,
) -> dict[str, Any]:
    """Pure deterministic not-fixed predicate.

    Returns ``{"not_fixed": bool, "reasons": [...]}``. ``not_fixed`` is True when
    any deterministic signal fires: a failing executable AC, a persisting
    originating symptom, or a *high-confidence* grader not-fixed verdict.
    """
    reasons: list[str] = []
    if ac_failed:
        reasons.append("ac_fail")
    if symptom_persists:
        reasons.append("symptom_persists")
    if grader_not_fixed and grader_confidence >= GRADER_NOT_FIXED_CONFIDENCE_THRESHOLD:
        reasons.append("grader_high_confidence_not_fixed")
    return {"not_fixed": bool(reasons), "reasons": reasons}


def not_fixed_for_work_order(
    work_order_id: str,
    *,
    db_path: Path,
    source_root: Path | None = None,
    verdict: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute the not-fixed signal for a specific WO.

    Re-runs the WO outcome (originating symptom + executable ACs via the outcome
    eval) and folds in an optional independent-review ``verdict``. Returns the
    same shape as ``compute_not_fixed_signal`` plus ``work_order_id``.
    """
    from core.eval.runner import evaluate_wo_outcome

    outcome = evaluate_wo_outcome(work_order_id, db_path=Path(db_path), source_root=source_root)
    failures = outcome.get("failures", [])
    ac_failed = any(str(f).startswith("executable_ac") for f in failures)
    symptom_persists = any("originating_symptom" in str(f) for f in failures)

    grader_not_fixed = False
    grader_confidence = 0.0
    if verdict is not None:
        # A grader that ran and did NOT pass (and is not merely unreviewable) is a
        # not-fixed signal at its reported confidence.
        if not verdict.get("unreviewable") and verdict.get("passed") is False:
            grader_not_fixed = True
            grader_confidence = float(
                verdict.get("confidence", verdict.get("correctness_score", 0.0)) or 0.0
            )

    signal = compute_not_fixed_signal(
        ac_failed=ac_failed,
        symptom_persists=symptom_persists,
        grader_not_fixed=grader_not_fixed,
        grader_confidence=grader_confidence,
    )
    signal["work_order_id"] = work_order_id
    return signal
