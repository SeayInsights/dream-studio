"""Behavioral eval runner — deterministic fixture scoring + live subagent mode.

Fixture mode (default): composite_score = event_score (100% deterministic, no LLM).
  Events are read from case.fixture_events.
  Pass threshold: composite_score >= case.minimum_pass_score.

Live mode (--live): spawn a fresh claude subprocess, synthesize events from its
  tool-call JSON output, score with the same deterministic matcher.
  Requires 'claude' CLI in PATH. Skipped gracefully when unavailable.
  Live runs emit an eval.run.completed canonical event with run_mode='live'.

WO-GF-CORE-HEALTH-SKILLS: implementation moved to runner_{process,outcome}.py;
this module re-exports the public+private surface so existing
`from core.eval.runner import X` callers are unchanged.
"""

from __future__ import annotations

from .runner_process import match_events  # noqa: F401 — pre-split passthrough (core.eval.matcher)
from .runner_outcome import (
    _read_wo_tasks_for_outcome,
    _record_outcome_run,
    _reopen_and_escalate,
    evaluate_wo_outcome,
    run_outcome_eval,
)
from .runner_process import (
    EVALS_DIR,
    EvalRunner,
    _synthesize_events_from_output,
    _write_live_eval_run,
    format_results_report,
    load_eval_cases,
    logger,
)

__all__ = [
    "EVALS_DIR",
    "EvalRunner",
    "_read_wo_tasks_for_outcome",
    "_record_outcome_run",
    "_reopen_and_escalate",
    "_synthesize_events_from_output",
    "_write_live_eval_run",
    "evaluate_wo_outcome",
    "format_results_report",
    "load_eval_cases",
    "logger",
    "run_outcome_eval",
]
