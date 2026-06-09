"""Tests for DuckDB analytics_conn wiring in ProjectionEngine (WO-TS3 task 5)."""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema  # noqa: E402
from core.projections.framework import Projection, ProjectionEngine  # noqa: E402


def _apply_ddl(conn: sqlite3.Connection) -> None:
    conn.executescript("""
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
            failed_at TEXT NOT NULL DEFAULT (datetime('now','utc')),
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
    """)
    conn.commit()


@pytest.fixture()
def tmp_db(tmp_path, monkeypatch):
    db_path = tmp_path / "studio.db"
    monkeypatch.setenv("DREAM_STUDIO_DB_PATH", str(db_path))
    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass
    conn = sqlite3.connect(str(db_path))
    _apply_ddl(conn)
    conn.close()
    yield db_path
    try:
        from core.config.database import DatabaseRuntime

        DatabaseRuntime.reset_instance()
    except Exception:
        pass


@pytest.fixture()
def duck_conn(tmp_path):
    db = tmp_path / "agg.db"
    conn = connect_analytics(db, read_only=False)
    ensure_analytics_schema(conn)
    yield conn
    try:
        conn.close()
    except Exception:
        pass


class _MilestoneNoop(Projection):
    name = "noop_milestone"
    source_canonical = "business"
    consumed_event_types = ["milestone.created"]

    def setup_tables(self, conn: sqlite3.Connection) -> None:
        pass

    def pre_rebuild(self, conn: sqlite3.Connection) -> None:
        pass

    def handle(self, event: dict, conn: sqlite3.Connection) -> int:
        return 0


class TestAnalyticsConnWiring:
    def test_analytics_conn_stored_on_engine(self, tmp_db, duck_conn):
        engine = ProjectionEngine(analytics_conn=duck_conn)
        assert engine.analytics_conn is duck_conn

    def test_analytics_conn_defaults_to_none(self, tmp_db):
        engine = ProjectionEngine()
        assert engine.analytics_conn is None

    def test_duckdb_dispatch_called_on_cycle(self, tmp_db, duck_conn):
        """Events processed by SQLite projections also land in DuckDB."""
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT INTO business_canonical_events "
            "(event_id, event_type, event_timestamp, trace, payload) VALUES (?, ?, ?, ?, ?)",
            (
                "evt-ms-wired",
                "milestone.created",
                "2026-01-01T00:00:00+00:00",
                json.dumps({"milestone_id": "ms-wired-1", "project_id": "p1"}),
                json.dumps({"title": "Alpha"}),
            ),
        )
        conn.commit()
        conn.close()

        engine = ProjectionEngine(analytics_conn=duck_conn)
        engine.register(_MilestoneNoop())
        engine.run_cycle()

        row = duck_conn.execute(
            "SELECT milestone_id FROM duckdb_milestones WHERE milestone_id='ms-wired-1'"
        ).fetchone()
        assert row is not None, "milestone.created was not dispatched to DuckDB"

    def test_duckdb_dispatch_failopen_when_conn_none(self, tmp_db):
        """Engine with analytics_conn=None processes SQLite events without error."""
        conn = sqlite3.connect(str(tmp_db))
        conn.execute(
            "INSERT INTO business_canonical_events "
            "(event_id, event_type, event_timestamp, trace, payload) VALUES (?, ?, ?, ?, ?)",
            (
                "evt-ms-failopen",
                "milestone.created",
                "2026-01-01T00:00:00+00:00",
                json.dumps({"milestone_id": "ms-fo", "project_id": "p"}),
                json.dumps({"title": "B"}),
            ),
        )
        conn.commit()
        conn.close()

        engine = ProjectionEngine(analytics_conn=None)
        engine.register(_MilestoneNoop())
        results = engine.run_cycle()
        assert results[0].events_processed == 1
        assert results[0].errors == []
