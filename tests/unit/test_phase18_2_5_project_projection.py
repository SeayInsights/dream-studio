"""Phase 18.2.5 tests — ProjectProjection.

Coverage:
  1.  project.created inserts row with status='active', columns populated
  2.  project.created duplicate is idempotent (returns 0)
  3.  project.created → project.deactivated → status='paused'
  4.  project.created → project.activated → status='active' (re-activate)
  5.  project.created → project.deleted → status='deleted' (soft delete)
  6.  Full lifecycle: created → deactivated → activated → deleted
  7.  Duplicate project.deactivated is idempotent (returns 0)
  8.  Out-of-order: project.deactivated before project.created → skeleton + paused; created backfills
  9.  Out-of-order: project.deleted before project.created → skeleton + deleted; created backfills
  10. Single-active invariant at projection level: deactivate A, activate B
  11. Missing project_id → skip (returns 0)
  12. Unknown event_type → skip (returns 0)
"""

from __future__ import annotations

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
# DDL — mirrors the live schema including migration 076 additions
# ---------------------------------------------------------------------------

_BUSINESS_PROJECTS_DDL = """
CREATE TABLE IF NOT EXISTS business_projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
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
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT 'ingestor'
);
"""

_TS = "2026-05-27T12:00:00+00:00"
_PROJECT_ID = "proj-test-18-2-5"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_project_event(
    event_type: str,
    project_id: str = _PROJECT_ID,
    event_timestamp: str = _TS,
    **payload_kwargs: Any,
) -> Dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_timestamp": event_timestamp,
        "trace": {
            "project_id": project_id,
            "domain": "sdlc",
        },
        "payload": payload_kwargs,
        "correlation_id": None,
        "project_id": project_id,
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
        "PRAGMA foreign_keys = OFF;\n"
        + _BUSINESS_PROJECTS_DDL
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
    from core.projections.project_projection import ProjectProjection

    proj = ProjectProjection()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    proj.setup_tables(conn)
    conn.close()
    return proj


