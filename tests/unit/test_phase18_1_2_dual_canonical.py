"""Phase 18.1.2: Dual canonical structure + event type registry unit tests.

Coverage:
  1. Registry: routing decisions for known and unknown event types
  2. Registry: API functions (get_routes, is_registered, get_entry, all_entries)
  3. Migration 067: both tables created with expected columns and indexes
  4. Ingestor: _write_to_dual_canonical routes correctly, best-effort semantics
  5. Backfill: dry-run routing counts match expected distribution
  6. Correlation join: canonical_join utility queries return correct structure
"""

from __future__ import annotations

import importlib
import json
import sqlite3
import sys
import uuid
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def registry():
    mod = importlib.import_module("config.event_type_registry")
    importlib.reload(mod)
    return mod


@pytest.fixture
def tmp_db(tmp_path):
    """Minimal studio.db with canonical_events + both dual canonical tables."""
    db_path = tmp_path / "studio.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        PRAGMA journal_mode = WAL;

        CREATE TABLE IF NOT EXISTS canonical_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL DEFAULT (datetime('now','utc')),
            trace JSON NOT NULL DEFAULT '{}',
            payload JSON NOT NULL DEFAULT '{}',
            schema_version INTEGER NOT NULL DEFAULT 1,
            severity TEXT NOT NULL DEFAULT 'info',
            created_at TEXT
        );

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
        """)
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def ingestor_module():
    """Import (or reload) spool.ingestor so _write_to_dual_canonical is accessible."""
    mod = importlib.import_module("spool.ingestor")
    importlib.reload(mod)
    return mod


# ---------------------------------------------------------------------------
# 1. Registry — routing decisions
# ---------------------------------------------------------------------------


class TestRegistryRouting:
    def test_business_only_event(self, registry):
        routes = registry.get_routes("project.created")
        assert routes == ("business",)

    def test_ai_only_event(self, registry):
        routes = registry.get_routes("skill.invoked")
        assert routes == ("ai",)

    def test_paired_event(self, registry):
        routes = registry.get_routes("skill.completed")
        assert set(routes) == {"business", "ai"}

    def test_raw_only_event_commitment_9(self, registry):
        routes = registry.get_routes("tool.execution.completed")
        assert routes == ()

    def test_unknown_event_defaults_to_both(self, registry):
        routes = registry.get_routes("completely.unknown.event_type_xyz")
        assert set(routes) == {
            "business",
            "ai",
        }, "Unknown event types must default to both canonicals (safe over-record)"

    def test_work_order_events_business_only(self, registry):
        for et in ("work_order.created", "work_order.started", "work_order.closed"):
            assert registry.get_routes(et) == ("business",), f"{et} should be business-only"

    def test_task_events_business_only(self, registry):
        for et in ("task.created", "task.started", "task.completed", "task.deleted"):
            assert registry.get_routes(et) == ("business",), f"{et} should be business-only"

    def test_session_events_ai_only(self, registry):
        for et in ("session.lifecycle.started", "session.lifecycle.ended"):
            assert registry.get_routes(et) == ("ai",), f"{et} should be ai-only"

    def test_token_consumed_ai_only(self, registry):
        assert registry.get_routes("token.consumed") == ("ai",)

    def test_hook_tool_activity_raw_only(self, registry):
        routes = registry.get_routes("hook.tool_activity")
        assert routes == ()

    def test_tool_execution_started_raw_only(self, registry):
        routes = registry.get_routes("tool.execution.started")
        assert routes == ()

    def test_all_registered_types_have_valid_routes(self, registry):
        valid_destinations = {"business", "ai"}
        for entry in registry.all_entries():
            for dest in entry.routes_to:
                assert (
                    dest in valid_destinations
                ), f"{entry.event_type} has invalid route destination: {dest!r}"

    def test_all_entries_have_granularity(self, registry):
        valid_granularity = {"meaningful-unit", "mechanical-detail"}
        for entry in registry.all_entries():
            assert (
                entry.granularity_level in valid_granularity
            ), f"{entry.event_type} has unexpected granularity: {entry.granularity_level!r}"

    def test_raw_only_events_are_mechanical_detail(self, registry):
        for entry in registry.all_entries():
            if entry.routes_to == ():
                assert (
                    entry.granularity_level == "mechanical-detail"
                ), f"{entry.event_type} is raw-only but not mechanical-detail"


# ---------------------------------------------------------------------------
# 2. Registry — API surface
# ---------------------------------------------------------------------------


class TestRegistryAPI:
    def test_is_registered_known(self, registry):
        assert registry.is_registered("project.created") is True

    def test_is_registered_unknown(self, registry):
        assert registry.is_registered("not.a.real.event") is False

    def test_get_entry_returns_dataclass(self, registry):
        entry = registry.get_entry("skill.invoked")
        assert entry is not None
        assert entry.event_type == "skill.invoked"
        assert isinstance(entry.routes_to, tuple)

    def test_get_entry_none_for_unknown(self, registry):
        assert registry.get_entry("no.such.type") is None

    def test_all_entries_returns_tuple(self, registry):
        entries = registry.all_entries()
        assert isinstance(entries, tuple)
        assert len(entries) >= 1

    def test_registry_has_minimum_entries(self, registry):
        # We expect at least 20 registered entries (actual is ~85)
        assert len(registry.all_entries()) >= 20

    def test_registry_no_duplicate_event_types(self, registry):
        types = [e.event_type for e in registry.all_entries()]
        assert len(types) == len(set(types)), "Duplicate event_type keys in registry"


# ---------------------------------------------------------------------------
# 3. Migration 067 — schema
# ---------------------------------------------------------------------------


class TestMigration067Schema:
    def test_migration_file_exists(self):
        migration = REPO_ROOT / "core" / "event_store" / "migrations" / "067_dual_canonical.sql"
        assert migration.exists(), "Migration 067 SQL file not found"

    def test_migration_is_idempotent(self, tmp_path):
        migration = REPO_ROOT / "core" / "event_store" / "migrations" / "067_dual_canonical.sql"
        sql = migration.read_text(encoding="utf-8")
        db_path = tmp_path / "idempotency.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(sql)  # first apply
        conn.executescript(sql)  # second apply — must not error
        conn.close()

    def test_business_canonical_columns(self, tmp_path):
        migration = REPO_ROOT / "core" / "event_store" / "migrations" / "067_dual_canonical.sql"
        sql = migration.read_text(encoding="utf-8")
        db_path = tmp_path / "schema.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(sql)
        cols = {
            row[1]
            for row in conn.execute("PRAGMA table_info(business_canonical_events)").fetchall()
        }
        expected = {
            "event_id",
            "received_at",
            "event_type",
            "event_timestamp",
            "schema_version",
            "trace",
            "payload",
            "correlation_id",
            "project_id",
            "milestone_id",
            "work_order_id",
            "task_id",
            "severity",
            "source",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"
        conn.close()

    def test_ai_canonical_columns(self, tmp_path):
        migration = REPO_ROOT / "core" / "event_store" / "migrations" / "067_dual_canonical.sql"
        sql = migration.read_text(encoding="utf-8")
        db_path = tmp_path / "schema.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(sql)
        cols = {row[1] for row in conn.execute("PRAGMA table_info(ai_canonical_events)").fetchall()}
        expected = {
            "event_id",
            "received_at",
            "event_type",
            "event_timestamp",
            "schema_version",
            "trace",
            "payload",
            "correlation_id",
            "session_id",
            "skill_id",
            "workflow_id",
            "agent_id",
            "hook_id",
            "model_id",
            "severity",
            "source",
        }
        assert expected.issubset(cols), f"Missing columns: {expected - cols}"
        conn.close()

    def test_business_canonical_indexes_exist(self, tmp_path):
        migration = REPO_ROOT / "core" / "event_store" / "migrations" / "067_dual_canonical.sql"
        sql = migration.read_text(encoding="utf-8")
        db_path = tmp_path / "idx.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(sql)
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='business_canonical_events'"
            ).fetchall()
        }
        assert any(
            "correlation_id" in idx or "bce_correlation" in idx for idx in indexes
        ), "Missing correlation_id index on business_canonical_events"
        conn.close()

    def test_ai_canonical_indexes_exist(self, tmp_path):
        migration = REPO_ROOT / "core" / "event_store" / "migrations" / "067_dual_canonical.sql"
        sql = migration.read_text(encoding="utf-8")
        db_path = tmp_path / "idx.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(sql)
        indexes = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' "
                "AND tbl_name='ai_canonical_events'"
            ).fetchall()
        }
        assert any(
            "session_id" in idx or "ace_session" in idx for idx in indexes
        ), "Missing session_id index on ai_canonical_events"
        conn.close()


# ---------------------------------------------------------------------------
# 4. Ingestor — _write_to_dual_canonical routing
# ---------------------------------------------------------------------------


def _make_envelope(event_type: str, **trace_overrides) -> dict:
    trace = {
        "session_id": "test-session-001",
        "skill_id": "ds-core",
        "project_id": "proj-abc",
        "workflow_id": "wf-xyz",
    }
    trace.update(trace_overrides)
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type,
        "timestamp": "2026-05-22T00:00:00Z",
        "trace": json.dumps(trace),
        "payload": json.dumps({"test": True}),
        "schema_version": 1,
        "severity": "info",
        "created_at": "2026-05-22T00:00:00Z",
    }


class TestIngestorDualCanonical:
    def test_business_event_routes_to_business_only(self, tmp_db, ingestor_module):
        env = _make_envelope("project.created")
        ingestor_module._write_to_dual_canonical(env, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        bce = conn.execute(
            "SELECT * FROM business_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        ace = conn.execute(
            "SELECT * FROM ai_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        conn.close()

        assert bce is not None, "project.created should appear in business_canonical_events"
        assert ace is None, "project.created should NOT appear in ai_canonical_events"

    def test_ai_event_routes_to_ai_only(self, tmp_db, ingestor_module):
        env = _make_envelope("skill.invoked")
        ingestor_module._write_to_dual_canonical(env, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        bce = conn.execute(
            "SELECT * FROM business_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        ace = conn.execute(
            "SELECT * FROM ai_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        conn.close()

        assert ace is not None, "skill.invoked should appear in ai_canonical_events"
        assert bce is None, "skill.invoked should NOT appear in business_canonical_events"

    def test_paired_event_routes_to_both(self, tmp_db, ingestor_module):
        env = _make_envelope("skill.completed")
        ingestor_module._write_to_dual_canonical(env, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        bce = conn.execute(
            "SELECT * FROM business_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        ace = conn.execute(
            "SELECT * FROM ai_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        conn.close()

        assert bce is not None, "skill.completed should appear in business_canonical_events"
        assert ace is not None, "skill.completed should appear in ai_canonical_events"

    def test_raw_only_event_writes_to_neither(self, tmp_db, ingestor_module):
        env = _make_envelope("tool.execution.completed")
        ingestor_module._write_to_dual_canonical(env, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        bce = conn.execute(
            "SELECT * FROM business_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        ace = conn.execute(
            "SELECT * FROM ai_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        conn.close()

        assert bce is None, "tool.execution.completed (raw-only) must not appear in business"
        assert ace is None, "tool.execution.completed (raw-only) must not appear in ai"

    def test_idempotent_insert_or_ignore(self, tmp_db, ingestor_module):
        env = _make_envelope("skill.invoked")
        ingestor_module._write_to_dual_canonical(env, tmp_db)
        ingestor_module._write_to_dual_canonical(env, tmp_db)  # second write

        conn = sqlite3.connect(str(tmp_db))
        count = conn.execute(
            "SELECT COUNT(*) FROM ai_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()[0]
        conn.close()

        assert count == 1, "INSERT OR IGNORE must prevent duplicate rows"

    def test_denormalized_columns_populated(self, tmp_db, ingestor_module):
        trace = {
            "session_id": "sess-123",
            "skill_id": "ds-core",
            "workflow_id": "wf-abc",
            "project_id": "proj-xyz",
        }
        env = _make_envelope("skill.invoked", **trace)
        # Override trace to be the dict we want
        env["trace"] = json.dumps(trace)
        ingestor_module._write_to_dual_canonical(env, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM ai_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["session_id"] == "sess-123"
        assert row["skill_id"] == "ds-core"
        assert row["workflow_id"] == "wf-abc"

    def test_correlation_id_composed_from_trace(self, tmp_db, ingestor_module):
        trace = {"session_id": "sess-A", "skill_id": "ds-core", "workflow_id": "wf-B"}
        env = _make_envelope("skill.invoked", **trace)
        env["trace"] = json.dumps(trace)
        ingestor_module._write_to_dual_canonical(env, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT correlation_id FROM ai_canonical_events WHERE event_id=?",
            (env["event_id"],),
        ).fetchone()
        conn.close()

        assert row is not None
        corr = row["correlation_id"]
        assert corr is not None
        assert "sess-A" in corr
        assert "ds-core" in corr

    def test_unknown_event_type_defaults_to_both(self, tmp_db, ingestor_module):
        env = _make_envelope("totally.unknown.event")
        ingestor_module._write_to_dual_canonical(env, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        bce = conn.execute(
            "SELECT * FROM business_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        ace = conn.execute(
            "SELECT * FROM ai_canonical_events WHERE event_id=?", (env["event_id"],)
        ).fetchone()
        conn.close()

        assert bce is not None, "Unknown event should default to business"
        assert ace is not None, "Unknown event should default to ai"


# ---------------------------------------------------------------------------
# 5. Backfill script — dry-run routing
# ---------------------------------------------------------------------------


class TestBackfillDryRun:
    def test_backfill_module_importable(self):
        mod = importlib.import_module("scripts.backfill_dual_canonical")
        assert hasattr(mod, "run_backfill")

    def test_dry_run_counts_without_writing(self, tmp_db):
        mod = importlib.import_module("scripts.backfill_dual_canonical")

        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT INTO canonical_events (event_id, event_type, timestamp) "
            "VALUES (?, ?, datetime('now','utc'))",
            (str(uuid.uuid4()), "project.created"),
        )
        conn.execute(
            "INSERT INTO canonical_events (event_id, event_type, timestamp) "
            "VALUES (?, ?, datetime('now','utc'))",
            (str(uuid.uuid4()), "skill.invoked"),
        )
        conn.execute(
            "INSERT INTO canonical_events (event_id, event_type, timestamp) "
            "VALUES (?, ?, datetime('now','utc'))",
            (str(uuid.uuid4()), "tool.execution.completed"),
        )
        conn.commit()
        conn.close()

        rc = mod.run_backfill(tmp_db, dry_run=True)
        assert rc == 0

        conn = sqlite3.connect(str(tmp_db))
        bce_count = conn.execute("SELECT COUNT(*) FROM business_canonical_events").fetchone()[0]
        ace_count = conn.execute("SELECT COUNT(*) FROM ai_canonical_events").fetchone()[0]
        conn.close()

        assert bce_count == 0, "Dry-run must not write to business_canonical_events"
        assert ace_count == 0, "Dry-run must not write to ai_canonical_events"

    def test_backfill_writes_correct_routes(self, tmp_db):
        mod = importlib.import_module("scripts.backfill_dual_canonical")

        conn = sqlite3.connect(str(tmp_db))
        biz_id = str(uuid.uuid4())
        ai_id = str(uuid.uuid4())
        raw_id = str(uuid.uuid4())
        conn.executemany(
            "INSERT INTO canonical_events (event_id, event_type, timestamp) "
            "VALUES (?, ?, datetime('now','utc'))",
            [
                (biz_id, "project.created"),
                (ai_id, "skill.invoked"),
                (raw_id, "tool.execution.completed"),
            ],
        )
        conn.commit()
        conn.close()

        rc = mod.run_backfill(tmp_db, dry_run=False)
        assert rc == 0

        conn = sqlite3.connect(str(tmp_db))
        bce_ids = {
            r[0] for r in conn.execute("SELECT event_id FROM business_canonical_events").fetchall()
        }
        ace_ids = {
            r[0] for r in conn.execute("SELECT event_id FROM ai_canonical_events").fetchall()
        }
        conn.close()

        assert biz_id in bce_ids, "project.created should be backfilled to business"
        assert biz_id not in ace_ids, "project.created should NOT be backfilled to ai"
        assert ai_id in ace_ids, "skill.invoked should be backfilled to ai"
        assert ai_id not in bce_ids, "skill.invoked should NOT be backfilled to business"
        assert raw_id not in bce_ids, "tool.execution.completed must not be backfilled"
        assert raw_id not in ace_ids, "tool.execution.completed must not be backfilled"

    def test_backfill_source_column_is_backfill(self, tmp_db):
        mod = importlib.import_module("scripts.backfill_dual_canonical")

        eid = str(uuid.uuid4())
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT INTO canonical_events (event_id, event_type, timestamp) "
            "VALUES (?, ?, datetime('now','utc'))",
            (eid, "project.created"),
        )
        conn.commit()
        conn.close()

        mod.run_backfill(tmp_db, dry_run=False)

        conn = sqlite3.connect(str(tmp_db))
        row = conn.execute(
            "SELECT source FROM business_canonical_events WHERE event_id=?", (eid,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "backfill", "Backfilled rows must have source='backfill'"


# ---------------------------------------------------------------------------
# 6. Correlation join utility
# ---------------------------------------------------------------------------


class TestCorrelationJoin:
    def test_table_exists_helper(self, tmp_db):
        from tools.canonical_join import _table_exists

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        assert _table_exists(conn, "business_canonical_events") is True
        assert _table_exists(conn, "nonexistent_table_xyz") is False
        conn.close()

    def test_join_returns_empty_for_missing_correlation(self, tmp_db, capsys):
        from tools import canonical_join

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        canonical_join._join_correlation_id(conn, "corr-does-not-exist", 20, False)
        conn.close()

        out = capsys.readouterr().out
        assert "No rows found" in out

    def test_join_returns_rows_for_known_correlation(self, tmp_db, ingestor_module, capsys):
        from tools import canonical_join

        trace = {"session_id": "sess-join-test", "skill_id": "ds-core"}
        env = _make_envelope("skill.invoked", **trace)
        env["trace"] = json.dumps(trace)
        ingestor_module._write_to_dual_canonical(env, tmp_db)

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        corr = conn.execute(
            "SELECT correlation_id FROM ai_canonical_events WHERE event_id=?",
            (env["event_id"],),
        ).fetchone()
        conn.close()

        assert corr is not None
        corr_id = corr["correlation_id"]

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        canonical_join._join_correlation_id(conn, corr_id, 20, False)
        conn.close()

        out = capsys.readouterr().out
        assert corr_id in out
        assert "ai rows" in out

    def test_stats_shows_both_tables(self, tmp_db, capsys):
        from tools import canonical_join

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        canonical_join._stats(conn)
        conn.close()

        out = capsys.readouterr().out
        assert "business_canonical_events" in out
        assert "ai_canonical_events" in out

    def test_list_correlation_ids_no_error_on_empty(self, tmp_db, capsys):
        from tools import canonical_join

        conn = sqlite3.connect(str(tmp_db))
        conn.row_factory = sqlite3.Row
        canonical_join._list_correlation_ids(conn, 20)
        conn.close()

        out = capsys.readouterr().out
        assert "No correlation_ids" in out or "CORRELATION_ID" in out
