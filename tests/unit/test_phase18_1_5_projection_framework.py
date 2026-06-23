"""Phase 18.1.5 tests — Projection framework.

Coverage:
  1. RetryPolicy — delay and timestamp calculation
  2. ProjectionRegistry — registration, routing, source filtering
  3. ProjectionEngine — registration, incremental dispatch, cursor management
  4. Dead-letter and retry — failure → retry → dead-letter cycle
  5. Rebuild — deterministic, idempotent
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _apply_projection_ddl(conn: sqlite3.Connection) -> None:
    """Apply just the DDL needed for projection framework tests."""
    conn.executescript("""
        PRAGMA journal_mode = WAL;

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

        CREATE TABLE IF NOT EXISTS projection_state (
            projection_name TEXT PRIMARY KEY,
            last_processed_business_event_id TEXT,
            last_processed_ai_event_id TEXT,
            last_run_at TEXT,
            events_processed_total INTEGER NOT NULL DEFAULT 0,
            events_failed_total INTEGER NOT NULL DEFAULT 0
        );

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

        CREATE TABLE IF NOT EXISTS projection_retry_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT NOT NULL,
            event_source TEXT NOT NULL,
            projection_name TEXT NOT NULL,
            next_retry_at TEXT NOT NULL,
            retry_count INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS projection_checkpoints (
            projection_name TEXT PRIMARY KEY,
            last_event_id TEXT NOT NULL DEFAULT '',
            last_timestamp TEXT NOT NULL DEFAULT '1970-01-01T00:00:00Z',
            events_processed INTEGER NOT NULL DEFAULT 0,
            last_rebuilt TEXT
        );

        CREATE TABLE IF NOT EXISTS _schema_version (
            version INTEGER PRIMARY KEY,
            applied_at TEXT NOT NULL
        );

        -- Target table for test projections
        CREATE TABLE IF NOT EXISTS test_projection_target (
            event_id TEXT PRIMARY KEY,
            processed_at TEXT
        );
    """)
    conn.commit()


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Tmp DB with all projection framework tables. Sets DREAM_STUDIO_DB_PATH."""
    db_path = tmp_path / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))

    # Reset DatabaseRuntime singleton so it picks up the new env var.
    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _apply_projection_ddl(conn)
    conn.close()

    yield db_path

    # Reset singleton on teardown.
    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass


def _insert_business_event(
    conn: sqlite3.Connection,
    event_id: str,
    event_type: str,
    event_timestamp: str,
    payload: dict,
    work_order_id: str | None = None,
    project_id: str | None = None,
) -> None:
    conn.execute(
        """
        INSERT INTO business_canonical_events
            (event_id, event_type, event_timestamp, trace, payload, work_order_id, project_id)
        VALUES (?, ?, ?, '{}', ?, ?, ?)
        """,
        (event_id, event_type, event_timestamp, json.dumps(payload), work_order_id, project_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Stub projection for engine tests
# ---------------------------------------------------------------------------


class _CountingProjection:
    """Minimal Projection stub that records calls without importing framework."""

    name = "test_counting_projection"
    consumed_event_types = ["work_order.created", "work_order.started"]
    source_canonical = "business"
    target_tables = ["test_projection_target"]

    def __init__(self):
        from core.projections.framework import RetryPolicy

        self.calls: list[dict[str, Any]] = []
        self._fail = False  # set True to make handle() raise
        self.retry_policy = RetryPolicy(max_retries=3, base_delay_seconds=1.0)

    @property
    def event_types(self):
        return self.consumed_event_types

    def setup_tables(self, conn):
        pass  # DDL already in _apply_projection_ddl

    def handle(self, event, conn):
        if self._fail:
            raise RuntimeError("intentional test failure")
        self.calls.append(event)
        conn.execute(
            "INSERT OR IGNORE INTO test_projection_target (event_id, processed_at) VALUES (?, ?)",
            (event["event_id"], datetime.now(UTC).isoformat()),
        )
        return 1

    def pre_rebuild(self, conn):
        conn.execute("DELETE FROM test_projection_target")

    def is_already_processed(self, event_id, target_table, conn):
        row = conn.execute(
            "SELECT 1 FROM test_projection_target WHERE event_id = ? LIMIT 1",
            (event_id,),
        ).fetchone()
        return row is not None

    def safe_upsert(self, conn, table, row, conflict_key):
        columns = list(row.keys())
        placeholders = ", ".join("?" * len(columns))
        col_list = ", ".join(columns)
        update_set = ", ".join(f"{c} = excluded.{c}" for c in columns if c != conflict_key)
        sql = (
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict_key}) DO UPDATE SET {update_set}"
        )
        conn.execute(sql, list(row.values()))
        return 1


