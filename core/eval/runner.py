"""Behavioral eval runner — deterministic fixture scoring + live subagent mode.

Fixture mode (default): composite_score = event_score (100% deterministic, no LLM).
  Events are read from case.fixture_events.
  Pass threshold: composite_score >= case.minimum_pass_score.

Live mode (--live): spawn a fresh claude subprocess, synthesize events from its
  tool-call JSON output, score with the same deterministic matcher.
  Requires 'claude' CLI in PATH. Skipped gracefully when unavailable.
  Live runs write run_mode='live' to ds_eval_runs.
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import uuid
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

    def run_case(self, case: EvalCase, *, live: bool = False) -> EvalResult:
        """Run a single eval case and return the result.

        Args:
            case: The eval case to run.
            live: If True, spawn a fresh claude subprocess and score its events.
                  If False (default), use case.fixture_events (deterministic).
        """
        if live:
            return self._run_case_live(case)

        start = time.monotonic()

        try:
            # ── 1. Get events ────────────────────────────────────────────────
            if case.fixture_events is None:
                raise NotImplementedError(
                    f"Live canonical-session eval mode is not implemented for this case "
                    f"via fixture mode. Use run_case(case, live=True) or add fixture_events "
                    f"to eval case '{case.eval_id}'."
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

    def _run_case_live(self, case: EvalCase) -> EvalResult:
        """Live mode: spawn a fresh claude subprocess, synthesize events, score.

        Requires 'claude' CLI in PATH. Events are synthesized from the subprocess
        JSON output (tool_use calls for Skill invocations). No spool ingestor
        dependency — synthesis happens inline from subprocess stdout.
        """
        start = time.monotonic()

        if not shutil.which("claude"):
            raise NotImplementedError(
                "Live eval mode requires the 'claude' CLI in PATH. "
                "Install Claude Code and ensure 'claude' is on your PATH."
            )

        try:
            # ── 1. Spawn subagent — isolated, no session history ──────────────
            proc = subprocess.run(
                [
                    "claude",
                    "--print",
                    case.input_prompt,
                    "--model",
                    "claude-haiku-4-5-20251001",
                    "--output-format",
                    "json",
                ],
                capture_output=True,
                text=True,
                timeout=120,
            )
            raw_output = proc.stdout or ""

            # ── 2. Synthesize events from JSON output ─────────────────────────
            events = _synthesize_events_from_output(raw_output)

            # ── 3. Deterministic scoring ──────────────────────────────────────
            match_result = match_events(case, events)
            event_score = match_result.score
            composite_score = round(event_score, 4)
            passed = composite_score >= case.minimum_pass_score

            # ── 4. Baseline check ─────────────────────────────────────────────
            baseline_data = load_baseline(case.eval_id + ":live", case.version, self.db_path)
            baseline_score = baseline_data["baseline_score"] if baseline_data else None

            _is_baseline, regression_flagged = save_run_result(
                case.eval_id + ":live",
                case.version,
                composite_score,
                passed,
                db_path=self.db_path,
            )

            # ── 5. Persist to ds_eval_runs ────────────────────────────────────
            _write_live_eval_run(
                eval_id=case.eval_id,
                version=case.version,
                composite_score=composite_score,
                passed=passed,
                failure_reasons=match_result.missing_events + match_result.negative_violations,
                db_path=self.db_path,
            )

            elapsed = time.monotonic() - start
            logger.info(
                "live eval %s: %s score=%.3f regression=%s elapsed=%.1fs events_captured=%d",
                case.eval_id,
                "PASS" if passed else "FAIL",
                composite_score,
                regression_flagged,
                elapsed,
                len(events),
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
                run_mode="live",
            )

        except subprocess.TimeoutExpired:
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
                error="Live eval timed out after 120s",
                run_mode="live",
            )
        except Exception as exc:
            logger.error("Live eval %s failed: %s", case.eval_id, exc)
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
                run_mode="live",
            )

    def run_all(self, skill_filter: str | None = None, *, live: bool = False) -> list[EvalResult]:
        """Run all eval cases (optionally filtered by skill_id)."""
        cases = load_eval_cases(self.evals_dir)
        if skill_filter:
            cases = [c for c in cases if c.skill_id == skill_filter]

        results = []
        for case in cases:
            result = self.run_case(case, live=live)
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


def _synthesize_events_from_output(raw_output: str) -> list[dict]:
    """Convert claude --output-format json stdout into a list of event dicts.

    The JSON output stream contains lines like:
      {"type": "tool_use", "name": "Skill", "input": {"skill": "ds-project", "args": "resume"}}
      {"type": "tool_result", "name": "Skill", ...}

    We synthesize Dream Studio event types:
      - session.start: always prepended
      - skill.invoked: for each Skill tool_use
      - skill.completed: for each Skill tool_result
      - session.end: always appended
    """
    events: list[dict] = [{"event_type": "session.start"}]
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        msg_type = obj.get("type", "")
        if msg_type == "tool_use" and obj.get("name") == "Skill":
            inp = obj.get("input") or {}
            skill = inp.get("skill", "")
            args = inp.get("args", "")
            skill_id = f"{skill}:{args}" if args else skill
            events.append(
                {
                    "event_type": "skill.invoked",
                    "skill_id": skill_id,
                    "trace": {"skill_id": skill_id},
                }
            )
        elif msg_type == "tool_result" and obj.get("name") == "Skill":
            events.append({"event_type": "skill.completed"})
    events.append({"event_type": "session.end"})
    return events


def _write_live_eval_run(
    *,
    eval_id: str,
    version: str,
    composite_score: float,
    passed: bool,
    failure_reasons: list[str],
    db_path=None,
) -> None:
    """Persist one live-mode eval run to ds_eval_runs. Non-fatal on any error."""
    try:
        import sqlite3

        if db_path is None:
            from core.config.database import _default_db_path

            db_path = _default_db_path()
        conn = sqlite3.connect(str(db_path))
        run_id = str(uuid.uuid4())
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        conn.execute(
            "INSERT INTO ds_eval_runs"
            " (run_id, eval_id, eval_version, started_at, completed_at,"
            "  event_score, behavior_score, total_score, passed, failure_reasons, run_mode)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                run_id,
                eval_id,
                version,
                now,
                now,
                composite_score,
                composite_score,
                composite_score,
                1 if passed else 0,
                json.dumps(failure_reasons),
                "live",
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        # ds_eval_runs may not exist or run_mode column may be absent on older DBs.
        pass


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
