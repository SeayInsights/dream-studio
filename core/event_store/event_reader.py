"""WO-SPLIT-STUDIO-DB: event_reader module (split from studio_db.py)."""

from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, UTC
from pathlib import Path

from .connection import _NOW, _connect


def last_run(workflow_name: str, db_path: Path | None = None) -> dict | None:
    """Most recent workflow.completed canonical event for a workflow name.

    WO 9f47a1a0: raw_workflow_runs (write-orphaned since ~2026-05-18) dropped
    by migration 141 — see
    core/event_store/migrations/141_drop_orphaned_workflow_raw_tables.sql.
    archive_workflow()'s DB write is gone; control/execution/workflow/state.py
    now emits workflow.completed canonical events straight to the spool, which
    the ingestor projects into ai_canonical_events (routing is AI-only per
    config/event_type_registry.py). Read-side is honestly empty (None) until
    ingestion has run for a given event.
    """
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                """SELECT payload FROM ai_canonical_events
                   WHERE event_type = 'workflow.completed'
                     AND json_extract(payload, '$.workflow') = ?
                   ORDER BY COALESCE(
                       json_extract(payload, '$.finished_at'),
                       json_extract(payload, '$.started_at')
                   ) DESC
                   LIMIT 1""",
                (workflow_name,),
            ).fetchone()
            if r is None:
                return None
            payload = json.loads(r["payload"])
            return {
                "run_key": payload.get("run_key"),
                "status": payload.get("status"),
                "started_at": payload.get("started_at"),
                "finished_at": payload.get("finished_at"),
            }
        finally:
            c.close()
    except Exception:
        return None


def run_count(workflow_name: str, db_path: Path | None = None) -> int:
    """Count of workflow.completed canonical events for a workflow name.

    WO 9f47a1a0: see last_run() docstring — raw_workflow_runs dropped
    migration 141, this now counts ai_canonical_events rows instead.
    """
    try:
        c = _connect(db_path)
        try:
            n = c.execute(
                """SELECT COUNT(*) FROM ai_canonical_events
                   WHERE event_type = 'workflow.completed'
                     AND json_extract(payload, '$.workflow') = ?""",
                (workflow_name,),
            ).fetchone()[0]
            return n
        finally:
            c.close()
    except Exception:
        return 0


def get_skill_summaries(db_path: Path | None = None) -> list[dict]:
    """Compute per-skill rollups directly from raw_skill_telemetry (via the
    effective_skill_runs view) at read time.

    sum_skill_summary (a persisted rebuild_summaries() rollup) was dropped in
    migration 140 — it was pure derived state duplicating raw_skill_telemetry.
    This SELECT is the same aggregation the old rebuild_summaries() INSERT used:
    only skills with >=5 total telemetry rows qualify, computed over the most
    recent 30 qualifying effective_skill_runs rows (by id, across all skills).
    """
    try:
        c = _connect(db_path)
        try:
            rows = c.execute("""SELECT
    skill_name,
    COUNT(*) AS times_used,
    AVG(success) AS success_rate,
    AVG(input_tokens) AS avg_input_tokens,
    AVG(output_tokens) AS avg_output_tokens,
    AVG(execution_time_s) AS avg_exec_time_s,
    MAX(CASE WHEN success=1 THEN invoked_at END) AS last_success,
    MAX(CASE WHEN success=0 THEN invoked_at END) AS last_failure,
    datetime('now') AS updated_at
FROM (
    SELECT * FROM effective_skill_runs
    WHERE skill_name IN (
        SELECT skill_name FROM raw_skill_telemetry GROUP BY skill_name HAVING COUNT(*)>=5
    )
    ORDER BY id DESC LIMIT 30
)
GROUP BY skill_name""").fetchall()
            result = []
            for r in rows:
                d = dict(r)
                fail_ids = c.execute(
                    "SELECT id FROM effective_skill_runs WHERE skill_name=? AND success=0 ORDER BY id DESC LIMIT 3",
                    (d["skill_name"],),
                ).fetchall()
                d["recent_failure_ids"] = [row[0] for row in fail_ids]
                result.append(d)
            return result
        finally:
            c.close()
    except Exception:
        return []


