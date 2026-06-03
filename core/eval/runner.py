"""Behavioral eval runner — orchestrates event capture, matching, judging, and scoring.

Phase 1 runs in "fixture" mode: eval cases provide pre-specified events and transcripts.
Phase 2 will add "live" mode: actual Claude API session with real event capture.

Scoring: composite = (event_weight × event_score) + (behavior_weight × behavior_score)
Pass threshold: composite_score >= case.minimum_pass_score

The runner is deterministic in fixture mode — same input produces same score.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

from core.eval.baseline import load_baseline, save_run_result
from core.eval.judge import estimate_judge_tokens, grade_behavior
from core.eval.matcher import match_events
from core.eval.schema import EvalCase, EvalResult, JudgeResult, MatchResult

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
    """Orchestrates behavioral eval runs.

    Phase 1: fixture mode only — eval cases provide pre-specified events/transcripts.
    Phase 2: live mode — calls Claude API, captures spool events, grades transcript.
    """

    def __init__(
        self,
        evals_dir: Path | None = None,
        api_key: str | None = None,
        db_path: Path | None = None,
        run_mode: str = "fixture",
    ) -> None:
        self.evals_dir = evals_dir or EVALS_DIR
        self.api_key = api_key
        self.db_path = db_path
        self.run_mode = run_mode  # "fixture" | "live"

    def run_case(self, case: EvalCase) -> EvalResult:
        """Run a single eval case and return the result."""
        start = time.monotonic()

        try:
            # ── 1. Get events and transcript ────────────────────────────────
            if self.run_mode == "fixture" or case.fixture_events is not None:
                events, transcript = self._get_fixture_data(case)
            else:
                events, transcript = self._run_live_session(case)

            # ── 2. Deterministic event matching (70% weight) ─────────────────
            match_result = match_events(case, events)
            event_score = match_result.score

            # ── 3. LLM behavior judge (30% weight) ───────────────────────────
            judge_result = grade_behavior(case, transcript, api_key=self.api_key)
            behavior_score = judge_result.effective_score

            # ── 4. Compute composite score ────────────────────────────────────
            total_weight = case.event_weight + case.behavior_weight
            composite_score = (
                case.event_weight * event_score + case.behavior_weight * behavior_score
            ) / total_weight
            composite_score = round(composite_score, 4)

            passed = composite_score >= case.minimum_pass_score

            # ── 5. Baseline check ─────────────────────────────────────────────
            baseline_data = load_baseline(case.eval_id, case.version, self.db_path)
            baseline_score = baseline_data["baseline_score"] if baseline_data else None

            _is_baseline, regression_flagged = save_run_result(
                case.eval_id,
                case.version,
                composite_score,
                passed,
                db_path=self.db_path,
            )

            # ── 6. Token cost ──────────────────────────────────────────────────
            tokens = judge_result.tokens_used
            if judge_result.skipped:
                tokens = estimate_judge_tokens(case, transcript)

            elapsed = time.monotonic() - start
            logger.info(
                "eval %s: %s composite=%.3f event=%.3f behavior=%.3f regression=%s elapsed=%.1fs",
                case.eval_id,
                "PASS" if passed else "FAIL",
                composite_score,
                event_score,
                behavior_score,
                regression_flagged,
                elapsed,
            )

            return EvalResult(
                eval_id=case.eval_id,
                version=case.version,
                passed=passed,
                composite_score=composite_score,
                event_score=event_score,
                behavior_score=behavior_score,
                match_result=match_result,
                judge_result=judge_result,
                regression_flagged=regression_flagged,
                baseline_score=baseline_score,
                run_mode=self.run_mode if case.fixture_events is None else "fixture",
                tokens_consumed=tokens,
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
                behavior_score=0.0,
                match_result=MatchResult(
                    score=0.0, matched_required=0, total_required=0,
                    negative_violations=[], missing_events=[], out_of_order=[]
                ),
                judge_result=JudgeResult(score=None, rationale=str(exc), skipped=True),
                error=str(exc),
            )

    def run_all(self, skill_filter: str | None = None) -> list[EvalResult]:
        """Run all eval cases (optionally filtered by skill_id)."""
        cases = load_eval_cases(self.evals_dir)
        if skill_filter:
            cases = [c for c in cases if c.skill_id == skill_filter]

        results = []
        total_tokens = 0
        for case in cases:
            result = self.run_case(case)
            results.append(result)
            total_tokens += result.tokens_consumed

        passed = sum(1 for r in results if r.passed)
        regressions = sum(1 for r in results if r.regression_flagged)
        logger.info(
            "Eval suite complete: %d/%d passed, %d regressions, %d tokens estimated",
            passed, len(results), regressions, total_tokens,
        )
        return results

    def _get_fixture_data(self, case: EvalCase) -> tuple[list[dict[str, Any]], str]:
        """Return pre-specified fixture events and transcript from the eval case."""
        events = case.fixture_events or []
        transcript = case.fixture_transcript or self._events_to_transcript(events, case)
        return events, transcript

    def _run_live_session(self, case: EvalCase) -> tuple[list[dict[str, Any]], str]:
        """Live mode: invoke Claude API, capture events. Phase 2 implementation."""
        raise NotImplementedError(
            "Live session mode not yet implemented (Phase 2). "
            "Use fixture mode or provide fixture_events in the eval case."
        )

    def _events_to_transcript(self, events: list[dict[str, Any]], case: EvalCase) -> str:
        """Generate a synthetic transcript from events when fixture_transcript is absent."""
        if not events:
            return f"[Session for eval {case.eval_id}: no events captured]"
        lines = [f"[Eval session: {case.eval_id}]", f"Input: {case.input_prompt}", ""]
        for evt in events:
            evt_type = evt.get("event_type", "unknown")
            skill = evt.get("skill_id") or evt.get("trace", {}).get("skill_id", "")
            detail = f" skill={skill}" if skill else ""
            lines.append(f"  Event: {evt_type}{detail}")
        return "\n".join(lines)


def format_results_report(results: list[EvalResult]) -> str:
    """Format eval results as a human-readable report."""
    lines = ["\n=== Behavioral Eval Report ==="]
    total_tokens = 0

    for result in results:
        status = "✓" if result.passed else "✗"
        reg = " [REGRESSION]" if result.regression_flagged else ""
        lines.append(
            f"  {status} {result.eval_id} — {result.score_display}{reg}"
        )
        if not result.passed:
            mr = result.match_result
            if mr.missing_events:
                lines.append(f"      Missing events: {', '.join(mr.missing_events)}")
            if mr.negative_violations:
                lines.append(f"      Violations: {', '.join(mr.negative_violations)}")
            if result.judge_result.rationale:
                lines.append(f"      Judge: {result.judge_result.rationale}")
        total_tokens += result.tokens_consumed

    passed = sum(1 for r in results if r.passed)
    regressions = sum(1 for r in results if r.regression_flagged)
    lines.append(f"\nSummary: {passed}/{len(results)} passed")
    if regressions:
        lines.append(f"  ⚠️  {regressions} regression(s) detected")
    lines.append(f"  Tokens estimated: {total_tokens:,}")
    return "\n".join(lines)
