"""Behavioral eval runner — deterministic event-trace scoring only (WO-N2).

Scoring: composite_score = event_score (100% deterministic, no LLM judge).
Pass threshold: composite_score >= case.minimum_pass_score

Events are read from case.fixture_events only. All eval cases in evals/ define
fixture_events — live canonical-session mode is not implemented. Passing a case
with fixture_events=None raises NotImplementedError so the gap is explicit rather
than silently scoring 0.0 with a misleading "canonical" run_mode label.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from core.eval.baseline import load_baseline, save_run_result
from core.eval.matcher import match_events
from core.eval.schema import EvalCase, EvalResult, MatchResult

logger = logging.getLogger(__name__)

# Default eval cases directory
EVALS_DIR = Path(__file__).parents[2] / "evals"


def load_eval_cases(evals_dir: Path | None = None) -> list[EvalCase]:
    """Load all eval cases from the evals/ directory."""
    directory = evals_dir or EVALS_DIR
    cases = []
    for json_path in sorted(directory.glob("eval_*.json")):
        try:
            cases.append(EvalCase.from_json(json_path))
        except Exception as exc:
            logger.warning("Failed to load eval case %s: %s", json_path, exc)
    return cases


class EvalRunner:
    """Deterministic behavioral eval runner.

    Scores eval cases by matching expected event patterns against fixture events
    (unit/regression tests) or recorded session events from the canonical-event
    substrate. Never invokes a live Claude session.
    """

    def __init__(
        self,
        evals_dir: Path | None = None,
        db_path: Path | None = None,
    ) -> None:
        self.evals_dir = evals_dir or EVALS_DIR
        self.db_path = db_path

    def run_case(self, case: EvalCase) -> EvalResult:
        """Run a single eval case and return the result."""
        start = time.monotonic()

        try:
            # ── 1. Get events ────────────────────────────────────────────────
            if case.fixture_events is None:
                raise NotImplementedError(
                    f"Live canonical-session eval mode is not implemented. "
                    f"Eval case '{case.eval_id}' must define fixture_events."
                )
            events = case.fixture_events

            # ── 2. Deterministic event matching (100% weight) ─────────────────
            match_result = match_events(case, events)
            event_score = match_result.score
            composite_score = round(event_score, 4)
            passed = composite_score >= case.minimum_pass_score

            # ── 3. Baseline check ─────────────────────────────────────────────
            baseline_data = load_baseline(case.eval_id, case.version, self.db_path)
            baseline_score = baseline_data["baseline_score"] if baseline_data else None

            _is_baseline, regression_flagged = save_run_result(
                case.eval_id,
                case.version,
                composite_score,
                passed,
                db_path=self.db_path,
            )

            elapsed = time.monotonic() - start
            logger.info(
                "eval %s: %s score=%.3f regression=%s elapsed=%.1fs",
                case.eval_id,
                "PASS" if passed else "FAIL",
                composite_score,
                regression_flagged,
                elapsed,
            )

            return EvalResult(
                eval_id=case.eval_id,
                version=case.version,
                passed=passed,
                composite_score=composite_score,
                event_score=event_score,
                match_result=match_result,
                regression_flagged=regression_flagged,
                baseline_score=baseline_score,
                run_mode="fixture",
            )

        except Exception as exc:
            logger.error("Eval %s failed with error: %s", case.eval_id, exc)
            elapsed = time.monotonic() - start
            return EvalResult(
                eval_id=case.eval_id,
                version=case.version,
                passed=False,
                composite_score=0.0,
                event_score=0.0,
                match_result=MatchResult(
                    score=0.0,
                    matched_required=0,
                    total_required=0,
                    negative_violations=[],
                    missing_events=[],
                    out_of_order=[],
                ),
                error=str(exc),
            )

    def run_all(self, skill_filter: str | None = None) -> list[EvalResult]:
        """Run all eval cases (optionally filtered by skill_id)."""
        cases = load_eval_cases(self.evals_dir)
        if skill_filter:
            cases = [c for c in cases if c.skill_id == skill_filter]

        results = []
        for case in cases:
            result = self.run_case(case)
            results.append(result)

        passed = sum(1 for r in results if r.passed)
        regressions = sum(1 for r in results if r.regression_flagged)
        logger.info(
            "Eval suite complete: %d/%d passed, %d regressions",
            passed,
            len(results),
            regressions,
        )
        return results


def format_results_report(results: list[EvalResult]) -> str:
    """Format eval results as a human-readable report."""
    lines = ["\n=== Behavioral Eval Report ==="]

    for result in results:
        status = "✓" if result.passed else "✗"
        reg = " [REGRESSION]" if result.regression_flagged else ""
        lines.append(f"  {status} {result.eval_id} — {result.score_display}{reg}")
        if not result.passed:
            mr = result.match_result
            if mr.missing_events:
                lines.append(f"      Missing events: {', '.join(mr.missing_events)}")
            if mr.negative_violations:
                lines.append(f"      Violations: {', '.join(mr.negative_violations)}")

    passed = sum(1 for r in results if r.passed)
    regressions = sum(1 for r in results if r.regression_flagged)
    lines.append(f"\nSummary: {passed}/{len(results)} passed")
    if regressions:
        lines.append(f"  ⚠  {regressions} regression(s) detected")
    return "\n".join(lines)
