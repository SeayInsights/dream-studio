"""Phase 18.2.4 tests — DesignBriefProjection.

Coverage:
  1. created → status='draft', columns populated
  2. created → updated → field written
  3. created → locked → status='locked'
  4. Duplicate created event is a no-op
  5. Duplicate updated event is a no-op
  6. Out-of-order: updated before created → skeleton then backfill
  7. Out-of-order: locked before created → skeleton then backfill
  8. Invalid field in design_brief.updated → skip (returns 0)
  9. Missing brief_id → skip (returns 0)
  10. Unknown event_type → skip (returns 0)
  11. Full lifecycle: created → multiple updates → locked
"""

from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# DDL — mirrors the live schema including migration 074 additions
# ---------------------------------------------------------------------------

_BUSINESS_PROJECTS_DDL = """
CREATE TABLE IF NOT EXISTS business_projects (
    project_id TEXT PRIMARY KEY,
    name TEXT NOT NULL DEFAULT 'Test Project',
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);
"""

_BUSINESS_DESIGN_BRIEFS_DDL = """
CREATE TABLE IF NOT EXISTS business_design_briefs (
    brief_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES business_projects(project_id),
    status TEXT NOT NULL DEFAULT 'draft',
    purpose TEXT,
    audience TEXT,
    tone TEXT,
    design_system TEXT,
    font_pairing TEXT,
    brand_tokens TEXT,
    raw_output TEXT,
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
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT 'ingestor'
);
"""

