"""Phase 18.2.3 tests — TaskProjection.

Coverage:
  1. Happy path — created → completed sequence
  2. Task deleted lifecycle
  3. Idempotency — duplicate handle() calls produce same state, no extra rows
  4. Out-of-order events — completed before created
  5. Malformed events — missing task_id, unknown event_type
  6. Skeleton backfill — task.created arrives after skeleton written by out-of-order event
"""

from __future__ import annotations

import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# DDL — mirrors the live schema including migration 072 additions
# ---------------------------------------------------------------------------

_BUSINESS_TASKS_DDL = """
CREATE TABLE IF NOT EXISTS business_tasks (
    task_id TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    source_event_id TEXT,
    last_event_id TEXT
);
"""

_BUSINESS_CANONICAL_DDL = """
CREATE TABLE IF NOT EXISTS business_canonical_events (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL DEFAULT (datetime('now','utc')),
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    trace JSON NOT NULL DEFAULT '{}',
    payload JSON NOT NULL DEFAULT '{}',
    correlation_id TEXT,
    project_id TEXT,
    milestone_id TEXT,
    work_order_id TEXT,
    task_id TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT 'ingestor'
);
"""

_PROJECTION_STATE_DDL = """
CREATE TABLE IF NOT EXISTS projection_state (
    projection_name TEXT PRIMARY KEY,
    last_processed_business_event_id TEXT,
    last_processed_ai_event_id TEXT,
    last_run_at TEXT,
    events_processed_total INTEGER NOT NULL DEFAULT 0,
    events_failed_total INTEGER NOT NULL DEFAULT 0
);
"""

_RETRY_QUEUE_DDL = """
CREATE TABLE IF NOT EXISTS projection_retry_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    event_source TEXT NOT NULL,
    projection_name TEXT NOT NULL,
    next_retry_at TEXT NOT NULL,
    retry_count INTEGER NOT NULL DEFAULT 0
);
"""

_DEAD_LETTER_DDL = """
CREATE TABLE IF NOT EXISTS projection_dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL,
    event_source TEXT NOT NULL,
    projection_name TEXT NOT NULL,
    error_message TEXT,
    error_traceback TEXT,
    failed_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_retry_at TEXT,
    status TEXT NOT NULL DEFAULT 'active'
);
"""

_CHECKPOINTS_DDL = """
CREATE TABLE IF NOT EXISTS projection_checkpoints (
    projection_name TEXT PRIMARY KEY,
    last_event_id TEXT NOT NULL DEFAULT '',
    last_timestamp TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
    events_processed INTEGER NOT NULL DEFAULT 0,
    last_rebuilt TEXT
);
"""

_AI_CANONICAL_DDL = """
CREATE TABLE IF NOT EXISTS ai_canonical_events (
    event_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL DEFAULT (datetime('now','utc')),
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    trace JSON NOT NULL DEFAULT '{}',
    payload JSON NOT NULL DEFAULT '{}',
    correlation_id TEXT,
    session_id TEXT,
    skill_id TEXT,
    workflow_id TEXT,
    agent_id TEXT,
    hook_id TEXT,
    model_id TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT 'ingestor'
);
"""


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _mk_task_event(
    event_type: str,
    task_id: str,
    event_timestamp: str = "2026-05-27T12:00:00+00:00",
    project_id: str = "proj-test",
    work_order_id: str = "wo-test",
    **payload_kwargs: Any,
) -> Dict[str, Any]:
    """Build a normalized event dict matching ProjectionEngine._row_to_event() format."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_timestamp": event_timestamp,
        "trace": {
            "task_id": task_id,
            "work_order_id": work_order_id,
            "project_id": project_id,
        },
        "payload": payload_kwargs,
        "correlation_id": None,
        "project_id": project_id,
        "work_order_id": work_order_id,
        "task_id": task_id,
        "_source": "business",
    }


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Tmp DB with all tables needed for TaskProjection tests."""
    db_path = tmp_path / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))

    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.executescript(
        "PRAGMA journal_mode = WAL;\n"
        + _BUSINESS_TASKS_DDL
        + _BUSINESS_CANONICAL_DDL
        + _AI_CANONICAL_DDL
        + _PROJECTION_STATE_DDL
        + _RETRY_QUEUE_DDL
        + _DEAD_LETTER_DDL
        + _CHECKPOINTS_DDL
    )
    conn.commit()
    conn.close()

    yield db_path

    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass


def _setup_projection(db_path: Path):
    from core.projections.task_projection import TaskProjection

    proj = TaskProjection()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    proj.setup_tables(conn)
    conn.close()
    return proj


