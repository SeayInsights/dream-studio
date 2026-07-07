"""WO-SPLIT-STUDIO-DB: event_writer module (split from studio_db.py)."""

from __future__ import annotations
import hashlib
import json
from datetime import datetime, timedelta, UTC
from pathlib import Path

from .connection import (
    _CanonicalEventType,
    _NOW,
    _db_path,
    _db_transaction,
    _reraise_if_busy,
    _try_emit_canonical,
    _with_retry,
    get_connection,
    paths,
)


@_with_retry
def import_buffer(buffer_path: Path, db_path: Path | None = None) -> int:
    try:
        raw = buffer_path.read_bytes()
        if not raw.strip():
            return 0
        bid = hashlib.sha256(raw).hexdigest()
        with _db_transaction(db_path) as c:
            if c.execute("SELECT 1 FROM log_batch_imports WHERE batch_id=?", (bid,)).fetchone():
                return 0
            rows = [json.loads(ln) for ln in raw.decode().splitlines() if ln.strip()]
            for r in rows:
                c.execute(
                    "INSERT INTO raw_skill_telemetry(skill_name,invoked_at,model,input_tokens,output_tokens,success,execution_time_s) VALUES(?,?,?,?,?,?,?)",
                    (
                        r["skill_name"],
                        r.get("invoked_at", _NOW()),
                        r.get("model"),
                        r.get("input_tokens"),
                        r.get("output_tokens"),
                        int(r["success"]),
                        r.get("execution_time_s"),
                    ),
                )
            c.execute(
                "INSERT INTO log_batch_imports(batch_id,imported_at,row_count) VALUES(?,?,?)",
                (bid, _NOW(), len(rows)),
            )
        return len(rows)
    except Exception as e:
        _reraise_if_busy(e)
        return 0


@_with_retry
def rolling_window_prune(db_path: Path | None = None) -> int:
    """Prune rolling-window telemetry tables.

    WO 9f47a1a0: the raw_workflow_nodes/raw_workflow_runs DELETEs that used to
    live here were dropped along with the tables themselves (migration 141,
    write-orphaned since 2026-05-18 — see
    core/event_store/migrations/141_drop_orphaned_workflow_raw_tables.sql).
    Canonical workflow.completed/workflow.node.completed events are
    append-only in ai_canonical_events and are not pruned by this function.
    """
    try:
        cutoff = (datetime.now(UTC) - timedelta(days=90)).isoformat()
        with _db_transaction(db_path) as c:
            d1 = c.execute(
                "DELETE FROM raw_skill_telemetry WHERE id NOT IN (SELECT id FROM raw_skill_telemetry t2 WHERE t2.skill_name=raw_skill_telemetry.skill_name ORDER BY id DESC LIMIT 100)"
            ).rowcount
            d4 = c.execute("DELETE FROM raw_approaches WHERE captured_at<?", (cutoff,)).rowcount
        return d1 + d4
    except Exception as e:
        _reraise_if_busy(e)
        return 0


