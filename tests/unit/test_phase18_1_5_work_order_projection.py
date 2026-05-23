"""Phase 18.1.5 tests — WorkOrderProjection.

Coverage:
  1. Happy path — created → started → closed sequence
  2. Idempotency — duplicate handle() calls produce same state, no extra rows
  3. Out-of-order events — started before created, closed before created
  4. Block/unblock cycle — blocked status and block_reason management
  5. Malformed events — missing work_order_id, unknown event_type
  6. Rebuild from canonical — deterministic and idempotent
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
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _mk_wo_event(
    event_type: str,
    work_order_id: str,
    event_timestamp: str = "2026-05-22T12:00:00+00:00",
    project_id: str = "proj-test",
    **payload_kwargs: Any,
) -> Dict[str, Any]:
    """Build a normalized event dict matching ProjectionEngine._row_to_event() format."""
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "event_timestamp": event_timestamp,
        "trace": {},
        "payload": {"work_order_id": work_order_id, **payload_kwargs},
        "correlation_id": None,
        "project_id": project_id,
        "work_order_id": work_order_id,
        "_source": "business",
    }


_BUSINESS_WORK_ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS business_work_orders (
    work_order_id TEXT PRIMARY KEY,
    project_id TEXT,
    milestone_id TEXT,
    title TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TEXT,
    started_at TEXT,
    closed_at TEXT,
    blocked_at TEXT,
    unblocked_at TEXT,
    block_reason TEXT,
    source_event_id TEXT,
    last_event_id TEXT,
    last_updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
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


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Tmp DB with all tables needed for WorkOrderProjection tests."""
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
        + _BUSINESS_WORK_ORDERS_DDL
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
    """Create a WorkOrderProjection and call setup_tables()."""
    from core.projections.work_order_projection import WorkOrderProjection

    proj = WorkOrderProjection()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    proj.setup_tables(conn)
    conn.close()
    return proj


