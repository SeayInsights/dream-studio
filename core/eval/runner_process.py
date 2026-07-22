"""Behavioral eval runner — deterministic fixture scoring + live subagent mode.

Fixture mode (default): composite_score = event_score (100% deterministic, no LLM).
  Events are read from case.fixture_events.
  Pass threshold: composite_score >= case.minimum_pass_score.

Live mode (--live): spawn a fresh claude subprocess, synthesize events from its
  tool-call JSON output, score with the same deterministic matcher.
  Requires 'claude' CLI in PATH. Skipped gracefully when unavailable.
  Live runs emit an eval.run.completed canonical event with run_mode='live'.

Split out of runner.py (WO-GF-CORE-HEALTH-SKILLS): the process side (fixture +
live event generation and scoring). runner_outcome.py holds the outcome-eval
side (re-running a closed WO's originating symptom / ACs).
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

logger = logging.getLogger("core.eval.runner")

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
    substrate. The default path never invokes a live Claude session; the opt-in
    ``run_case(case, live=True)`` escape hatch (developer-only, CLI ``--live``) is
    the sole exception and only *generates* events to score — scoring stays
    deterministic.
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
            live: Developer-only opt-in escape hatch. If True, spawn a fresh
                  ``claude`` subprocess (see ``_run_case_live``) to *generate* the
                  events, then score them the same deterministic way. If False
                  (the default) use ``case.fixture_events`` — no subprocess, no
                  network. CI never sets this: the pre-push eval gate runs
                  ``pytest tests/evals/`` (fixture mode), never ``ds eval --live``.
                  ``live`` only changes how events are *produced*; scoring is
                  deterministic (``match_events``) either way — it is NOT the LLM
                  judge that WO-N2 removed.
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

        Reached only via the opt-in ``run_case(case, live=True)`` escape hatch —
        never on the default path and never in CI. Requires the ``claude`` CLI in
        PATH (raises ``NotImplementedError`` otherwise, so it fails closed where the
        CLI is absent). Events are synthesized from the subprocess JSON output
        (tool_use calls for Skill invocations) and then scored by the SAME
        deterministic matcher used in fixture mode — the subprocess only produces
        the events, it does not judge them. No spool ingestor dependency —
        synthesis happens inline from subprocess stdout.
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

            if proc.returncode != 0:
                stderr_snippet = (proc.stderr or "").strip()[:200]
                error_msg = f"claude subprocess exited with returncode={proc.returncode}"
                if stderr_snippet:
                    error_msg += f": {stderr_snippet}"
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
                    error=error_msg,
                    run_mode="live",
                )

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

            # Load fixture baseline for friction detection (live vs fixture delta)
            fixture_baseline_data = load_baseline(case.eval_id, case.version, self.db_path)
            fixture_baseline_score = (
                fixture_baseline_data["baseline_score"] if fixture_baseline_data else None
            )

            # ── 5. Persist to ds_eval_runs + update eval_registry ────────────
            _write_live_eval_run(
                eval_id=case.eval_id,
                version=case.version,
                composite_score=composite_score,
                passed=passed,
                failure_reasons=match_result.missing_events + match_result.negative_violations,
                db_path=self.db_path,
                target_id=case.skill_id,
                target_type="skill" if case.skill_id else None,
                fixture_baseline_score=fixture_baseline_score,
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
    target_id: str | None = None,
    target_type: str | None = None,
    fixture_baseline_score: float | None = None,
) -> None:
    """Update eval_registry and emit the eval.run.completed canonical event.

    Non-fatal on any error. History for live eval runs now lives solely in
    business_canonical_events (T4 dropped ds_eval_runs); run_id is still
    generated here because eval_registry.last_run_id needs it, and it is
    carried in the emitted event payload so it stays discoverable.
    """
    run_id = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        import sqlite3

        if db_path is None:
            from core.config.database import _default_db_path

            db_path = _default_db_path()
        conn = sqlite3.connect(str(db_path))
        if target_id and target_type:
            conn.execute(
                "UPDATE eval_registry"
                " SET last_run_at=?, last_run_id=?, rubric_score=?, updated_at=?"
                " WHERE target_id=? AND target_type=?",
                (now, run_id, int(round(composite_score * 100)), now, target_id, target_type),
            )
            if (
                fixture_baseline_score is not None
                and (fixture_baseline_score - composite_score) > 0.10
            ):
                conn.execute(
                    "UPDATE eval_registry SET friction_flag=1, updated_at=?"
                    " WHERE target_id=? AND target_type=?",
                    (now, target_id, target_type),
                )
        conn.commit()
        conn.close()
    except Exception as exc:
        # eval_registry may not exist on older DBs — tolerated, but never silent:
        # a swallowed registry write means stale last_run/friction state.
        logger.warning("eval_registry update failed for %s: %s", eval_id, exc)

    from core.eval.events import emit_eval_run_event

    emit_eval_run_event(
        {
            "run_id": run_id,
            "eval_id": eval_id,
            "eval_version": version,
            "total_score": composite_score,
            "passed": passed,
            "failure_reasons": failure_reasons,
            "run_mode": "live",
            "target_id": target_id,
            "target_type": target_type,
        }
    )


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