def _call_handle(proj, event: Dict[str, Any], db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = proj.handle(event, conn)
        conn.commit()
        return rows
    finally:
        conn.close()


def _fetch_task(db_path: Path, task_id: str) -> Dict[str, Any] | None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM business_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# 1. Happy path — created → completed
# ---------------------------------------------------------------------------


def test_task_created_inserts_row(tmp_db):
    proj = _setup_projection(tmp_db)
    task_id = str(uuid.uuid4())
    ev = _mk_task_event(
        "task.created", task_id, title="Write the tests", description="Describe all scenarios"
    )
    result = _call_handle(proj, ev, tmp_db)
    assert result == 1
    row = _fetch_task(tmp_db, task_id)
    assert row is not None
    assert row["status"] == "pending"
    assert row["title"] == "Write the tests"
    assert row["description"] == "Describe all scenarios"
    assert row["source_event_id"] == ev["event_id"]


def test_task_completed_updates_status(tmp_db):
    proj = _setup_projection(tmp_db)
    task_id = str(uuid.uuid4())

    created = _mk_task_event("task.created", task_id, title="A task")
    completed = _mk_task_event(
        "task.completed",
        task_id,
        event_timestamp="2026-05-27T13:00:00+00:00",
    )

    _call_handle(proj, created, tmp_db)
    _call_handle(proj, completed, tmp_db)

    row = _fetch_task(tmp_db, task_id)
    assert row["status"] == "complete"
    assert row["last_event_id"] == completed["event_id"]


def test_task_deleted_updates_status(tmp_db):
    proj = _setup_projection(tmp_db)
    task_id = str(uuid.uuid4())

    created = _mk_task_event("task.created", task_id, title="A deletable task")
    deleted = _mk_task_event(
        "task.deleted",
        task_id,
        event_timestamp="2026-05-27T14:00:00+00:00",
    )

    _call_handle(proj, created, tmp_db)
    _call_handle(proj, deleted, tmp_db)

    row = _fetch_task(tmp_db, task_id)
    assert row["status"] == "deleted"
    assert row["last_event_id"] == deleted["event_id"]


# ---------------------------------------------------------------------------
# 2. Idempotency
# ---------------------------------------------------------------------------


def test_duplicate_created_event_is_noop(tmp_db):
    proj = _setup_projection(tmp_db)
    task_id = str(uuid.uuid4())
    ev = _mk_task_event("task.created", task_id, title="Idempotent task")

    _call_handle(proj, ev, tmp_db)
    result = _call_handle(proj, ev, tmp_db)

    assert result == 0  # second call skipped
    conn = sqlite3.connect(str(tmp_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM business_tasks WHERE task_id = ?", (task_id,)
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_duplicate_completed_event_is_noop(tmp_db):
    proj = _setup_projection(tmp_db)
    task_id = str(uuid.uuid4())

    created = _mk_task_event("task.created", task_id, title="T")
    completed = _mk_task_event("task.completed", task_id)

    _call_handle(proj, created, tmp_db)
    _call_handle(proj, completed, tmp_db)
    result = _call_handle(proj, completed, tmp_db)

    assert result == 0
    row = _fetch_task(tmp_db, task_id)
    assert row["status"] == "complete"


# ---------------------------------------------------------------------------
# 3. Out-of-order events
# ---------------------------------------------------------------------------


def test_completed_before_created_skeleton_then_backfill(tmp_db):
    """task.completed arriving before task.created writes skeleton, then backfills."""
    proj = _setup_projection(tmp_db)
    task_id = str(uuid.uuid4())

    completed = _mk_task_event("task.completed", task_id)
    created = _mk_task_event("task.created", task_id, title="Backfilled title")

    _call_handle(proj, completed, tmp_db)
    skeleton = _fetch_task(tmp_db, task_id)
    assert skeleton is not None
    assert skeleton["status"] == "complete"

    _call_handle(proj, created, tmp_db)
    row = _fetch_task(tmp_db, task_id)
    assert row["status"] == "complete"
    assert row["title"] == "Backfilled title"


def test_deleted_before_created_skeleton_then_backfill(tmp_db):
    proj = _setup_projection(tmp_db)
    task_id = str(uuid.uuid4())

    deleted = _mk_task_event("task.deleted", task_id)
    created = _mk_task_event("task.created", task_id, title="Was deleted first")

    _call_handle(proj, deleted, tmp_db)
    _call_handle(proj, created, tmp_db)

    row = _fetch_task(tmp_db, task_id)
    assert row["status"] == "deleted"
    assert row["title"] == "Was deleted first"


# ---------------------------------------------------------------------------
# 4. Malformed events
# ---------------------------------------------------------------------------


def test_missing_task_id_skips_event(tmp_db):
    proj = _setup_projection(tmp_db)
    ev = {
        "event_id": str(uuid.uuid4()),
        "event_type": "task.created",
        "event_timestamp": "2026-05-27T12:00:00+00:00",
        "trace": {},
        "payload": {"title": "No task ID"},
        "correlation_id": None,
        "project_id": "proj-test",
        "work_order_id": "wo-test",
        # task_id deliberately absent
        "_source": "business",
    }
    result = _call_handle(proj, ev, tmp_db)
    assert result == 0


def test_unknown_event_type_skips(tmp_db):
    proj = _setup_projection(tmp_db)
    task_id = str(uuid.uuid4())
    ev = _mk_task_event("task.unknown_future_type", task_id)
    result = _call_handle(proj, ev, tmp_db)
    assert result == 0