def get_approach_patterns(skill_id: str | None = None, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            if skill_id:
                rows = c.execute(
                    "SELECT * FROM vw_approach_patterns WHERE skill_id=? ORDER BY success_pct DESC",
                    (skill_id,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM vw_approach_patterns ORDER BY success_pct DESC"
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_best_approaches(skill_id: str, limit: int = 3, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                "SELECT * FROM vw_approach_patterns WHERE skill_id=? ORDER BY success_pct DESC, times_tried DESC LIMIT ?",
                (skill_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def search_gotchas_db(keyword: str, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            try:
                rows = c.execute(
                    "SELECT g.* FROM reg_gotchas g "
                    "INNER JOIN fts_gotchas f ON g.rowid = f.rowid "
                    "WHERE fts_gotchas MATCH ? ORDER BY g.severity",
                    (keyword,),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = c.execute(
                    "SELECT * FROM reg_gotchas WHERE keywords LIKE ? OR title LIKE ? "
                    "OR context LIKE ? ORDER BY severity",
                    (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%"),
                ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_gotchas_for_skill(skill_id: str, db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                "SELECT * FROM reg_gotchas WHERE skill_id=? ORDER BY severity", (skill_id,)
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_project(project_id: str, db_path: Path | None = None) -> dict | None:
    # reg_projects deleted in migration 084. Query business_projects instead.
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                "SELECT project_id, name AS project_name, description, status,"
                " project_path, detected_stack AS project_type,"
                " total_sessions, total_tokens, last_session_at,"
                " created_at, updated_at"
                " FROM business_projects WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            return dict(r) if r else None
        finally:
            c.close()
    except Exception:
        return None


def list_projects(db_path: Path | None = None) -> list[dict]:
    # reg_projects deleted in migration 084. Query business_projects instead.
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                "SELECT project_id, name AS project_name, description, status,"
                " project_path, total_sessions, total_tokens, last_session_at,"
                " created_at, updated_at"
                " FROM business_projects"
                " ORDER BY last_session_at DESC, updated_at DESC"
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_session(session_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        try:
            r = c.execute("SELECT * FROM raw_sessions WHERE session_id=?", (session_id,)).fetchone()
            return dict(r) if r else None
        finally:
            c.close()
    except Exception:
        return None


def get_latest_session(project_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                "SELECT * FROM raw_sessions WHERE project_id=? ORDER BY started_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            return dict(r) if r else None
        finally:
            c.close()
    except Exception:
        return None


def get_latest_handoff(project_id: str, db_path: Path | None = None) -> dict | None:
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                "SELECT * FROM raw_handoffs WHERE project_id=? ORDER BY created_at DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        finally:
            c.close()
        if not r:
            return None
        d = dict(r)
        for col in (
            "working",
            "broken",
            "pending_decisions",
            "active_files",
            "lessons_json",
            "gotchas_hit",
            "approaches_json",
        ):
            if d.get(col):
                try:
                    d[col] = json.loads(d[col])
                except (
                    json.JSONDecodeError,
                    TypeError,
                ):  # cq-006-suppress: intentional graceful degradation on malformed event payload. See: docs/architecture/event-store-corruption-tolerance.md
                    pass
        return d
    except Exception:
        return None


def get_latest_unconsumed_handoff(db_path: Path | None = None) -> dict | None:
    """Return the most recent handoff that has not been consumed, across all projects."""
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                """SELECT h.* FROM raw_handoffs h
               LEFT JOIN raw_sessions s ON h.session_id = s.session_id
               WHERE COALESCE(s.handoff_consumed, 0) = 0
               ORDER BY h.created_at DESC LIMIT 1""",
            ).fetchone()
        finally:
            c.close()
        if not r:
            return None
        d = dict(r)
        for col in (
            "working",
            "broken",
            "pending_decisions",
            "active_files",
            "lessons_json",
            "gotchas_hit",
            "approaches_json",
        ):
            if d.get(col):
                try:
                    d[col] = json.loads(d[col])
                except (
                    json.JSONDecodeError,
                    TypeError,
                ):  # cq-006-suppress: intentional graceful degradation on malformed event payload. See: docs/architecture/event-store-corruption-tolerance.md
                    pass
        return d
    except Exception:
        return None


def get_handoffs_for_project(
    project_id: str, limit: int = 20, db_path: Path | None = None
) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                "SELECT * FROM raw_handoffs WHERE project_id=? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_lessons(
    source: str | None = None, status: str | None = None, db_path: Path | None = None
) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            query = "SELECT * FROM raw_lessons"
            params: list = []
            clauses: list[str] = []
            if source:
                clauses.append("source=?")
                params.append(source)
            if status:
                clauses.append("status=?")
                params.append(status)
            if clauses:
                query += " WHERE " + " AND ".join(clauses)
            query += " ORDER BY created_at DESC"
            rows = c.execute(query, params).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_pending_lessons(db_path: Path | None = None) -> list[dict]:
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                "SELECT * FROM raw_lessons WHERE status='draft' ORDER BY created_at DESC",
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_research_cache(topic: str, db_path: Path | None = None) -> dict | None:
    """Get cached research for a topic (if not expired)."""
    try:
        cache_id = hashlib.sha256(topic.encode()).hexdigest()[:16]
        c = _connect(db_path)
        try:
            r = c.execute(
                """SELECT * FROM research_cache
               WHERE cache_id=? AND (expires_at IS NULL OR expires_at > ?)""",
                (cache_id, _NOW()),
            ).fetchone()
        finally:
            c.close()
        if not r:
            return None
        d = dict(r)
        # Parse JSON fields
        for col in ("focus_areas", "sources"):
            if d.get(col):
                try:
                    d[col] = json.loads(d[col])
                except (
                    json.JSONDecodeError,
                    TypeError,
                ):  # cq-006-suppress: intentional graceful degradation on malformed event payload. See: docs/architecture/event-store-corruption-tolerance.md
                    pass
        return d
    except Exception:
        return None


def get_research_by_task(task_id: str, db_path: Path | None = None) -> list[dict]:
    """Get all research linked to a specific task."""
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                """SELECT * FROM raw_research
               WHERE task_id=? ORDER BY created_at DESC""",
                (task_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def get_research_by_prd(prd_id: str, db_path: Path | None = None) -> list[dict]:
    """Get all research linked to a specific PRD."""
    try:
        c = _connect(db_path)
        try:
            rows = c.execute(
                """SELECT * FROM raw_research
               WHERE prd_id=? ORDER BY created_at DESC""",
                (prd_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            c.close()
    except Exception:
        return []


def has_sentinel(sentinel_key: str, db_path: Path | None = None) -> bool:
    try:
        c = _connect(db_path)
        try:
            r = c.execute(
                "SELECT expires_at FROM raw_sentinels WHERE sentinel_key=?", (sentinel_key,)
            ).fetchone()
        finally:
            c.close()
        if not r:
            return False
        if r["expires_at"]:
            return datetime.fromisoformat(r["expires_at"]) > datetime.now(UTC)
        return True
    except Exception:
        return False