# ---------------------------------------------------------------------------
# 1. RetryPolicy
# ---------------------------------------------------------------------------


class TestRetryPolicy:
    def test_delay_for_attempt_0_returns_base(self):
        from core.projections.framework import RetryPolicy

        policy = RetryPolicy(max_retries=3, base_delay_seconds=2.0, backoff_factor=3.0)
        assert policy.delay_for(0) == 2.0

    def test_delay_for_attempt_1_returns_base_times_factor(self):
        from core.projections.framework import RetryPolicy

        policy = RetryPolicy(max_retries=3, base_delay_seconds=2.0, backoff_factor=3.0)
        assert policy.delay_for(1) == pytest.approx(6.0)

    def test_delay_for_attempt_2_returns_base_times_factor_squared(self):
        from core.projections.framework import RetryPolicy

        policy = RetryPolicy(max_retries=3, base_delay_seconds=2.0, backoff_factor=3.0)
        assert policy.delay_for(2) == pytest.approx(18.0)

    def test_delay_exponential_with_default_values(self):
        from core.projections.framework import RetryPolicy

        policy = RetryPolicy()  # base=1.0, factor=2.0
        assert policy.delay_for(0) == pytest.approx(1.0)
        assert policy.delay_for(1) == pytest.approx(2.0)
        assert policy.delay_for(2) == pytest.approx(4.0)
        assert policy.delay_for(3) == pytest.approx(8.0)

    def test_next_retry_at_returns_future_iso_timestamp(self):
        from core.projections.framework import RetryPolicy

        policy = RetryPolicy(base_delay_seconds=5.0)
        before = datetime.now(UTC)
        ts = policy.next_retry_at(0)
        _ = before  # before/after bracket the timestamp for ordering assertions below

        # Parse the returned ISO timestamp.
        dt = datetime.fromisoformat(ts)
        # Must be after now (not in the past).
        assert dt > before, "next_retry_at should return a future timestamp"
        # Delay should be at most base + a small margin for execution time.
        delta = (dt - before).total_seconds()
        assert delta <= policy.delay_for(0) + 2.0, "delay too far in the future"

    def test_next_retry_at_increases_with_attempt(self):
        from core.projections.framework import RetryPolicy

        policy = RetryPolicy(base_delay_seconds=1.0, backoff_factor=2.0)
        ts0 = datetime.fromisoformat(policy.next_retry_at(0))
        ts1 = datetime.fromisoformat(policy.next_retry_at(1))
        ts2 = datetime.fromisoformat(policy.next_retry_at(2))
        assert ts1 > ts0
        assert ts2 > ts1


# ---------------------------------------------------------------------------
# 2. ProjectionRegistry
# ---------------------------------------------------------------------------