_TS = "2026-05-27T12:00:00+00:00"
_PROJECT_ID = "proj-test-18-2-4"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mk_brief_event(
    event_type: str,
    brief_id: str,
    project_id: str = _PROJECT_ID,
    event_timestamp: str = _TS,
    **payload_kwargs: Any,
) -> dict[str, Any]:
    """Build a normalized event dict for DesignBriefProjection tests."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_timestamp": event_timestamp,
        "trace": {
            "brief_id": brief_id,
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
    """Tmp DB with all tables needed for DesignBriefProjection tests."""
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
        + _BUSINESS_DESIGN_BRIEFS_DDL
        + _BUSINESS_CANONICAL_DDL
        + _AI_CANONICAL_DDL
        + _PROJECTION_STATE_DDL
        + _RETRY_QUEUE_DDL
        + _DEAD_LETTER_DDL
        + _CHECKPOINTS_DDL
    )
    conn.execute("INSERT OR IGNORE INTO business_projects (project_id) VALUES (?)", (_PROJECT_ID,))
    conn.commit()
    conn.close()

    yield db_path

    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass


def _setup_projection(db_path: Path):
    from core.projections.design_brief_projection import DesignBriefProjection

    proj = DesignBriefProjection()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    proj.setup_tables(conn)
    conn.close()
    return proj


def _call_handle(proj, event: dict[str, Any], db_path: Path) -> int:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        result = proj.handle(event, conn)
        conn.commit()
        return result
    finally:
        conn.close()


def _fetch_brief(db_path: Path, brief_id: str) -> dict[str, Any] | None:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT * FROM business_design_briefs WHERE brief_id = ?", (brief_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_created_inserts_row(tmp_db):
    """design_brief.created inserts a draft row with correct columns."""
    proj = _setup_projection(tmp_db)
    brief_id = str(uuid.uuid4())

    evt = _mk_brief_event(
        "design_brief.created",
        brief_id,
        status="draft",
    )
    result = _call_handle(proj, evt, tmp_db)

    assert result == 1
    row = _fetch_brief(tmp_db, brief_id)
    assert row is not None
    assert row["brief_id"] == brief_id
    assert row["project_id"] == _PROJECT_ID
    assert row["status"] == "draft"
    assert row["source_event_id"] == evt["event_id"]
    assert row["last_event_id"] == evt["event_id"]


def test_updated_writes_field(tmp_db):
    """design_brief.updated writes the specified field to the row."""
    proj = _setup_projection(tmp_db)
    brief_id = str(uuid.uuid4())

    created_evt = _mk_brief_event("design_brief.created", brief_id, project_id=_PROJECT_ID)
    _call_handle(proj, created_evt, tmp_db)

    updated_evt = _mk_brief_event(
        "design_brief.updated",
        brief_id,
        field="audience",
        new_value="designers",
    )
    result = _call_handle(proj, updated_evt, tmp_db)

    assert result == 1
    row = _fetch_brief(tmp_db, brief_id)
    assert row["audience"] == "designers"
    assert row["last_event_id"] == updated_evt["event_id"]


def test_locked_updates_status(tmp_db):
    """design_brief.locked sets status='locked'."""
    proj = _setup_projection(tmp_db)
    brief_id = str(uuid.uuid4())

    _call_handle(
        proj,
        _mk_brief_event(
            "design_brief.created",
            brief_id,
        ),
        tmp_db,
    )
    locked_evt = _mk_brief_event(
        "design_brief.locked",
        brief_id,
    )
    result = _call_handle(proj, locked_evt, tmp_db)

    assert result == 1
    row = _fetch_brief(tmp_db, brief_id)
    assert row["status"] == "locked"
    assert row["last_event_id"] == locked_evt["event_id"]


def test_duplicate_created_event_is_noop(tmp_db):
    """Replaying design_brief.created returns 0 and does not alter the row."""
    proj = _setup_projection(tmp_db)
    brief_id = str(uuid.uuid4())
    evt = _mk_brief_event(
        "design_brief.created",
        brief_id,
    )

    _call_handle(proj, evt, tmp_db)
    result = _call_handle(proj, evt, tmp_db)

    assert result == 0
    conn = sqlite3.connect(str(tmp_db))
    count = conn.execute(
        "SELECT COUNT(*) FROM business_design_briefs WHERE brief_id = ?", (brief_id,)
    ).fetchone()[0]
    conn.close()
    assert count == 1


def test_duplicate_updated_event_is_noop(tmp_db):
    """Replaying design_brief.updated returns 0."""
    proj = _setup_projection(tmp_db)
    brief_id = str(uuid.uuid4())

    _call_handle(
        proj,
        _mk_brief_event(
            "design_brief.created",
            brief_id,
        ),
        tmp_db,
    )
    evt = _mk_brief_event("design_brief.updated", brief_id, field="tone", new_value="bold")
    _call_handle(proj, evt, tmp_db)
    result = _call_handle(proj, evt, tmp_db)

    assert result == 0


def test_updated_before_created_skeleton_then_backfill(tmp_db):
    """Out-of-order: updated arrives first → skeleton row; created fills it in."""
    proj = _setup_projection(tmp_db)
    brief_id = str(uuid.uuid4())

    updated_evt = _mk_brief_event(
        "design_brief.updated",
        brief_id,
        field="purpose",
        new_value="drive signups",
    )
    result_up = _call_handle(proj, updated_evt, tmp_db)
    assert result_up == 1

    # Skeleton should be present
    row = _fetch_brief(tmp_db, brief_id)
    assert row is not None
    assert row["purpose"] == "drive signups"
    assert row["status"] == "draft"

    # Now the created event arrives — it should backfill project_id / source_event_id
    created_evt = _mk_brief_event("design_brief.created", brief_id, project_id=_PROJECT_ID)
    result_cr = _call_handle(proj, created_evt, tmp_db)
    assert result_cr == 1

    row = _fetch_brief(tmp_db, brief_id)
    assert row["source_event_id"] == created_evt["event_id"]
    assert row["purpose"] == "drive signups"  # preserved by backfill


def test_locked_before_created_skeleton_then_backfill(tmp_db):
    """Out-of-order: locked arrives first → skeleton + lock; created backfills."""
    proj = _setup_projection(tmp_db)
    brief_id = str(uuid.uuid4())

    locked_evt = _mk_brief_event(
        "design_brief.locked",
        brief_id,
    )
    _call_handle(proj, locked_evt, tmp_db)

    row = _fetch_brief(tmp_db, brief_id)
    assert row is not None
    assert row["status"] == "locked"

    created_evt = _mk_brief_event("design_brief.created", brief_id, project_id=_PROJECT_ID)
    result = _call_handle(proj, created_evt, tmp_db)
    assert result == 1

    row = _fetch_brief(tmp_db, brief_id)
    assert row["source_event_id"] == created_evt["event_id"]
    assert row["status"] == "locked"  # lock preserved; create does not downgrade


def test_invalid_field_in_updated_skips(tmp_db):
    """design_brief.updated with an unknown field returns 0 (safe skip)."""
    proj = _setup_projection(tmp_db)
    brief_id = str(uuid.uuid4())

    _call_handle(
        proj,
        _mk_brief_event(
            "design_brief.created",
            brief_id,
        ),
        tmp_db,
    )
    evt = _mk_brief_event(
        "design_brief.updated",
        brief_id,
        field="__injected__",
        new_value="bad",
    )
    result = _call_handle(proj, evt, tmp_db)

    assert result == 0


def test_missing_brief_id_skips(tmp_db):
    """Event with no brief_id in trace or payload returns 0."""
    proj = _setup_projection(tmp_db)
    evt = {
        "event_id": str(uuid.uuid4()),
        "event_type": "design_brief.created",
        "event_timestamp": _TS,
        "trace": {},
        "payload": {},
        "_source": "business",
    }
    result = _call_handle(proj, evt, tmp_db)
    assert result == 0


def test_unknown_event_type_skips(tmp_db):
    """Unrecognized event_type returns 0 and writes nothing."""
    proj = _setup_projection(tmp_db)
    brief_id = str(uuid.uuid4())
    evt = _mk_brief_event(
        "design_brief.archived",
        brief_id,
    )
    result = _call_handle(proj, evt, tmp_db)
    assert result == 0


def test_full_lifecycle(tmp_db):
    """Full lifecycle: created → 3 field updates → locked."""
    proj = _setup_projection(tmp_db)
    brief_id = str(uuid.uuid4())

    _call_handle(
        proj,
        _mk_brief_event(
            "design_brief.created",
            brief_id,
        ),
        tmp_db,
    )
    for field, value in [
        ("purpose", "increase trial signups"),
        ("audience", "mid-market SaaS buyers"),
        ("tone", "professional-casual"),
    ]:
        _call_handle(
            proj,
            _mk_brief_event("design_brief.updated", brief_id, field=field, new_value=value),
            tmp_db,
        )
    _call_handle(
        proj,
        _mk_brief_event(
            "design_brief.locked",
            brief_id,
        ),
        tmp_db,
    )

    row = _fetch_brief(tmp_db, brief_id)
    assert row["purpose"] == "increase trial signups"
    assert row["audience"] == "mid-market SaaS buyers"
    assert row["tone"] == "professional-casual"
    assert row["status"] == "locked"