def _call_handle(proj, event: Dict[str, Any], db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        result = proj.handle(event, conn)
        conn.commit()
        return result
    finally:
        conn.close()


def _fetch_project(db_path: Path, project_id: str) -> Dict[str, Any] | None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM business_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_created_inserts_row(tmp_db):
    """project.created inserts a row with status='active' and tracking columns set."""
    proj = _setup_projection(tmp_db)

    evt = _mk_project_event(
        "project.created", name="My Project", description="desc", status="active"
    )
    result = _call_handle(proj, evt, tmp_db)

    assert result == 1
    row = _fetch_project(tmp_db, _PROJECT_ID)
    assert row is not None
    assert row["project_id"] == _PROJECT_ID
    assert row["name"] == "My Project"
    assert row["status"] == "active"
    assert row["source_event_id"] == evt["event_id"]
    assert row["last_event_id"] == evt["event_id"]


def test_duplicate_created_is_noop(tmp_db):
    """Replaying project.created returns 0 and does not alter the row."""
    proj = _setup_projection(tmp_db)
    evt = _mk_project_event("project.created", name="My Project", status="active")

    _call_handle(proj, evt, tmp_db)
    result = _call_handle(proj, evt, tmp_db)

    assert result == 0
    conn = sqlite3.connect(str(tmp_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM business_projects WHERE project_id = ?", (_PROJECT_ID,)
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_deactivated_sets_paused(tmp_db):
    """project.created → project.deactivated yields status='paused'."""
    proj = _setup_projection(tmp_db)

    _call_handle(proj, _mk_project_event("project.created", name="P", status="active"), tmp_db)
    deact_evt = _mk_project_event("project.deactivated")
    result = _call_handle(proj, deact_evt, tmp_db)

    assert result == 1
    row = _fetch_project(tmp_db, _PROJECT_ID)
    assert row["status"] == "paused"
    assert row["last_event_id"] == deact_evt["event_id"]


def test_activated_sets_active(tmp_db):
    """project.created → project.deactivated → project.activated restores status='active'."""
    proj = _setup_projection(tmp_db)

    _call_handle(proj, _mk_project_event("project.created", name="P", status="active"), tmp_db)
    _call_handle(proj, _mk_project_event("project.deactivated"), tmp_db)

    act_evt = _mk_project_event("project.activated")
    result = _call_handle(proj, act_evt, tmp_db)

    assert result == 1
    row = _fetch_project(tmp_db, _PROJECT_ID)
    assert row["status"] == "active"
    assert row["last_event_id"] == act_evt["event_id"]


def test_deleted_soft_deletes(tmp_db):
    """project.created → project.deleted sets status='deleted'; row stays in table."""
    proj = _setup_projection(tmp_db)

    _call_handle(proj, _mk_project_event("project.created", name="P", status="active"), tmp_db)
    del_evt = _mk_project_event("project.deleted")
    result = _call_handle(proj, del_evt, tmp_db)

    assert result == 1
    row = _fetch_project(tmp_db, _PROJECT_ID)
    assert row is not None
    assert row["status"] == "deleted"
    assert row["last_event_id"] == del_evt["event_id"]


def test_full_lifecycle(tmp_db):
    """Full lifecycle: created → deactivated → activated → deleted."""
    proj = _setup_projection(tmp_db)

    _call_handle(proj, _mk_project_event("project.created", name="Full", status="active"), tmp_db)

    deact_evt = _mk_project_event("project.deactivated")
    _call_handle(proj, deact_evt, tmp_db)
    assert _fetch_project(tmp_db, _PROJECT_ID)["status"] == "paused"

    act_evt = _mk_project_event("project.activated")
    _call_handle(proj, act_evt, tmp_db)
    assert _fetch_project(tmp_db, _PROJECT_ID)["status"] == "active"

    del_evt = _mk_project_event("project.deleted")
    _call_handle(proj, del_evt, tmp_db)

    row = _fetch_project(tmp_db, _PROJECT_ID)
    assert row["status"] == "deleted"
    assert row["last_event_id"] == del_evt["event_id"]


def test_duplicate_deactivated_is_noop(tmp_db):
    """Replaying project.deactivated returns 0."""
    proj = _setup_projection(tmp_db)

    _call_handle(proj, _mk_project_event("project.created", name="P", status="active"), tmp_db)
    evt = _mk_project_event("project.deactivated")
    _call_handle(proj, evt, tmp_db)
    result = _call_handle(proj, evt, tmp_db)

    assert result == 0


def test_out_of_order_deactivated_before_created(tmp_db):
    """Out-of-order: project.deactivated before project.created → skeleton + paused; created backfills."""
    proj = _setup_projection(tmp_db)

    deact_evt = _mk_project_event("project.deactivated")
    result_deact = _call_handle(proj, deact_evt, tmp_db)
    assert result_deact == 1

    row = _fetch_project(tmp_db, _PROJECT_ID)
    assert row is not None
    assert row["status"] == "paused"
    assert row["source_event_id"] is None  # skeleton — created not yet applied

    created_evt = _mk_project_event("project.created", name="Late Create", status="active")
    result_cr = _call_handle(proj, created_evt, tmp_db)
    assert result_cr == 1

    row = _fetch_project(tmp_db, _PROJECT_ID)
    assert row["name"] == "Late Create"
    assert row["source_event_id"] == created_evt["event_id"]
    assert row["status"] == "paused"  # deactivated state preserved


def test_out_of_order_deleted_before_created(tmp_db):
    """Out-of-order: project.deleted before project.created → skeleton + deleted; created backfills."""
    proj = _setup_projection(tmp_db)

    del_evt = _mk_project_event("project.deleted")
    _call_handle(proj, del_evt, tmp_db)

    row = _fetch_project(tmp_db, _PROJECT_ID)
    assert row is not None
    assert row["status"] == "deleted"

    created_evt = _mk_project_event("project.created", name="Ghost", status="active")
    _call_handle(proj, created_evt, tmp_db)

    row = _fetch_project(tmp_db, _PROJECT_ID)
    assert row["name"] == "Ghost"
    assert row["source_event_id"] == created_evt["event_id"]
    assert row["status"] == "deleted"  # deleted state preserved


def test_single_active_invariant_at_projection_level(tmp_db):
    """Projection correctly applies deactivated (A→paused) then activated (B→active).

    This mirrors what set_active_project emits: project.deactivated for A, then
    project.activated for B. ProjectProjection applies them independently.
    """
    proj = _setup_projection(tmp_db)
    proj_a = "proj-a-18-2-5"
    proj_b = "proj-b-18-2-5"

    _call_handle(
        proj,
        _mk_project_event("project.created", project_id=proj_a, name="A", status="active"),
        tmp_db,
    )
    _call_handle(
        proj,
        _mk_project_event("project.created", project_id=proj_b, name="B", status="active"),
        tmp_db,
    )

    _call_handle(proj, _mk_project_event("project.deactivated", project_id=proj_a), tmp_db)
    _call_handle(proj, _mk_project_event("project.activated", project_id=proj_b), tmp_db)

    row_a = _fetch_project(tmp_db, proj_a)
    row_b = _fetch_project(tmp_db, proj_b)
    assert row_a["status"] == "paused"
    assert row_b["status"] == "active"


def test_missing_project_id_skips(tmp_db):
    """Event with no project_id anywhere returns 0."""
    proj = _setup_projection(tmp_db)
    evt = {
        "event_id": str(uuid.uuid4()),
        "event_type": "project.created",
        "event_timestamp": _TS,
        "trace": {},
        "payload": {},
        "_source": "business",
    }
    result = _call_handle(proj, evt, tmp_db)
    assert result == 0


def test_unknown_event_type_skips(tmp_db):
    """Unrecognized event_type returns 0 (skeleton may be created but no status change)."""
    proj = _setup_projection(tmp_db)
    evt = _mk_project_event("project.archived")
    result = _call_handle(proj, evt, tmp_db)
    assert result == 0


def test_single_event_produces_exactly_one_row(tmp_db):
    """Regression: one project.created event must produce exactly 1 row, not 3.

    Bug4 context: INSERT OR IGNORE + UPDATE pattern. Both statements touch the
    same row — they must NOT produce duplicates or triplicates.
    """
    proj = _setup_projection(tmp_db)
    evt = _mk_project_event("project.created", name="Solo", status="active")
    _call_handle(proj, evt, tmp_db)

    conn = sqlite3.connect(str(tmp_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM business_projects WHERE project_id = ?", (_PROJECT_ID,)
    ).fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM business_projects").fetchone()[0]
    conn.close()

    assert count == 1, f"Expected 1 row for project_id, got {count}"
    assert total == 1, f"Expected 1 total row in business_projects, got {total}"