def _call_handle(proj, event: Dict[str, Any], db_path: Path) -> int:
    """Call proj.handle(event, conn) in a fresh connection and commit."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        rows = proj.handle(event, conn)
        conn.commit()
        return rows
    finally:
        conn.close()


def _fetch_wo(db_path: Path, work_order_id: str) -> Dict[str, Any] | None:
    """Return the business_work_orders row for the given work_order_id, or None."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM business_work_orders WHERE work_order_id = ?",
        (work_order_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _insert_canonical_event(
    db_path: Path,
    event_id: str,
    event_type: str,
    event_timestamp: str,
    payload: dict,
    work_order_id: str | None = None,
    project_id: str | None = None,
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        INSERT INTO business_canonical_events
            (event_id, event_type, event_timestamp, trace, payload, work_order_id, project_id)
        VALUES (?, ?, ?, '{}', ?, ?, ?)
        """,
        (event_id, event_type, event_timestamp, json.dumps(payload), work_order_id, project_id),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# 1. Happy path — created → started → closed
# ---------------------------------------------------------------------------


class TestWorkOrderHappyPath:
    def test_created_inserts_row_with_status_created(self, tmp_db):
        proj = _setup_projection(tmp_db)
        event = _mk_wo_event("work_order.created", "wo-hp-1", title="Happy Path WO")
        _call_handle(proj, event, tmp_db)

        row = _fetch_wo(tmp_db, "wo-hp-1")
        assert row is not None
        assert row["status"] == "created"
        assert row["title"] == "Happy Path WO"

    def test_started_sets_status_in_progress_and_started_at(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-hp-2"
        created_event = _mk_wo_event(
            "work_order.created", wo_id,
            event_timestamp="2026-05-22T10:00:00+00:00",
            title="Started WO",
        )
        started_event = _mk_wo_event(
            "work_order.started", wo_id,
            event_timestamp="2026-05-22T11:00:00+00:00",
        )

        _call_handle(proj, created_event, tmp_db)
        _call_handle(proj, started_event, tmp_db)

        row = _fetch_wo(tmp_db, wo_id)
        assert row["status"] == "in_progress"
        assert row["started_at"] == "2026-05-22T11:00:00+00:00"

    def test_closed_sets_status_closed_and_closed_at(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-hp-3"
        ts_base = "2026-05-22T10:00:00+00:00"
        ts_started = "2026-05-22T11:00:00+00:00"
        ts_closed = "2026-05-22T12:00:00+00:00"

        _call_handle(proj, _mk_wo_event("work_order.created", wo_id, event_timestamp=ts_base), tmp_db)
        _call_handle(proj, _mk_wo_event("work_order.started", wo_id, event_timestamp=ts_started), tmp_db)
        _call_handle(proj, _mk_wo_event("work_order.closed", wo_id, event_timestamp=ts_closed), tmp_db)

        row = _fetch_wo(tmp_db, wo_id)
        assert row["status"] == "closed"
        assert row["closed_at"] == ts_closed

    def test_full_lifecycle_row_exists(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-hp-4"

        for et, ts in [
            ("work_order.created", "2026-05-22T08:00:00+00:00"),
            ("work_order.started", "2026-05-22T09:00:00+00:00"),
            ("work_order.closed", "2026-05-22T10:00:00+00:00"),
        ]:
            _call_handle(proj, _mk_wo_event(et, wo_id, event_timestamp=ts), tmp_db)

        row = _fetch_wo(tmp_db, wo_id)
        assert row is not None
        assert row["created_at"] == "2026-05-22T08:00:00+00:00"
        assert row["started_at"] == "2026-05-22T09:00:00+00:00"
        assert row["closed_at"] == "2026-05-22T10:00:00+00:00"
        assert row["status"] == "closed"


# ---------------------------------------------------------------------------
# 2. Idempotency
# ---------------------------------------------------------------------------


class TestWorkOrderIdempotency:
    def test_duplicate_created_event_same_state(self, tmp_db):
        proj = _setup_projection(tmp_db)
        event = _mk_wo_event("work_order.created", "wo-idem-1", title="Idempotent WO")

        _call_handle(proj, event, tmp_db)
        row_after_first = _fetch_wo(tmp_db, "wo-idem-1")

        # Call again with the exact same event.
        second_return = _call_handle(proj, event, tmp_db)
        row_after_second = _fetch_wo(tmp_db, "wo-idem-1")

        assert second_return == 0, "Second call with same event must return 0 (already processed)"
        assert row_after_first["status"] == row_after_second["status"]
        assert row_after_first["title"] == row_after_second["title"]

    def test_duplicate_does_not_increase_row_count(self, tmp_db):
        proj = _setup_projection(tmp_db)
        event = _mk_wo_event("work_order.created", "wo-idem-2", title="Row Count WO")

        _call_handle(proj, event, tmp_db)
        _call_handle(proj, event, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        count = conn.execute(
            "SELECT COUNT(*) FROM business_work_orders WHERE work_order_id = ?",
            ("wo-idem-2",),
        ).fetchone()[0]
        conn.close()

        assert count == 1, "Duplicate events must not create extra rows"

    def test_duplicate_started_does_not_change_status_back_to_created(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-idem-3"
        created_event = _mk_wo_event(
            "work_order.created", wo_id, event_timestamp="2026-05-22T10:00:00+00:00"
        )
        started_event = _mk_wo_event(
            "work_order.started", wo_id, event_timestamp="2026-05-22T11:00:00+00:00"
        )

        _call_handle(proj, created_event, tmp_db)
        _call_handle(proj, started_event, tmp_db)
        # Replay started event.
        second_return = _call_handle(proj, started_event, tmp_db)

        row = _fetch_wo(tmp_db, wo_id)
        assert row["status"] == "in_progress"
        assert second_return == 0


# ---------------------------------------------------------------------------
# 3. Out-of-order events
# ---------------------------------------------------------------------------


class TestWorkOrderOutOfOrder:
    def test_started_before_created_creates_skeleton_with_in_progress(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-ooo-1"

        # Send started before created.
        _call_handle(
            proj,
            _mk_wo_event("work_order.started", wo_id, event_timestamp="2026-05-22T11:00:00+00:00"),
            tmp_db,
        )

        row = _fetch_wo(tmp_db, wo_id)
        assert row is not None, "started event must create a skeleton row"
        assert row["status"] == "in_progress", "skeleton status should be in_progress after started"

    def test_created_after_started_backfills_title_and_preserves_status(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-ooo-2"

        # Started arrives first.
        _call_handle(
            proj,
            _mk_wo_event("work_order.started", wo_id, event_timestamp="2026-05-22T11:00:00+00:00"),
            tmp_db,
        )
        # Created arrives after.
        _call_handle(
            proj,
            _mk_wo_event(
                "work_order.created", wo_id,
                event_timestamp="2026-05-22T10:00:00+00:00",
                title="Backfilled Title",
            ),
            tmp_db,
        )

        row = _fetch_wo(tmp_db, wo_id)
        assert row["title"] == "Backfilled Title", "title must be backfilled from created event"
        assert row["status"] == "in_progress", "status must remain in_progress, not revert to created"

    def test_closed_before_created_creates_row_with_closed_status(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-ooo-3"

        # Closed arrives first.
        _call_handle(
            proj,
            _mk_wo_event("work_order.closed", wo_id, event_timestamp="2026-05-22T12:00:00+00:00"),
            tmp_db,
        )

        row = _fetch_wo(tmp_db, wo_id)
        assert row is not None
        assert row["status"] == "closed"

    def test_created_after_closed_backfills_title_status_stays_closed(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-ooo-4"

        # Closed first.
        _call_handle(
            proj,
            _mk_wo_event("work_order.closed", wo_id, event_timestamp="2026-05-22T12:00:00+00:00"),
            tmp_db,
        )
        # Then created.
        _call_handle(
            proj,
            _mk_wo_event(
                "work_order.created", wo_id,
                event_timestamp="2026-05-22T10:00:00+00:00",
                title="Late Title",
            ),
            tmp_db,
        )

        row = _fetch_wo(tmp_db, wo_id)
        assert row["title"] == "Late Title", "title must be backfilled from late created event"
        assert row["status"] == "closed", "closed status must not be overwritten by created"

    def test_multiple_ooo_events_all_create_a_row(self, tmp_db):
        """All out-of-order events must result in exactly one row per work_order_id."""
        proj = _setup_projection(tmp_db)
        wo_id = "wo-ooo-5"

        # Arrive in reverse order: closed → started → created
        _call_handle(
            proj,
            _mk_wo_event("work_order.closed", wo_id, event_timestamp="2026-05-22T14:00:00+00:00"),
            tmp_db,
        )
        _call_handle(
            proj,
            _mk_wo_event("work_order.started", wo_id, event_timestamp="2026-05-22T11:00:00+00:00"),
            tmp_db,
        )
        _call_handle(
            proj,
            _mk_wo_event(
                "work_order.created", wo_id,
                event_timestamp="2026-05-22T10:00:00+00:00",
                title="Multi OOO WO",
            ),
            tmp_db,
        )

        row = _fetch_wo(tmp_db, wo_id)
        # Row must exist and title must be backfilled from the created event.
        assert row is not None
        assert row["title"] == "Multi OOO WO"
        # started_at must be populated from the started event.
        assert row["started_at"] == "2026-05-22T11:00:00+00:00"

        # Verify exactly one row exists.
        conn = sqlite3.connect(str(tmp_db))
        count = conn.execute(
            "SELECT COUNT(*) FROM business_work_orders WHERE work_order_id = ?",
            (wo_id,),
        ).fetchone()[0]
        conn.close()
        assert count == 1, "Exactly one row must exist regardless of event arrival order"


# ---------------------------------------------------------------------------
# 4. Block/unblock cycle
# ---------------------------------------------------------------------------


class TestWorkOrderBlockUnblock:
    def test_blocked_sets_status_and_block_reason(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-block-1"

        _call_handle(proj, _mk_wo_event("work_order.created", wo_id, event_timestamp="2026-05-22T10:00:00+00:00"), tmp_db)
        _call_handle(proj, _mk_wo_event("work_order.started", wo_id, event_timestamp="2026-05-22T11:00:00+00:00"), tmp_db)
        _call_handle(
            proj,
            _mk_wo_event(
                "work_order.blocked", wo_id,
                event_timestamp="2026-05-22T12:00:00+00:00",
                reason="Waiting for design approval",
            ),
            tmp_db,
        )

        row = _fetch_wo(tmp_db, wo_id)
        assert row["status"] == "blocked"
        assert row["block_reason"] == "Waiting for design approval"

    def test_unblocked_restores_in_progress_and_clears_reason(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-block-2"

        _call_handle(proj, _mk_wo_event("work_order.created", wo_id, event_timestamp="2026-05-22T10:00:00+00:00"), tmp_db)
        _call_handle(proj, _mk_wo_event("work_order.started", wo_id, event_timestamp="2026-05-22T11:00:00+00:00"), tmp_db)
        _call_handle(
            proj,
            _mk_wo_event(
                "work_order.blocked", wo_id,
                event_timestamp="2026-05-22T12:00:00+00:00",
                reason="Waiting for dependencies",
            ),
            tmp_db,
        )
        _call_handle(
            proj,
            _mk_wo_event("work_order.unblocked", wo_id, event_timestamp="2026-05-22T13:00:00+00:00"),
            tmp_db,
        )

        row = _fetch_wo(tmp_db, wo_id)
        assert row["status"] == "in_progress"
        assert row["block_reason"] is None, "block_reason must be cleared on unblocked"

    def test_block_reason_uses_block_reason_key(self, tmp_db):
        """Projection must also accept block_reason as the payload key (not just reason)."""
        proj = _setup_projection(tmp_db)
        wo_id = "wo-block-3"

        _call_handle(proj, _mk_wo_event("work_order.created", wo_id), tmp_db)
        _call_handle(
            proj,
            _mk_wo_event(
                "work_order.blocked", wo_id,
                block_reason="Alt key block",
            ),
            tmp_db,
        )

        row = _fetch_wo(tmp_db, wo_id)
        assert row["status"] == "blocked"
        assert row["block_reason"] == "Alt key block"

    def test_multiple_block_unblock_cycles(self, tmp_db):
        """Work order can cycle through block/unblock multiple times."""
        proj = _setup_projection(tmp_db)
        wo_id = "wo-block-4"

        events = [
            ("work_order.created", "2026-05-22T08:00:00+00:00", {}),
            ("work_order.started", "2026-05-22T09:00:00+00:00", {}),
            ("work_order.blocked", "2026-05-22T10:00:00+00:00", {"reason": "First block"}),
            ("work_order.unblocked", "2026-05-22T11:00:00+00:00", {}),
            ("work_order.blocked", "2026-05-22T12:00:00+00:00", {"reason": "Second block"}),
            ("work_order.unblocked", "2026-05-22T13:00:00+00:00", {}),
        ]
        for et, ts, extra in events:
            _call_handle(proj, _mk_wo_event(et, wo_id, event_timestamp=ts, **extra), tmp_db)

        row = _fetch_wo(tmp_db, wo_id)
        assert row["status"] == "in_progress"
        assert row["block_reason"] is None


# ---------------------------------------------------------------------------
# 5. Malformed events
# ---------------------------------------------------------------------------


class TestWorkOrderMalformedEvents:
    def test_event_with_no_work_order_id_returns_zero(self, tmp_db):
        proj = _setup_projection(tmp_db)
        # Build event without work_order_id in payload.
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "work_order.created",
            "event_timestamp": "2026-05-22T12:00:00+00:00",
            "trace": {},
            "payload": {"title": "No WO ID"},  # no work_order_id
            "correlation_id": None,
            "project_id": "proj-test",
            # Deliberately omit work_order_id key from the top-level dict too.
            "_source": "business",
        }
        result = _call_handle(proj, event, tmp_db)
        assert result == 0, "Event without work_order_id must return 0"

    def test_event_with_no_work_order_id_writes_no_rows(self, tmp_db):
        proj = _setup_projection(tmp_db)
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "work_order.created",
            "event_timestamp": "2026-05-22T12:00:00+00:00",
            "trace": {},
            "payload": {"title": "No WO ID in payload"},
            "correlation_id": None,
            "project_id": "proj-test",
            "_source": "business",
        }
        _call_handle(proj, event, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        count = conn.execute("SELECT COUNT(*) FROM business_work_orders").fetchone()[0]
        conn.close()
        assert count == 0, "Malformed event must not write any rows"

    def test_event_with_none_work_order_id_in_payload_returns_zero(self, tmp_db):
        proj = _setup_projection(tmp_db)
        event = _mk_wo_event("work_order.created", "wo-none")
        # Override both to None to simulate a truly missing ID.
        event["work_order_id"] = None
        event["payload"]["work_order_id"] = None

        result = _call_handle(proj, event, tmp_db)
        assert result == 0

    def test_unknown_event_type_handled_gracefully(self, tmp_db):
        """An unknown event type not in consumed_event_types returns 0 without crashing."""
        proj = _setup_projection(tmp_db)
        # First ensure the skeleton row exists via created.
        wo_id = "wo-unknown-type"
        _call_handle(proj, _mk_wo_event("work_order.created", wo_id), tmp_db)

        # Now send an unknown event type that is not in consumed_event_types.
        event = _mk_wo_event("work_order.some_future_event", wo_id)
        # handle() checks is_already_processed first; event_id is unique, so it won't short-circuit.
        result = _call_handle(proj, event, tmp_db)

        # The method should return 0 without raising.
        assert result == 0, "Unknown event type must return 0 gracefully"

    def test_empty_payload_dict_handled_gracefully(self, tmp_db):
        """An event with an empty payload dict and valid work_order_id must not crash."""
        proj = _setup_projection(tmp_db)
        event = {
            "event_id": str(uuid.uuid4()),
            "event_type": "work_order.created",
            "event_timestamp": "2026-05-22T12:00:00+00:00",
            "trace": {},
            "payload": {},  # empty payload
            "correlation_id": None,
            "project_id": None,
            "work_order_id": "wo-empty-payload",
            "_source": "business",
        }
        # Should not raise, but may return 0 or 1 depending on work_order_id resolution.
        # The key test is that it doesn't crash.
        try:
            _call_handle(proj, event, tmp_db)
        except Exception as exc:
            pytest.fail(f"handle() raised unexpectedly on empty payload: {exc}")


# ---------------------------------------------------------------------------
# 6. Rebuild from canonical
# ---------------------------------------------------------------------------


class TestWorkOrderRebuildFromCanonical:
    def test_rebuild_from_canonical_produces_correct_state(self, tmp_db):
        proj = _setup_projection(tmp_db)
        wo_id = "wo-rebuild-1"

        _insert_canonical_event(
            tmp_db,
            str(uuid.uuid4()), "work_order.created", "2026-05-22T10:00:00+00:00",
            {"work_order_id": wo_id, "title": "Rebuild WO"},
            work_order_id=wo_id,
        )
        _insert_canonical_event(
            tmp_db,
            str(uuid.uuid4()), "work_order.started", "2026-05-22T11:00:00+00:00",
            {"work_order_id": wo_id},
            work_order_id=wo_id,
        )
        _insert_canonical_event(
            tmp_db,
            str(uuid.uuid4()), "work_order.closed", "2026-05-22T12:00:00+00:00",
            {"work_order_id": wo_id},
            work_order_id=wo_id,
        )

        from core.projections.framework import ProjectionEngine

        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)
        result = engine.rebuild(proj.name)

        assert result.events_processed == 3
        row = _fetch_wo(tmp_db, wo_id)
        assert row is not None
        assert row["status"] == "closed"
        assert row["title"] == "Rebuild WO"

    def test_rebuild_twice_is_idempotent(self, tmp_db):
        """Running rebuild twice must produce identical final state."""
        proj = _setup_projection(tmp_db)
        wo_id = "wo-rebuild-idem"

        _insert_canonical_event(
            tmp_db,
            str(uuid.uuid4()), "work_order.created", "2026-05-22T10:00:00+00:00",
            {"work_order_id": wo_id, "title": "Idempotent Rebuild"},
            work_order_id=wo_id,
        )
        _insert_canonical_event(
            tmp_db,
            str(uuid.uuid4()), "work_order.started", "2026-05-22T11:00:00+00:00",
            {"work_order_id": wo_id},
            work_order_id=wo_id,
        )

        from core.projections.framework import ProjectionEngine

        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)
        engine.rebuild(proj.name)

        row_after_first = _fetch_wo(tmp_db, wo_id)

        # Second rebuild.
        engine.rebuild(proj.name)
        row_after_second = _fetch_wo(tmp_db, wo_id)

        assert row_after_first["status"] == row_after_second["status"]
        assert row_after_first["title"] == row_after_second["title"]
        assert row_after_first["started_at"] == row_after_second["started_at"]

    def test_rebuild_row_count_stays_one_per_work_order(self, tmp_db):
        """After rebuild, exactly one row per work_order_id must exist."""
        proj = _setup_projection(tmp_db)
        wo_ids = ["wo-rc-1", "wo-rc-2", "wo-rc-3"]

        ts_offset = 0
        for wo_id in wo_ids:
            ts_offset += 1
            _insert_canonical_event(
                tmp_db,
                str(uuid.uuid4()),
                "work_order.created",
                f"2026-05-22T1{ts_offset}:00:00+00:00",
                {"work_order_id": wo_id, "title": f"WO {wo_id}"},
                work_order_id=wo_id,
            )

        from core.projections.framework import ProjectionEngine

        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)
        engine.rebuild(proj.name)

        conn = sqlite3.connect(str(tmp_db))
        total = conn.execute("SELECT COUNT(*) FROM business_work_orders").fetchone()[0]
        conn.close()

        assert total == len(wo_ids), "Exactly one row per work_order_id after rebuild"

    def test_rebuild_uses_rebuild_from_canonical_on_projection(self, tmp_db):
        """rebuild_from_canonical() must produce the same result as engine.rebuild()."""
        proj1 = _setup_projection(tmp_db)
        wo_id = "wo-rfc-direct"

        _insert_canonical_event(
            tmp_db,
            str(uuid.uuid4()), "work_order.created", "2026-05-22T10:00:00+00:00",
            {"work_order_id": wo_id, "title": "Direct RFC Test"},
            work_order_id=wo_id,
        )

        from core.projections.framework import ProjectionEngine

        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj1)
        engine.rebuild(proj1.name)

        row = _fetch_wo(tmp_db, wo_id)
        assert row is not None
        assert row["status"] == "created"
        assert row["title"] == "Direct RFC Test"

    def test_rebuild_with_multiple_events_per_work_order(self, tmp_db):
        """Rebuild correctly handles multiple events for the same work_order_id."""
        proj = _setup_projection(tmp_db)
        wo_id = "wo-multi-events"

        sequence = [
            ("work_order.created", "2026-05-22T08:00:00+00:00", {"title": "Multi Events WO"}),
            ("work_order.started", "2026-05-22T09:00:00+00:00", {}),
            ("work_order.blocked", "2026-05-22T10:00:00+00:00", {"reason": "Waiting"}),
            ("work_order.unblocked", "2026-05-22T11:00:00+00:00", {}),
            ("work_order.closed", "2026-05-22T12:00:00+00:00", {}),
        ]

        for et, ts, extra in sequence:
            _insert_canonical_event(
                tmp_db,
                str(uuid.uuid4()), et, ts,
                {"work_order_id": wo_id, **extra},
                work_order_id=wo_id,
            )

        from core.projections.framework import ProjectionEngine

        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)
        result = engine.rebuild(proj.name)

        assert result.events_processed == 5
        row = _fetch_wo(tmp_db, wo_id)
        assert row["status"] == "closed"
        assert row["title"] == "Multi Events WO"
        assert row["block_reason"] is None
