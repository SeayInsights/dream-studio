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
from datetime import UTC

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
    """Persist one live-mode eval run to ds_eval_runs and update eval_registry. Non-fatal on any error."""
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


# ── Outcome eval (WO-OUTCOME-EVAL) ──────────────────────────────────────────
#
# The eval runner above measures PROCESS (rail adherence from traces). The
# outcome eval measures OUTCOME: for a recently-closed WO, re-run its
# originating_symptom + task acceptance-criteria against live/seeded state and
# report whether the symptom actually stayed resolved. On FAIL with
# auto_reopen=True the WO is set back to in_progress and an escalation file is
# written (consumed by the pulse open-escalations counter). This is the safety
# net behind the close gate — a WO can close green and still regress later.


def _read_wo_tasks_for_outcome(conn, work_order_id: str) -> list[dict]:
    has_ac = any(
        r[1] == "acceptance_criteria"
        for r in conn.execute("PRAGMA table_info(business_tasks)").fetchall()
    )
    cols = "title, description, status" + (", acceptance_criteria" if has_ac else "")
    rows = conn.execute(
        f"SELECT {cols} FROM business_tasks WHERE work_order_id = ? ORDER BY created_at ASC",
        (work_order_id,),
    ).fetchall()
    return [
        {
            "title": r[0],
            "description": r[1] or "",
            "status": r[2],
            "acceptance_criteria": (r[3] or "") if has_ac else "",
        }
        for r in rows
    ]


def evaluate_wo_outcome(
    work_order_id: str,
    *,
    db_path: Path,
    source_root: Path | None = None,
    symptom_only: bool = False,
) -> dict:
    """Re-run a closed WO's originating_symptom (+ task ACs unless symptom_only).

    Returns ``{work_order_id, title, passed, failures}``. ``passed`` is False when
    the symptom SQL-CHECK still fails or any executable AC fails.
    """
    import sqlite3

    db_path = Path(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT title, originating_symptom FROM business_work_orders WHERE work_order_id = ?",
            (work_order_id,),
        ).fetchone()
        if row is None:
            return {"work_order_id": work_order_id, "passed": True, "failures": [], "skipped": True}
        title, symptom = row
        tasks = [] if symptom_only else _read_wo_tasks_for_outcome(conn, work_order_id)
    finally:
        conn.close()

    failures: list[str] = []

    if symptom:
        from core.work_orders.close import _check_originating_symptom

        reason = _check_originating_symptom(symptom, db_path)
        if reason:
            failures.append(reason)

    if tasks:
        from core.work_orders.verify import run_executable_checks

        try:
            ac_results = run_executable_checks(tasks, db_path, source_root)
        except TypeError:
            # Older signature without source_root.
            ac_results = run_executable_checks(tasks, db_path)
        for t_title, checks in ac_results.items():
            for c in checks:
                if not c.get("passed"):
                    failures.append(
                        f"executable_ac[{t_title}]: {c.get('kind', 'CHECK')} "
                        f"{c.get('expr', '')!r} FAILED — {c.get('error') or 'check returned falsy'}"
                    )

    return {
        "work_order_id": work_order_id,
        "title": title,
        "passed": not failures,
        "failures": failures,
    }


def _record_outcome_run(work_order_id: str, outcome: dict, db_path: Path) -> None:
    """Best-effort: record the outcome eval to ds_eval_runs (never raises)."""
    import sqlite3
    from datetime import datetime

    try:
        now = datetime.now(UTC).isoformat()
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute(
                "INSERT INTO ds_eval_runs"
                " (run_id, eval_id, eval_version, started_at, completed_at,"
                "  event_score, behavior_score, total_score, passed, failure_reasons, run_mode)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(uuid.uuid4()),
                    f"outcome:{work_order_id[:8]}",
                    "1",
                    now,
                    now,
                    None,
                    None,
                    None,
                    1 if outcome["passed"] else 0,
                    json.dumps(outcome["failures"]),
                    "outcome",
                ),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        pass


