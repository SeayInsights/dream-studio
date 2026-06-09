"""Phase 18.2.3 tests — MilestoneProjection.

Coverage:
  1. Happy path — created → completed sequence
  2. Milestone deleted lifecycle
  3. Idempotency — duplicate handle() calls produce same state
  4. Out-of-order events — completed before created
  5. Malformed events — missing milestone_id, unknown event_type
  6. Skeleton backfill — milestone.created arrives after out-of-order event
"""

from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# DDL — mirrors the live schema including migration 073 additions
# ---------------------------------------------------------------------------

_BUSINESS_MILESTONES_DDL = """
CREATE TABLE IF NOT EXISTS business_milestones (
    milestone_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    due_date TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    order_index INTEGER DEFAULT 0,
    stage_gate_json TEXT,
    validation_expectations_json TEXT,
    security_readiness_checks_json TEXT,
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


def _mk_milestone_event(
    event_type: str,
    milestone_id: str,
    event_timestamp: str = "2026-05-27T12:00:00+00:00",
    project_id: str = "proj-test",
    **payload_kwargs: Any,
) -> Dict[str, Any]:
    """Build a normalized event dict matching ProjectionEngine._row_to_event() format."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_timestamp": event_timestamp,
        "trace": {
            "milestone_id": milestone_id,
            "project_id": project_id,
        },
        "payload": payload_kwargs,
        "correlation_id": None,
        "project_id": project_id,
        "milestone_id": milestone_id,
        "_source": "business",
    }


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
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
        + _BUSINESS_MILESTONES_DDL
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
    from core.projections.milestone_projection import MilestoneProjection

    proj = MilestoneProjection()
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


def _fetch_milestone(db_path: Path, milestone_id: str) -> Dict[str, Any] | None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM business_milestones WHERE milestone_id = ?", (milestone_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# 1. Happy path — created → completed
# ---------------------------------------------------------------------------


def test_milestone_created_inserts_row(tmp_db):
    proj = _setup_projection(tmp_db)
    ms_id = str(uuid.uuid4())
    ev = _mk_milestone_event("milestone.created", ms_id, title="Phase 1 Complete", status="pending")
    result = _call_handle(proj, ev, tmp_db)
    assert result == 1
    row = _fetch_milestone(tmp_db, ms_id)
    assert row is not None
    assert row["status"] == "pending"
    assert row["title"] == "Phase 1 Complete"
    assert row["source_event_id"] == ev["event_id"]


def test_milestone_completed_updates_status(tmp_db):
    proj = _setup_projection(tmp_db)
    ms_id = str(uuid.uuid4())

    created = _mk_milestone_event("milestone.created", ms_id, title="Phase 1")
    completed = _mk_milestone_event(
        "milestone.completed", ms_id, event_timestamp="2026-05-27T15:00:00+00:00"
    )

    _call_handle(proj, created, tmp_db)
    _call_handle(proj, completed, tmp_db)

    row = _fetch_milestone(tmp_db, ms_id)
    assert row["status"] == "complete"
    assert row["last_event_id"] == completed["event_id"]


def test_milestone_deleted_updates_status(tmp_db):
    proj = _setup_projection(tmp_db)
    ms_id = str(uuid.uuid4())

    created = _mk_milestone_event("milestone.created", ms_id, title="Phase X")
    deleted = _mk_milestone_event(
        "milestone.deleted", ms_id, event_timestamp="2026-05-27T16:00:00+00:00"
    )

    _call_handle(proj, created, tmp_db)
    _call_handle(proj, deleted, tmp_db)

    row = _fetch_milestone(tmp_db, ms_id)
    assert row["status"] == "deleted"
    assert row["last_event_id"] == deleted["event_id"]


# ---------------------------------------------------------------------------
# 2. Idempotency
# ---------------------------------------------------------------------------


def test_duplicate_created_event_is_noop(tmp_db):
    proj = _setup_projection(tmp_db)
    ms_id = str(uuid.uuid4())
    ev = _mk_milestone_event("milestone.created", ms_id, title="Idempotent MS")

    _call_handle(proj, ev, tmp_db)
    result = _call_handle(proj, ev, tmp_db)

    assert result == 0
    conn = sqlite3.connect(str(tmp_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM business_milestones WHERE milestone_id = ?", (ms_id,)
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_duplicate_completed_event_is_noop(tmp_db):
    proj = _setup_projection(tmp_db)
    ms_id = str(uuid.uuid4())

    created = _mk_milestone_event("milestone.created", ms_id, title="M")
    completed = _mk_milestone_event("milestone.completed", ms_id)

    _call_handle(proj, created, tmp_db)
    _call_handle(proj, completed, tmp_db)
    result = _call_handle(proj, completed, tmp_db)

    assert result == 0
    row = _fetch_milestone(tmp_db, ms_id)
    assert row["status"] == "complete"


# ---------------------------------------------------------------------------
# 3. Out-of-order events
# ---------------------------------------------------------------------------


def test_completed_before_created_skeleton_then_backfill(tmp_db):
    proj = _setup_projection(tmp_db)
    ms_id = str(uuid.uuid4())

    completed = _mk_milestone_event("milestone.completed", ms_id)
    created = _mk_milestone_event("milestone.created", ms_id, title="The Real Title")

    _call_handle(proj, completed, tmp_db)
    skeleton = _fetch_milestone(tmp_db, ms_id)
    assert skeleton is not None
    assert skeleton["status"] == "complete"

    _call_handle(proj, created, tmp_db)
    row = _fetch_milestone(tmp_db, ms_id)
    assert row["status"] == "complete"
    assert row["title"] == "The Real Title"


# ---------------------------------------------------------------------------
# 4. Malformed events
# ---------------------------------------------------------------------------


def test_missing_milestone_id_skips_event(tmp_db):
    proj = _setup_projection(tmp_db)
    ev = {
        "event_id": str(uuid.uuid4()),
        "event_type": "milestone.created",
        "event_timestamp": "2026-05-27T12:00:00+00:00",
        "trace": {},
        "payload": {"title": "No milestone ID"},
        "correlation_id": None,
        "project_id": "proj-test",
        # milestone_id deliberately absent
        "_source": "business",
    }
    result = _call_handle(proj, ev, tmp_db)
    assert result == 0


def test_unknown_event_type_skips(tmp_db):
    proj = _setup_projection(tmp_db)
    ms_id = str(uuid.uuid4())
    ev = _mk_milestone_event("milestone.future_event", ms_id)
    result = _call_handle(proj, ev, tmp_db)
    assert result == 0