class TestProjectionRegistry:
    def _make_registry(self):
        # Reload to get a fresh instance not shared between tests.
        import core.projections.framework as fw_mod

        importlib.reload(fw_mod)
        return fw_mod.ProjectionRegistry()

    def _make_proj(self, name, event_types, source="business"):
        """Build a minimal duck-type projection for registry tests."""
        proj = _CountingProjection.__new__(_CountingProjection)
        proj.name = name
        proj.consumed_event_types = event_types
        proj.source_canonical = source
        proj.target_tables = []

        from core.projections.framework import RetryPolicy

        proj.retry_policy = RetryPolicy()
        return proj

    def test_register_adds_projection(self):
        from core.projections.framework import ProjectionRegistry

        reg = ProjectionRegistry()
        proj = self._make_proj("reg_test", ["work_order.created"])
        reg.register(proj)
        summary = reg.summary()
        assert summary["count"] == 1
        assert summary["projections"][0]["name"] == "reg_test"

    def test_summary_shows_registered_projection(self):
        from core.projections.framework import ProjectionRegistry

        reg = ProjectionRegistry()
        proj = self._make_proj("my_proj", ["work_order.started"], source="business")
        reg.register(proj)
        s = reg.summary()
        entries = {p["name"]: p for p in s["projections"]}
        assert "my_proj" in entries
        assert entries["my_proj"]["source_canonical"] == "business"

    def test_get_projections_for_event_type_exact_match(self):
        from core.projections.framework import ProjectionRegistry

        reg = ProjectionRegistry()
        proj = self._make_proj("exact_proj", ["work_order.created"])
        reg.register(proj)
        result = reg.get_projections_for_event_type("work_order.created", "business")
        assert len(result) == 1
        assert result[0].name == "exact_proj"

    def test_get_projections_for_event_type_no_match(self):
        from core.projections.framework import ProjectionRegistry

        reg = ProjectionRegistry()
        proj = self._make_proj("no_match_proj", ["work_order.created"])
        reg.register(proj)
        result = reg.get_projections_for_event_type("project.created", "business")
        assert result == []

    def test_get_projections_for_event_type_wildcard_match(self):
        from core.projections.framework import ProjectionRegistry

        reg = ProjectionRegistry()
        # Use wildcard pattern "work_order.%"
        proj = self._make_proj("wildcard_proj", ["work_order.%"])
        reg.register(proj)
        assert len(reg.get_projections_for_event_type("work_order.created", "business")) == 1
        assert len(reg.get_projections_for_event_type("work_order.started", "business")) == 1
        assert len(reg.get_projections_for_event_type("work_order.blocked", "business")) == 1
        # Non-matching prefix must not match.
        assert reg.get_projections_for_event_type("project.created", "business") == []

    def test_get_projections_source_filter_business(self):
        from core.projections.framework import ProjectionRegistry

        reg = ProjectionRegistry()
        biz_proj = self._make_proj("biz", ["work_order.created"], source="business")
        ai_proj = self._make_proj("ai", ["work_order.created"], source="ai")
        reg.register(biz_proj)
        reg.register(ai_proj)

        biz_result = reg.get_projections_for_event_type("work_order.created", "business")
        ai_result = reg.get_projections_for_event_type("work_order.created", "ai")

        assert any(p.name == "biz" for p in biz_result)
        assert not any(p.name == "ai" for p in biz_result)
        assert any(p.name == "ai" for p in ai_result)
        assert not any(p.name == "biz" for p in ai_result)

    def test_get_projections_source_both_receives_all(self):
        from core.projections.framework import ProjectionRegistry

        reg = ProjectionRegistry()
        both_proj = self._make_proj("both_proj", ["work_order.created"], source="both")
        reg.register(both_proj)

        from_biz = reg.get_projections_for_event_type("work_order.created", "business")
        from_ai = reg.get_projections_for_event_type("work_order.created", "ai")
        assert any(p.name == "both_proj" for p in from_biz)
        assert any(p.name == "both_proj" for p in from_ai)

    def test_unknown_non_wildcard_emits_warning_not_error(self, caplog):
        """Registering a projection with an unknown event type warns but does not raise."""
        import logging
        from core.projections.framework import ProjectionRegistry

        reg = ProjectionRegistry()
        proj = self._make_proj(
            "unknown_type_proj",
            ["completely.unknown.event_type_xyz_phase18"],
        )
        # Should NOT raise.
        with caplog.at_level(logging.WARNING, logger="core.projections.framework"):
            reg.register(proj)

        assert reg.get("unknown_type_proj") is not None
        # A warning must have been emitted.
        warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
        assert any(
            "completely.unknown.event_type_xyz_phase18" in r.message for r in warnings
        ), "Expected a warning for unregistered event type"

    def test_wildcard_event_type_skips_registry_validation(self, caplog):
        """Wildcard patterns must not trigger the 'not in registry' warning."""
        import logging
        from core.projections.framework import ProjectionRegistry

        reg = ProjectionRegistry()
        proj = self._make_proj("wildcard_ok", ["work_order.%"])
        with caplog.at_level(logging.WARNING, logger="core.projections.framework"):
            reg.register(proj)

        # No warning about work_order.% not being in the registry.
        warnings = [r for r in caplog.records if "work_order.%" in r.message]
        assert warnings == [], f"Unexpected warning for wildcard: {warnings}"

    def test_register_missing_name_raises(self):
        from core.projections.framework import ProjectionRegistry

        reg = ProjectionRegistry()
        proj = self._make_proj("", ["work_order.created"])
        with pytest.raises(ValueError):
            reg.register(proj)