def _reopen_and_escalate(
    work_order_id: str,
    outcome: dict,
    *,
    db_path: Path,
    source_root: Path | None = None,
    dream_studio_home: Path | None = None,
) -> None:
    """Set a regressed WO back to in_progress and write an unresolved escalation file.

    The business_work_orders status write goes through the work-order mutation
    layer (reopen_work_order) — never a direct write from the eval layer — to
    respect the authority boundary (dependency Rule 3). reopen_work_order also
    emits work_order.reopened and syncs the read model.
    """
    from core.work_orders.escalation import (
        escalate_to_operator,
        mark_escalated,
        register_retry,
    )
    from core.work_orders.mutations import reopen_work_order

    _reason = "; ".join(str(f) for f in outcome.get("failures", [])) or "outcome regressed"

    # WO-ESCALATION-LADDER T4: count this retry attempt. When the cap is reached, stop
    # the auto-retry loop and hand the WO to the operator — do NOT silently reopen
    # again. The escalation file below is replaced by an operator-action escalation.
    _retry = register_retry(work_order_id, db_path=Path(db_path))
    if _retry["capped"]:
        escalate_to_operator(
            work_order_id,
            db_path=Path(db_path),
            dream_studio_home=dream_studio_home,
            reason=(
                f"retry cap reached ({_retry['retry_count']}/{_retry['retry_cap']}); "
                f"last failure: {_reason}"
            ),
        )
        return

    reopen_work_order(
        work_order_id=work_order_id,
        reason="outcome_eval: symptom regressed after close",
        source_root=source_root,
        dream_studio_home=dream_studio_home,
    )

    # Escalate: the reopened WO carries the Opus capability flag so its retry is
    # routed to a more capable model (WO-ESCALATION-LADDER T2). Both execution
    # surfaces read this via escalation.resolve_executor.
    mark_escalated(work_order_id, db_path=Path(db_path), reason=_reason)

    # Escalation file — counted by the pulse open-escalations scan
    # (meta_dir/*.md containing "ESC-" and "unresolved").
    home = Path(dream_studio_home) if dream_studio_home else Path.home() / ".dream-studio"
    meta_dir = home / "meta"
    meta_dir.mkdir(parents=True, exist_ok=True)
    esc_path = meta_dir / f"ESC-OUTCOME-{work_order_id[:8]}.md"
    reasons = "\n".join(f"- {r}" for r in outcome["failures"])
    esc_path.write_text(
        f"# ESC-OUTCOME-{work_order_id[:8]} — status: unresolved\n\n"
        f"Outcome eval re-opened work order `{work_order_id}` "
        f"({outcome.get('title', '')}). The symptom/ACs regressed after close:\n\n"
        f"{reasons}\n",
        encoding="utf-8",
    )


def run_outcome_eval(
    *,
    db_path: Path,
    source_root: Path | None = None,
    dream_studio_home: Path | None = None,
    auto_reopen: bool = True,
    symptom_only: bool = False,
    window_hours: float | None = None,
) -> dict:
    """Re-run outcomes for closed WOs that have an originating symptom.

    ``window_hours`` scopes to *recently*-closed WOs (closed_at within the window);
    ``None`` evaluates all closed WOs. The pulse passes a finite window so the
    safety net never auto-reopens ancient WOs whose symptom SQL is environment-
    dependent. On FAIL with ``auto_reopen``: set the WO back to in_progress and
    write an escalation file. Returns ``{ok, evaluated, failed, results}``.
    """
    import sqlite3
    from datetime import datetime, timedelta

    db_path = Path(db_path)
    query = (
        "SELECT work_order_id FROM business_work_orders"
        " WHERE status = 'closed'"
        " AND originating_symptom IS NOT NULL AND TRIM(originating_symptom) <> ''"
    )
    params: tuple = ()
    if window_hours is not None:
        cutoff = (datetime.now(UTC) - timedelta(hours=window_hours)).isoformat()
        # closed_at is ISO-8601 → lexicographic comparison is chronological.
        query += " AND closed_at IS NOT NULL AND closed_at >= ?"
        params = (cutoff,)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(query, params).fetchall()
    finally:
        conn.close()

    results: list[dict] = []
    for (wo_id,) in rows:
        outcome = evaluate_wo_outcome(
            wo_id, db_path=db_path, source_root=source_root, symptom_only=symptom_only
        )
        _record_outcome_run(wo_id, outcome, db_path)
        if not outcome["passed"] and auto_reopen:
            try:
                _reopen_and_escalate(
                    wo_id,
                    outcome,
                    db_path=db_path,
                    source_root=source_root,
                    dream_studio_home=dream_studio_home,
                )
                outcome["reopened"] = True
            except Exception as exc:  # pragma: no cover - defensive
                outcome["reopen_error"] = str(exc)
        results.append(outcome)

    return {
        "ok": True,
        "evaluated": len(results),
        "failed": [r for r in results if not r["passed"]],
        "results": results,
    }
