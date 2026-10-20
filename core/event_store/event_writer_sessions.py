"""event_writer sessions group: raw_sessions + raw_handoffs writers.

WO-GF-PROJECTION-ENGINE: split from ``core/event_store/event_writer.py``.
LANDMINE #2 (3 of 4): tests read this file's source text to assert the
session-end analyzer hooks (FrictionSignalHarvester, GapClassifier,
RetroactiveValidator) are wired in and fail-open.
"""

from __future__ import annotations
import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from .connection import (
    _CanonicalEventType,
    _NOW,
    _db_transaction,
    _reraise_if_busy,
    _try_emit_canonical,
    _with_retry,
    get_connection,
)


@_with_retry
def insert_session(
    session_id: str,
    project_id: str,
    *,
    topic: str | None = None,
    pipeline_phase: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT INTO raw_sessions
                   (session_id, project_id, topic, started_at, pipeline_phase)
                   VALUES (?, ?, ?, ?, ?)""",
                (session_id, project_id, topic, _NOW(), pipeline_phase),
            )

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.SESSION_RECORDED,
                {
                    "session_id": session_id,
                    "project_id": project_id,
                    "topic": topic,
                    "pipeline_phase": pipeline_phase,
                },
                session_id=session_id,
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def mark_handoff_consumed(session_id: str, db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                "UPDATE raw_sessions SET handoff_consumed=1 WHERE session_id=?", (session_id,)
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def end_session(
    session_id: str,
    *,
    outcome: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    tasks_completed: int | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        started = None
        with _db_transaction(db_path) as c:
            row = c.execute(
                "SELECT started_at FROM raw_sessions WHERE session_id=?", (session_id,)
            ).fetchone()
            if row:
                try:
                    started = datetime.fromisoformat(row["started_at"])
                except (ValueError, TypeError):
                    pass
            now = _NOW()
            duration = (datetime.fromisoformat(now) - started).total_seconds() if started else None
            c.execute(
                """UPDATE raw_sessions SET
                    ended_at=?, duration_s=?, outcome=?,
                    input_tokens=COALESCE(?, input_tokens),
                    output_tokens=COALESCE(?, output_tokens),
                    tasks_completed=COALESCE(?, tasks_completed)
                   WHERE session_id=?""",
                (now, duration, outcome, input_tokens, output_tokens, tasks_completed, session_id),
            )

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.SESSION_CLOSED,
                {
                    "session_id": session_id,
                    "outcome": outcome,
                    "duration_s": duration,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "tasks_completed": tasks_completed,
                },
                session_id=session_id,
            )

        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def run_session_end_analyzers(session_ids: Sequence[str], *, pattern_analysis: bool = True) -> None:
    """The learning-loop analyzers that follow a session close (Phases 19.2-19.5).

    NOT PART OF ``end_session``, AND NOT SAFE TO CALL FROM A HOOK. They used to run
    inline at the end of ``end_session``, which the Stop hook calls, under a comment
    that said "non-blocking". The comment described the failure handling (each block
    is fail-open) and was read as a promise about latency. It is not one:
    The workflow-pattern analyzer runs a ``json_extract`` over every row of the events
    table (525k rows, a 1.5 GB database) and was measured past three minutes. Claude
    Code waits for the Stop hook, so every turn ended with a hang, and because the
    session sentinel is written only after ``end_session`` returns, a killed run left
    no marker and the next turn started the same scan again.

    Callers run this off the hook path -- ``on-session-end`` hands it to a detached
    worker (``--analyze``). Order is part of the contract and is pinned by a test: the
    harvester feeds the classifier, the classifier feeds the pattern analyzer, and the
    validator reads what the session produced.

    Every block stays fail-open, so one analyzer failing never stops the next.
    ``pattern_analysis=False`` skips the global scan; it is not per-session, so a
    worker draining several sessions runs it once, not once each.
    """
    for session_id in session_ids:
        # Session-end friction signal harvest (Phase 19.2).
        try:
            from projections.core.analyzers.friction_signals import FrictionSignalHarvester

            _hconn = get_connection()
            try:
                harvester = FrictionSignalHarvester(_hconn, session_id=session_id)
                harvester.harvest()
            finally:
                _hconn.close()
        except Exception:
            pass

        # Session-end gap classification (Phase 19.3).
        # Runs after harvester; classifies newly-captured signals.
        try:
            from projections.core.analyzers.gap_classifier import GapClassifier

            _gconn = get_connection()
            try:
                classifier = GapClassifier(_gconn, session_id=session_id)
                classifier.classify_all()
            finally:
                _gconn.close()
        except Exception:
            pass

    # Session-end workflow pattern analysis (Phase 19.4).
    # Detects skill co-occurrence patterns across ALL sessions and upserts to
    # ds_workflow_pattern_signals. Runs after gap classification so the current
    # sessions' friction signals are already captured.
    if pattern_analysis:
        try:
            from projections.core.analyzers.workflow_patterns import WorkflowPatternAnalyzer

            _pconn = get_connection()
            try:
                analyzer = WorkflowPatternAnalyzer(_pconn)
                analyzer.analyze()
            finally:
                _pconn.close()
        except Exception:
            pass

    for session_id in session_ids:
        # Session-end retroactive validation (Phase 19.5).
        # Increments past_wo_count for experimental extensions whose skills ran
        # this session; triggers full validation when count crosses 5.
        try:
            from core.expansion.validation import RetroactiveValidator

            _vconn = get_connection()
            try:
                validator = RetroactiveValidator(_vconn)
                validator.increment_for_session(session_id=session_id)
            finally:
                _vconn.close()
        except Exception:
            pass


@_with_retry
def insert_handoff(
    session_id: str,
    project_id: str,
    topic: str,
    *,
    plan_path: str | None = None,
    pipeline_phase: str | None = None,
    current_task_id: str | None = None,
    current_task_name: str | None = None,
    tasks_completed: int | None = None,
    tasks_total: int | None = None,
    branch: str | None = None,
    last_commit: str | None = None,
    working: list | None = None,
    broken: list | None = None,
    pending_decisions: list | None = None,
    active_files: list | None = None,
    next_action: str | None = None,
    lessons_json: list | None = None,
    gotchas_hit: list | None = None,
    approaches_json: list | None = None,
    file_id: str | None = None,
    checksum: str | None = None,
    db_path: Path | None = None,
) -> int | None:
    try:
        with _db_transaction(db_path) as c:
            cur = c.execute(
                """INSERT INTO raw_handoffs
                   (session_id, project_id, topic, plan_path, pipeline_phase,
                    current_task_id, current_task_name, tasks_completed, tasks_total,
                    branch, last_commit, working, broken, pending_decisions,
                    active_files, next_action, lessons_json, gotchas_hit,
                    approaches_json, file_id, checksum, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id,
                    project_id,
                    topic,
                    plan_path,
                    pipeline_phase,
                    current_task_id,
                    current_task_name,
                    tasks_completed,
                    tasks_total,
                    branch,
                    last_commit,
                    json.dumps(working) if working is not None else None,
                    json.dumps(broken) if broken is not None else None,
                    json.dumps(pending_decisions) if pending_decisions is not None else None,
                    json.dumps(active_files) if active_files is not None else None,
                    next_action,
                    json.dumps(lessons_json) if lessons_json is not None else None,
                    json.dumps(gotchas_hit) if gotchas_hit is not None else None,
                    json.dumps(approaches_json) if approaches_json is not None else None,
                    file_id,
                    checksum,
                    _NOW(),
                ),
            )
            handoff_id = cur.lastrowid

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.HANDOFF_CREATED,
                {
                    "handoff_id": str(handoff_id),
                    "project_id": project_id,
                    "session_id": session_id,
                    "topic": topic,
                    "branch": branch,
                },
                session_id=session_id,
            )

            return handoff_id
    except Exception as e:
        _reraise_if_busy(e)
        return None