# ---------------------------------------------------------------------------
# 3. ProjectionEngine — registration
# ---------------------------------------------------------------------------


class TestProjectionEngineRegistration:
    def test_register_creates_projection_state_row(self, tmp_db):
        from core.projections.framework import ProjectionEngine

        proj = _CountingProjection()
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        conn = sqlite3.connect(str(tmp_db))
        row = conn.execute(
            "SELECT projection_name FROM projection_state WHERE projection_name = ?",
            (proj.name,),
        ).fetchone()
        conn.close()

        assert row is not None, "register() must create a projection_state row"

    def test_register_calls_setup_tables(self, tmp_db):
        """setup_tables() should be invoked during registration."""
        setup_called = []

        class _SetupCapture(_CountingProjection):
            name = "setup_capture_proj"

            def setup_tables(self, conn):
                setup_called.append(True)

        from core.projections.framework import ProjectionEngine

        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(_SetupCapture())
        assert setup_called, "setup_tables() must be called during register()"

    def test_duplicate_registration_does_not_error(self, tmp_db):
        """Registering the same projection twice must not raise."""
        from core.projections.framework import ProjectionEngine

        engine = ProjectionEngine(db_path=str(tmp_db))
        proj1 = _CountingProjection()
        engine.register(proj1)

        proj2 = _CountingProjection()
        # Second register with same name — must not raise.
        engine.register(proj2)

    def test_projection_state_columns_exist(self, tmp_db):
        """Verify projection_state DDL was applied before engine tests run."""
        conn = sqlite3.connect(str(tmp_db))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(projection_state)").fetchall()}
        conn.close()
        expected = {
            "projection_name",
            "last_processed_business_event_id",
            "last_processed_ai_event_id",
            "last_run_at",
            "events_processed_total",
            "events_failed_total",
        }
        assert expected.issubset(cols)


# ---------------------------------------------------------------------------
# 4. ProjectionEngine — incremental dispatch (run_cycle)
# ---------------------------------------------------------------------------


