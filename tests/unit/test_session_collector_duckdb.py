"""SessionCollector DuckDB repoint tests (WO-DBA-REPOINT).

The collector reads the DuckDB raw_sessions compat view (events_fact over
system.session.recorded/closed canonical events) first, and falls back to the
SQLite raw_sessions table when the analytics store has no views yet or holds
no rows for the window.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

SESSIONS = [
    ("sess-1", "proj-a", "2026-06-30T09:00:00Z", "2026-06-30T09:30:00Z", 1800.0, "completed"),
    ("sess-2", "proj-a", "2026-07-01T14:00:00Z", "2026-07-01T14:10:00Z", 600.0, "completed"),
    ("sess-3", "proj-b", "2026-07-02T20:00:00Z", None, None, "in_progress"),
]


@pytest.fixture
def analytics_db(tmp_path, monkeypatch):
    """Isolated analytics store with the raw_sessions view seeded from events."""
    from core.analytics import duckdb_store

    db = tmp_path / "aggregate_metrics.db"
    monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: db)

    conn = duckdb_store.connect_analytics(db, read_only=False)
    try:
        duckdb_store.ensure_analytics_schema(conn)
        for i, (sid, project, started, ended, duration, outcome) in enumerate(SESSIONS):
            conn.execute(
                "INSERT INTO events_fact (event_id, event_type, event_timestamp, payload,"
                " project_id) VALUES (?, 'system.session.recorded', ?, ?, ?)",
                [
                    f"evt-rec-{i}",
                    started,
                    json.dumps(
                        {
                            "session_id": sid,
                            "project_id": project,
                            "started_at": started,
                            "outcome": outcome,
                        }
                    ),
                    project,
                ],
            )
            if ended:
                conn.execute(
                    "INSERT INTO events_fact (event_id, event_type, event_timestamp, payload,"
                    " project_id) VALUES (?, 'system.session.closed', ?, ?, ?)",
                    [
                        f"evt-close-{i}",
                        ended,
                        json.dumps(
                            {
                                "session_id": sid,
                                "duration_s": duration,
                                "outcome": outcome,
                            }
                        ),
                        project,
                    ],
                )
    finally:
        conn.close()
    return db


@pytest.fixture
def sqlite_db(tmp_path):
    """SQLite fallback source with one distinctive row."""
    db = tmp_path / "studio.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE raw_sessions (session_id TEXT, project_id TEXT, started_at TEXT,"
        " ended_at TEXT, outcome TEXT)"
    )
    conn.execute(
        "INSERT INTO raw_sessions VALUES"
        " ('sqlite-sess', 'proj-sqlite', '2026-07-01T00:00:00Z', NULL, 'completed')"
    )
    conn.commit()
    conn.close()
    return db


class TestDuckDBPath:
    def test_collect_reads_duckdb_view(self, analytics_db, sqlite_db):
        from projections.core.collectors.session_collector import SessionCollector

        metrics = SessionCollector(db_path=str(sqlite_db)).collect(days=3650)
        assert metrics["total_sessions"] == 3
        assert metrics["by_project"] == {"proj-a": 2, "proj-b": 1}
        assert metrics["outcomes"]["completed"] == 2
        # (1800 + 600) / 2 closed sessions = 1200s = 20 minutes
        assert metrics["avg_duration_minutes"] == 20.0
        assert metrics["success_rate"] == round(2 / 3, 3)
        assert {t["date"] for t in metrics["timeline"]} == {
            "2026-06-30",
            "2026-07-01",
            "2026-07-02",
        }
        assert sum(metrics["day_of_week"].values()) == 3
        assert "analytics" in str(metrics["source_status"])

    def test_recent_sessions_from_duckdb(self, analytics_db, sqlite_db):
        from projections.core.collectors.session_collector import SessionCollector

        recent = SessionCollector(db_path=str(sqlite_db)).get_recent_sessions(limit=2)
        assert [r["session_id"] for r in recent] == ["sess-3", "sess-2"]


class TestSqliteFallback:
    def test_missing_analytics_store_falls_back(self, tmp_path, sqlite_db, monkeypatch):
        from core.analytics import duckdb_store
        from projections.core.collectors.session_collector import SessionCollector

        # Point analytics at an empty store: connect succeeds, views absent.
        monkeypatch.setattr(
            duckdb_store, "analytics_db_path", lambda: tmp_path / "empty-analytics.db"
        )
        metrics = SessionCollector(db_path=str(sqlite_db)).collect(days=3650)
        assert metrics["total_sessions"] == 1
        assert metrics["by_project"] == {"proj-sqlite": 1}

        recent = SessionCollector(db_path=str(sqlite_db)).get_recent_sessions()
        assert [r["session_id"] for r in recent] == ["sqlite-sess"]

    def test_empty_view_falls_back_to_sqlite_rows(self, tmp_path, sqlite_db, monkeypatch):
        from core.analytics import duckdb_store
        from projections.core.collectors.session_collector import SessionCollector

        db = tmp_path / "analytics-with-views.db"
        monkeypatch.setattr(duckdb_store, "analytics_db_path", lambda: db)
        conn = duckdb_store.connect_analytics(db, read_only=False)
        try:
            duckdb_store.ensure_analytics_schema(conn)  # views exist, zero events
        finally:
            conn.close()

        metrics = SessionCollector(db_path=str(sqlite_db)).collect(days=3650)
        assert metrics["total_sessions"] == 1
        assert metrics["by_project"] == {"proj-sqlite": 1}