@_with_retry
def insert_operational_snapshot(
    snapshot_date: str,
    project_slug: str,
    *,
    ci_status: str | None = None,
    open_prs: int | None = None,
    stale_branches: int | None = None,
    pending_drafts: int | None = None,
    open_escalations: int | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO raw_operational_snapshots
                   (snapshot_date, project_slug, ci_status, open_prs,
                    stale_branches, pending_drafts, open_escalations, captured_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot_date,
                    project_slug,
                    ci_status,
                    open_prs,
                    stale_branches,
                    pending_drafts,
                    open_escalations,
                    _NOW(),
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def insert_approach(
    skill_id: str,
    approach: str,
    outcome: str,
    *,
    context: str = "",
    why: str = "",
    tokens_used: int | None = None,
    duration_s: float | None = None,
    model: str | None = None,
    session_date: str | None = None,
    project_id: str | None = None,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        if db_path is not None and not Path(db_path).parent.exists():
            return False
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT INTO raw_approaches
                   (skill_id, session_date, approach, outcome, context,
                    why_worked, tokens_used, duration_s, model, captured_at,
                    project_id, session_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    skill_id,
                    session_date or _NOW()[:10],
                    approach,
                    outcome,
                    context or None,
                    why or None,
                    tokens_used,
                    duration_s,
                    model,
                    _NOW(),
                    project_id,
                    session_id,
                ),
            )

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.APPROACH_CAPTURED,
                {
                    "skill_id": skill_id,
                    "approach": approach,
                    "outcome": outcome,
                    "model": model,
                    "duration_s": duration_s,
                    "tokens_used": tokens_used,
                },
                session_id=session_id,
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def capture_approach(
    skill: str,
    approach: str,
    outcome: str,
    context: str = "",
    why: str = "",
) -> bool:
    """High-level convenience: write approach to DB, fall back to text file."""
    ok = insert_approach(skill, approach, outcome, context=context, why=why, db_path=_db_path())
    if not ok:
        try:
            fallback = paths.meta_dir() / "approaches.log"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%H:%M")
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(f"{ts} | approach:{skill} | {outcome} | {approach}\n")
            return True
        except Exception:
            return False
    return True


@_with_retry
def upsert_gotcha(
    gotcha_id: str,
    skill_id: str,
    severity: str,
    title: str,
    *,
    context: str = "",
    fix: str = "",
    keywords: str = "",
    discovered: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO reg_gotchas
                   (gotcha_id, skill_id, severity, title, context, fix,
                    keywords, discovered, times_hit, last_hit)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?,
                           COALESCE((SELECT times_hit FROM reg_gotchas WHERE gotcha_id=? AND skill_id=?), 0),
                           (SELECT last_hit FROM reg_gotchas WHERE gotcha_id=? AND skill_id=?))""",
                (
                    gotcha_id,
                    skill_id,
                    severity,
                    title,
                    context,
                    fix,
                    keywords,
                    discovered,
                    gotcha_id,
                    skill_id,
                    gotcha_id,
                    skill_id,
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def clear_registry(db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute("DELETE FROM reg_gotchas")  # noqa: S608
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def upsert_project(
    project_id: str,
    project_path: str,
    *,
    project_name: str | None = None,
    project_type: str | None = None,
    git_remote: str | None = None,
    db_path: Path | None = None,
) -> bool:
    # reg_projects deleted in migration 084. Writes to business_projects instead.
    # project_type maps to detected_stack; git_remote has no equivalent column (ignored).
    # INSERT OR IGNORE preserves existing rows, then selectively UPDATE changed fields.
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                "INSERT OR IGNORE INTO business_projects"
                " (project_id, name, project_path, detected_stack, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 'active', ?, ?)",
                (
                    project_id,
                    project_name or project_id,
                    project_path,
                    project_type,
                    _NOW(),
                    _NOW(),
                ),
            )
            # Update mutable fields only when the row already existed
            c.execute(
                "UPDATE business_projects SET"
                " project_path = ?,"
                " updated_at = ?"
                " WHERE project_id = ?",
                (project_path, _NOW(), project_id),
            )
            if project_name:
                c.execute(
                    "UPDATE business_projects SET name = ? WHERE project_id = ? AND name = ?",
                    (project_name, project_id, project_id),
                )
            if project_type:
                c.execute(
                    "UPDATE business_projects SET detected_stack = ? WHERE project_id = ?",
                    (project_type, project_id),
                )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def update_project_stats(
    project_id: str, *, sessions_delta: int = 0, tokens_delta: int = 0, db_path: Path | None = None
) -> bool:
    # reg_projects deleted in migration 084. Update business_projects instead.
    # Only applies when project_id is a UUID that exists in business_projects.
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """UPDATE business_projects SET
                    total_sessions = total_sessions + ?,
                    total_tokens = total_tokens + ?,
                    last_session_at = ?,
                    updated_at = ?
                   WHERE project_id = ?""",
                (sessions_delta, tokens_delta, _NOW(), _NOW(), project_id),
            )

            # Event emission (additive side-effect) — TA0c: activity_log retired
            _try_emit_canonical(
                _CanonicalEventType.PROJECT_STATS_UPDATED,
                {
                    "project_id": project_id,
                    "sessions_delta": sessions_delta,
                    "tokens_delta": tokens_delta,
                },
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


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

        # Session-end friction signal harvest (Phase 19.2).
        # Non-blocking: session close completes regardless of harvester outcome.
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
        # Non-blocking: session close completes regardless of classifier outcome.
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
        # Detects skill co-occurrence patterns across sessions and upserts to
        # ds_workflow_pattern_signals. Runs after gap classification so the
        # current session's friction signals are already captured.
        # Non-blocking: session close completes regardless of analyzer outcome.
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

        # Session-end retroactive validation (Phase 19.5).
        # Increments past_wo_count for experimental extensions whose skills ran
        # this session; triggers full validation when count crosses 5.
        # Non-blocking: session close completes regardless of validation outcome.
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

        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


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


@_with_retry
def insert_lesson(
    lesson_id: str,
    source: str,
    title: str,
    *,
    what_happened: str | None = None,
    lesson: str | None = None,
    evidence: str | None = None,
    confidence: str = "medium",
    prd_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    skill_id: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """
    Insert lesson into raw_lessons table.

    Writes to activity_log FIRST via EventNormalizer, then links via activity_id (Phase 3 traceability).

    Args:
        lesson_id: Unique lesson identifier
        source: Source of the lesson (e.g., 'build', 'review', 'debug')
        title: Short lesson title
        what_happened: Description of what occurred
        lesson: The actual lesson learned
        evidence: Evidence supporting the lesson
        confidence: Confidence level ('low', 'medium', 'high')
        prd_id: Optional PRD ID for cross-domain linkage
        task_id: Optional task ID for cross-domain linkage
        session_id: Optional session ID for cross-domain linkage
        skill_id: Optional skill ID for cross-domain linkage
        db_path: Optional database path
    """
    try:
        with _db_transaction(db_path) as c:
            # 1. Emit canonical event (TA0c: activity_log retired)
            _try_emit_canonical(
                _CanonicalEventType.LESSON_CAPTURED,
                {
                    "lesson_id": lesson_id,
                    "source": source,
                    "title": title,
                    "confidence": confidence,
                },
                session_id=session_id,
                task_id=task_id,
                prd_id=prd_id,
                skill_id=skill_id,
            )
            activity_id = None  # deprecated FK column

            # 2. Insert into raw_lessons with activity_id FK
            c.execute(
                """INSERT OR IGNORE INTO raw_lessons
                   (lesson_id, source, title, what_happened, lesson,
                    evidence, confidence, created_at, activity_id,
                    prd_id, task_id, skill_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lesson_id,
                    source,
                    title,
                    what_happened,
                    lesson,
                    evidence,
                    confidence,
                    _NOW(),
                    activity_id,
                    prd_id,
                    task_id,
                    skill_id,
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def draft_lesson(
    source: str,
    title: str,
    *,
    lesson_id: str | None = None,
    what_happened: str | None = None,
    lesson: str | None = None,
    evidence: str | None = None,
    confidence: str = "medium",
    db_path: Path | None = None,
) -> bool:
    """Create a draft lesson in raw_lessons. Single authoritative entry point.

    lesson_id defaults to a UUID if not supplied. Callers that need deterministic
    deduplication (e.g., file-based writers that deduplicated by filename) should
    supply a stable lesson_id (e.g., the old filename stem).
    """
    import uuid as _uuid

    lid = lesson_id if lesson_id is not None else str(_uuid.uuid4())
    return insert_lesson(
        lid,
        source,
        title,
        what_happened=what_happened,
        lesson=lesson,
        evidence=evidence,
        confidence=confidence,
        db_path=db_path,
    )


@_with_retry
def promote_lesson(lesson_id: str, promoted_to: str, db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """UPDATE raw_lessons SET
                    status='promoted', promoted_to=?, reviewed_at=?
                   WHERE lesson_id=?""",
                (promoted_to, _NOW(), lesson_id),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def reject_lesson(lesson_id: str, db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                "UPDATE raw_lessons SET status='rejected', reviewed_at=? WHERE lesson_id=?",
                (_NOW(), lesson_id),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def cache_research(
    topic: str,
    focus_areas: list[str],
    sources: list[dict],
    findings: str,
    *,
    confidence_score: float = 0.5,
    triangulation_score: float = 0.5,
    prd_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    ttl_days: int = 30,
    db_path: Path | None = None,
) -> bool:
    """
    Cache research results in research_cache table.

    Writes to activity_log FIRST via EventNormalizer, then links via activity_id (Phase 3 traceability).

    Args:
        topic: Research topic
        focus_areas: List of focus areas (JSON array)
        sources: List of source dicts with {url, title, summary, tier}
        findings: Markdown summary of research findings
        confidence_score: Overall confidence (0.0-1.0)
        triangulation_score: Source triangulation score (0.0-1.0)
        prd_id: Optional PRD ID for cross-domain linkage
        task_id: Optional task ID for cross-domain linkage
        session_id: Optional session ID for cross-domain linkage
        ttl_days: Time-to-live in days (default 30)
        db_path: Optional database path
    """
    try:
        cache_id = hashlib.sha256(topic.encode()).hexdigest()[:16]
        expires_at = (datetime.now(UTC) + timedelta(days=ttl_days)).isoformat()

        with _db_transaction(db_path) as c:
            # 1. Emit canonical event (TA0c: activity_log retired)
            _try_emit_canonical(
                _CanonicalEventType.RESEARCH_CACHE_STORED,
                {
                    "cache_id": cache_id,
                    "topic": topic,
                    "source_count": len(sources),
                    "confidence_score": confidence_score,
                    "triangulation_score": triangulation_score,
                },
                session_id=session_id,
                task_id=task_id,
                prd_id=prd_id,
            )
            activity_id = None  # deprecated FK column

            # 2. Insert into research_cache with activity_id FK
            c.execute(
                """INSERT OR REPLACE INTO research_cache
                   (cache_id, topic, focus_areas, sources, findings,
                    confidence_score, triangulation_score, activity_id,
                    prd_id, task_id, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cache_id,
                    topic,
                    json.dumps(focus_areas),
                    json.dumps(sources),
                    findings,
                    confidence_score,
                    triangulation_score,
                    activity_id,
                    prd_id,
                    task_id,
                    expires_at,
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def set_sentinel(
    sentinel_key: str,
    sentinel_type: str,
    *,
    expires_at: str | None = None,
    db_path: Path | None = None,
) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """INSERT OR REPLACE INTO raw_sentinels
                   (sentinel_key, sentinel_type, created_at, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (sentinel_key, sentinel_type, _NOW(), expires_at),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def clear_expired_sentinels(db_path: Path | None = None) -> int:
    try:
        with _db_transaction(db_path) as c:
            n = c.execute(
                "DELETE FROM raw_sentinels WHERE expires_at IS NOT NULL AND expires_at < ?",
                (_NOW(),),
            ).rowcount
        return n
    except Exception as e:
        _reraise_if_busy(e)
        return 0


@_with_retry
def insert_hook_execution(
    hook_name: str,
    hook_type: str,
    trigger_context: dict,
    started_at: str,
    completed_at: str | None = None,
    duration_ms: int | None = None,
    exit_code: int = 0,
    status: str = "success",
    output: str | None = None,
    error_message: str | None = None,
    cpu_time_ms: int | None = None,
    memory_mb: float | None = None,
    prd_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    db_path: Path | None = None,
) -> int | None:
    """
    Emit the HOOK_EXECUTION_LOGGED canonical event for a hook execution.

    The SQLite hook_executions projection table was dropped in migration 129
    (WO-READMODELS-DUCKDB). Hook executions are now served by the DuckDB
    hook_executions VIEW in aggregate_metrics.db, derived from this canonical
    event via the events_fact pipeline. This function only emits the canonical
    event; it no longer writes a SQLite projection row.

    Returns None (activity_id is a retired FK column).
    Uses fire-and-forget pattern with DB lock fallback to text file.
    """
    try:
        with _db_transaction(db_path):
            # Emit canonical event (TA0c: activity_log retired). The DuckDB
            # hook_executions view is derived from this event via events_fact.
            _try_emit_canonical(
                _CanonicalEventType.HOOK_EXECUTION_LOGGED,
                {
                    "hook_name": hook_name,
                    "hook_type": hook_type,
                    "trigger_context": trigger_context,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "duration_ms": duration_ms,
                    "exit_code": exit_code,
                    "status": status,
                    "output": output,
                    "error_message": error_message,
                    "cpu_time_ms": cpu_time_ms,
                    "memory_mb": memory_mb,
                },
                session_id=session_id,
                task_id=task_id,
                prd_id=prd_id,
            )
            return None
    except Exception as e:
        # 3. If DB locked: write to fallback file
        _reraise_if_busy(e)
        try:
            fallback = paths.state_dir() / "hook_executions_fallback.jsonl"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "hook_name": hook_name,
                            "hook_type": hook_type,
                            "trigger_context": trigger_context,
                            "started_at": started_at,
                            "completed_at": completed_at,
                            "duration_ms": duration_ms,
                            "exit_code": exit_code,
                            "status": status,
                            "output": output,
                            "error_message": error_message,
                            "cpu_time_ms": cpu_time_ms,
                            "memory_mb": memory_mb,
                            "prd_id": prd_id,
                            "task_id": task_id,
                            "session_id": session_id,
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass  # Fire-and-forget - don't fail the hook
        return -1  # Return sentinel value for fallback


def log_skill_execution(
    skill_name: str,
    skill_args: str = "",
    *,
    status: str = "success",
    model: str = "unspecified",
    session_id: str | None = None,
    project_id: str | None = None,
    prd_id: str | None = None,
    task_id: str | None = None,
    duration_ms: int | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    error_message: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """
    Log skill execution to activity_log via EventNormalizer (TC-007).

    This function integrates the EventNormalizer with skill invocations, ensuring
    all skill outputs are normalized before being written to activity_log.

    Args:
        skill_name: Skill identifier (e.g., "ds-core", "ds-quality")
        skill_args: Skill arguments/mode (e.g., "build", "debug")
        status: Execution status ("success", "failed", "error")
        model: Optional tool/model metadata label
        session_id: Tool/session ID
        project_id: Project identifier
        prd_id: Optional PRD ID for cross-domain linkage
        task_id: Optional task ID for cross-domain linkage
        duration_ms: Execution duration in milliseconds
        input_tokens: Input token count
        output_tokens: Output token count
        error_message: Optional error message if status != "success"
        db_path: Optional database path

    Returns:
        True on success, False on failure
    """
    try:
        # Generate unique skill execution ID
        skill_exec_id = hashlib.sha256(
            f"{skill_name}:{skill_args}:{session_id}:{_NOW()}".encode()
        ).hexdigest()[:16]

        # Map user-friendly status to DB-compatible status
        # DB schema only allows: 'pending', 'in_progress', 'completed', 'failed', 'cancelled'
        status_map = {
            "success": "completed",
            "error": "failed",
            "pending": "pending",
            "in_progress": "in_progress",
            "completed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }
        db_status = status_map.get(status, "completed")  # Default to "completed" for unknown

        # Emit canonical event (TA0c: activity_log retired)
        _try_emit_canonical(
            _CanonicalEventType.SKILL_EXECUTED,
            {
                "skill_exec_id": skill_exec_id,
                "skill_name": skill_name,
                "skill_args": skill_args,
                "model": model,
                "status": db_status,
                "duration_ms": duration_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "error_message": error_message,
                "session_id": session_id,
                "project_id": project_id,
            },
            session_id=session_id,
            task_id=task_id,
            prd_id=prd_id,
            skill_id=skill_name,
        )

        return True
    except Exception as e:
        _reraise_if_busy(e)
        # Fallback: write to JSONL file if DB write fails
        try:
            fallback = paths.state_dir() / "skill_executions_fallback.jsonl"
            fallback.parent.mkdir(parents=True, exist_ok=True)
            with open(fallback, "a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "skill_name": skill_name,
                            "skill_args": skill_args,
                            "status": status,
                            "model": model,
                            "session_id": session_id,
                            "project_id": project_id,
                            "error_message": error_message,
                            "logged_at": _NOW(),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass  # Fire-and-forget - don't fail the hook
        return False