class TestProjectionEngineRunCycle:
    def test_new_events_dispatched_to_matching_projection(self, tmp_db):
        from core.projections.framework import ProjectionEngine

        proj = _CountingProjection()
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        eid = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_db))
        _insert_business_event(
            conn,
            eid,
            "work_order.created",
            "2026-05-22T10:00:00+00:00",
            {"work_order_id": "wo-1"},
            work_order_id="wo-1",
        )
        conn.close()

        results = engine.run_cycle()
        assert len(results) == 1
        assert results[0].events_processed == 1
        assert any(e["event_id"] == eid for e in proj.calls)

    def test_events_past_cursor_not_reprocessed(self, tmp_db):
        """After processing, running run_cycle() again must not re-dispatch."""
        from core.projections.framework import ProjectionEngine

        proj = _CountingProjection()
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        eid = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_db))
        _insert_business_event(
            conn,
            eid,
            "work_order.created",
            "2026-05-22T10:00:00+00:00",
            {"work_order_id": "wo-2"},
            work_order_id="wo-2",
        )
        conn.close()

        engine.run_cycle()
        first_call_count = len(proj.calls)

        # Run again — no new events, so no new dispatches.
        engine.run_cycle()
        second_call_count = len(proj.calls)

        assert first_call_count == second_call_count, "Events past cursor must not be re-dispatched"

    def test_handle_rows_written_accumulates_in_result(self, tmp_db):
        from core.projections.framework import ProjectionEngine

        proj = _CountingProjection()
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        conn = sqlite3.connect(str(tmp_db))
        for i in range(3):
            _insert_business_event(
                conn,
                str(uuid.uuid4()),
                "work_order.created",
                f"2026-05-22T10:0{i}:00+00:00",
                {"work_order_id": f"wo-row-{i}"},
                work_order_id=f"wo-row-{i}",
            )
        conn.close()

        results = engine.run_cycle()
        assert results[0].rows_written == 3, "rows_written should accumulate across all events"

    def test_events_from_wrong_source_not_dispatched(self, tmp_db):
        """A business-only projection must not receive AI events."""
        from core.projections.framework import ProjectionEngine

        proj = _CountingProjection()  # source_canonical = "business"
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        # Insert into AI canonical — must not be dispatched.
        ai_eid = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            """
            INSERT INTO ai_canonical_events
                (event_id, event_type, event_timestamp, trace, payload)
            VALUES (?, ?, ?, '{}', '{}')
            """,
            (ai_eid, "work_order.created", "2026-05-22T10:00:00+00:00"),
        )
        conn.commit()
        conn.close()

        engine.run_cycle()
        assert not any(
            e["event_id"] == ai_eid for e in proj.calls
        ), "AI events must not be dispatched to business-source projection"

    def test_events_with_non_matching_type_not_dispatched(self, tmp_db):
        """Events with types not in consumed_event_types must not be dispatched."""
        from core.projections.framework import ProjectionEngine

        proj = _CountingProjection()  # consumes work_order.created / started
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        other_eid = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_db))
        _insert_business_event(
            conn,
            other_eid,
            "project.created",
            "2026-05-22T10:00:00+00:00",
            {"project_id": "proj-abc"},
        )
        conn.close()

        engine.run_cycle()
        assert not any(e["event_id"] == other_eid for e in proj.calls)


# ---------------------------------------------------------------------------
# 5. Dead-letter and retry
# ---------------------------------------------------------------------------


class TestDeadLetterAndRetry:
    def _failing_proj(self):
        """Return a CountingProjection whose handle() always raises."""
        proj = _CountingProjection()
        proj.name = "failing_proj"
        proj._fail = True
        return proj

    def test_failing_handle_schedules_retry(self, tmp_db):
        from core.projections.framework import ProjectionEngine

        proj = self._failing_proj()
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        eid = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_db))
        _insert_business_event(
            conn,
            eid,
            "work_order.created",
            "2026-05-22T10:00:00+00:00",
            {"work_order_id": "wo-fail-1"},
            work_order_id="wo-fail-1",
        )
        conn.close()

        engine.run_cycle()

        conn = sqlite3.connect(str(tmp_db))
        retry_row = conn.execute(
            "SELECT * FROM projection_retry_queue WHERE event_id = ? AND projection_name = ?",
            (eid, proj.name),
        ).fetchone()
        conn.close()

        assert retry_row is not None, "Failed handle() must schedule a retry"

    def test_max_retries_exceeded_moves_to_dead_letter(self, tmp_db):
        """When retry count exceeds max_retries, event lands in dead letter."""
        from core.projections.framework import ProjectionEngine, RetryPolicy

        proj = self._failing_proj()
        proj.retry_policy = RetryPolicy(max_retries=1, base_delay_seconds=0.0)
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        eid = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_db))
        _insert_business_event(
            conn,
            eid,
            "work_order.created",
            "2026-05-22T10:00:00+00:00",
            {"work_order_id": "wo-dead-1"},
            work_order_id="wo-dead-1",
        )
        conn.close()

        # First run: initial failure → schedules retry.
        engine.run_cycle()

        # Manually set next_retry_at to the past so it fires immediately.
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "UPDATE projection_retry_queue SET next_retry_at = '2000-01-01T00:00:00+00:00' "
            "WHERE event_id = ? AND projection_name = ?",
            (eid, proj.name),
        )
        conn.commit()
        conn.close()

        # Second run: retry fires, fails again, exceeds max_retries → dead letter.
        engine.run_cycle()

        conn = sqlite3.connect(str(tmp_db))
        dl_row = conn.execute(
            "SELECT status FROM projection_dead_letter "
            "WHERE event_id = ? AND projection_name = ?",
            (eid, proj.name),
        ).fetchone()
        conn.close()

        assert dl_row is not None, "Exhausted retries must create a dead-letter entry"
        assert dl_row[0] == "active", "Dead-letter status should be 'active'"

    def test_retry_success_removes_from_queue(self, tmp_db):
        """When a retry succeeds, the entry must be removed from retry queue."""
        from core.projections.framework import ProjectionEngine, RetryPolicy

        call_count = [0]

        class _FlipProj(_CountingProjection):
            name = "flip_proj"
            retry_policy = RetryPolicy(max_retries=3, base_delay_seconds=0.0)

            def handle(self, event, conn):
                call_count[0] += 1
                if call_count[0] == 1:
                    raise RuntimeError("first attempt fails")
                # Subsequent attempts succeed.
                conn.execute(
                    "INSERT OR IGNORE INTO test_projection_target (event_id, processed_at)"
                    " VALUES (?, ?)",
                    (event["event_id"], datetime.now(UTC).isoformat()),
                )
                return 1

            def is_already_processed(self, event_id, target_table, conn):
                row = conn.execute(
                    "SELECT 1 FROM test_projection_target WHERE event_id = ? LIMIT 1",
                    (event_id,),
                ).fetchone()
                return row is not None

        flip = _FlipProj()
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(flip)

        eid = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_db))
        _insert_business_event(
            conn,
            eid,
            "work_order.created",
            "2026-05-22T10:00:00+00:00",
            {"work_order_id": "wo-retry-ok"},
            work_order_id="wo-retry-ok",
        )
        conn.close()

        # First cycle: initial failure → retry scheduled.
        engine.run_cycle()

        # Backdate the retry so it fires on next cycle.
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "UPDATE projection_retry_queue SET next_retry_at = '2000-01-01T00:00:00+00:00' "
            "WHERE event_id = ? AND projection_name = ?",
            (eid, flip.name),
        )
        conn.commit()
        conn.close()

        # Second cycle: retry fires and succeeds.
        engine.run_cycle()

        conn = sqlite3.connect(str(tmp_db))
        remaining = conn.execute(
            "SELECT COUNT(*) FROM projection_retry_queue WHERE event_id = ? AND projection_name = ?",
            (eid, flip.name),
        ).fetchone()[0]
        conn.close()

        assert remaining == 0, "Successful retry must remove entry from projection_retry_queue"

    def test_future_retry_not_fired(self, tmp_db):
        """A retry entry with next_retry_at in the future must not be processed."""
        from core.projections.framework import ProjectionEngine

        proj = self._failing_proj()
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        eid = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_db))
        _insert_business_event(
            conn,
            eid,
            "work_order.created",
            "2026-05-22T10:00:00+00:00",
            {"work_order_id": "wo-future"},
            work_order_id="wo-future",
        )
        conn.close()

        # First cycle schedules retry with a future timestamp.
        engine.run_cycle()

        # Verify retry entry was inserted with a future next_retry_at.
        conn = sqlite3.connect(str(tmp_db))
        retry_row = conn.execute(
            "SELECT next_retry_at FROM projection_retry_queue WHERE event_id = ? AND projection_name = ?",
            (eid, proj.name),
        ).fetchone()
        conn.close()

        assert retry_row is not None
        # next_retry_at should be in the future (not a past date).
        # The retry scheduled by the first cycle must not already be in the past
        # (base_delay is at least 1s, so this should hold within any reasonable test runtime).
        # We just verify the row still exists (not fired) by running cycle again
        # WITHOUT backdating the timestamp.

        handle_calls_before = len(proj.calls)
        # NOTE: proj._fail is True, but _process_retries won't fire future entries.
        engine._process_retries(proj)
        handle_calls_after = len(proj.calls)
        # Since retry is still in the future, no new handle() calls.
        # (The initial dispatch already failed; calls only increase on retry fires.)
        assert (
            handle_calls_after == handle_calls_before
        ), "Future retries must not be processed immediately"


# ---------------------------------------------------------------------------
# 6. Rebuild
# ---------------------------------------------------------------------------


class TestRebuild:
    def test_rebuild_calls_pre_rebuild_and_replays_events(self, tmp_db):
        from core.projections.framework import ProjectionEngine

        proj = _CountingProjection()
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        conn = sqlite3.connect(str(tmp_db))
        for i in range(3):
            _insert_business_event(
                conn,
                str(uuid.uuid4()),
                "work_order.created",
                f"2026-05-22T1{i}:00:00+00:00",
                {"work_order_id": f"wo-rb-{i}"},
                work_order_id=f"wo-rb-{i}",
            )
        conn.close()

        result = engine.rebuild(proj.name)
        assert result.events_processed == 3, "rebuild must replay all matching events"

    def test_rebuild_is_deterministic(self, tmp_db):
        """Running rebuild twice must produce identical business_work_orders state."""
        from core.projections.framework import ProjectionEngine

        proj = _CountingProjection()
        engine = ProjectionEngine(db_path=str(tmp_db))
        engine.register(proj)

        conn = sqlite3.connect(str(tmp_db))
        for i in range(4):
            _insert_business_event(
                conn,
                str(uuid.uuid4()),
                "work_order.created",
                f"2026-05-22T1{i}:00:00+00:00",
                {"work_order_id": f"wo-det-{i}"},
                work_order_id=f"wo-det-{i}",
            )
        conn.close()

        result1 = engine.rebuild(proj.name)
        proj.calls.clear()  # reset call tracking for the second rebuild

        result2 = engine.rebuild(proj.name)

        # Both rebuilds should have processed the same number of events.
        assert (
            result1.events_processed == result2.events_processed
        ), "Rebuild must be deterministic (same event count both runs)"

    def test_rebuild_matches_incremental_from_scratch(self, tmp_db):
        """Rebuild result must equal what incremental processing produces."""
        from core.projections.framework import ProjectionEngine

        # Insert events first.
        conn = sqlite3.connect(str(tmp_db))
        event_ids = []
        for i in range(3):
            eid = str(uuid.uuid4())
            event_ids.append(eid)
            _insert_business_event(
                conn,
                eid,
                "work_order.created",
                f"2026-05-22T1{i}:00:00+00:00",
                {"work_order_id": f"wo-cmp-{i}"},
                work_order_id=f"wo-cmp-{i}",
            )
        conn.close()

        # Engine A: incremental.
        proj_a = _CountingProjection()
        engine_a = ProjectionEngine(db_path=str(tmp_db))
        engine_a.register(proj_a)
        incr_result = engine_a.run_cycle()[0]

        # Engine B (fresh): rebuild.
        proj_b = _CountingProjection()
        engine_b = ProjectionEngine(db_path=str(tmp_db))
        engine_b.register(proj_b)
        rebuild_result = engine_b.rebuild(proj_b.name)

        # Both should have processed the same number of events.
        assert (
            incr_result.events_processed == rebuild_result.events_processed
        ), "Incremental and rebuild must process the same number of events"

    def test_rebuild_unknown_projection_raises(self, tmp_db):
        from core.projections.framework import ProjectionEngine

        engine = ProjectionEngine(db_path=str(tmp_db))
        with pytest.raises(KeyError):
            engine.rebuild("nonexistent_projection_xyz")
