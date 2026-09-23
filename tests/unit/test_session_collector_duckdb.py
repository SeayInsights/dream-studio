"""SessionCollector DuckDB repoint tests (WO-DBA-REPOINT).

The collector reads the DuckDB raw_sessions compat view (events_fact over
system.session.recorded/closed canonical events) first, and falls back to the
SQLite raw_sessions table when the analytics store has no views yet or holds
no rows for the window.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
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
    def test_missing_analytics_store_falls_back(self, sqlite_db):
        """No aggregate_metrics.db exists beside sqlite_db at all.

        SessionCollector(db_path=...) resolves its analytics store as the
        canonical aggregate_metrics.db sibling of sqlite_db (see
        core.analytics.duckdb_store.analytics_db_path_for); nothing here ever
        creates that file, so connect_analytics raises
        AnalyticsStoreMissingError before any DuckDB query runs. No
        monkeypatch is needed -- unlike the pre-fix collector, which always
        resolved the ambient DREAM_STUDIO_HOME store, this collector consults
        sqlite_db's own directory, so simply not creating a store there is
        sufficient to exercise the genuinely-missing-store path.
        """
        from projections.core.collectors.session_collector import SessionCollector

        metrics = SessionCollector(db_path=str(sqlite_db)).collect(days=3650)
        assert metrics["total_sessions"] == 1
        assert metrics["by_project"] == {"proj-sqlite": 1}

        recent = SessionCollector(db_path=str(sqlite_db)).get_recent_sessions()
        assert [r["session_id"] for r in recent] == ["sqlite-sess"]

    def test_empty_view_falls_back_to_sqlite_rows(self, tmp_path, sqlite_db):
        """The analytics store DOES exist beside sqlite_db (schema/views
        present) but holds zero session events -- distinct from
        test_missing_analytics_store_falls_back, where connect_analytics
        never succeeds at all.

        Built at aggregate_metrics.db, the canonical sibling of sqlite_db
        (tmp_path is shared by both fixtures), which is exactly where the
        collector now looks given an explicit db_path -- a monkeypatch of
        analytics_db_path() would go unread, since an explicit db_path
        bypasses that resolver entirely.

        collect() normalizes both this path and the missing-store path onto
        identical final metrics (it only returns _collect_duckdb's own result
        when total_sessions > 0), so asserting on collect()'s return value
        alone cannot tell the two apart. Calling _collect_duckdb directly
        first proves THIS test actually drove a successful, zero-row DuckDB
        read rather than an exception being swallowed the same way the
        missing-store case swallows one.
        """
        from core.analytics import duckdb_store
        from projections.core.collectors.session_collector import SessionCollector

        db = tmp_path / "aggregate_metrics.db"
        conn = duckdb_store.connect_analytics(db, read_only=False)
        try:
            duckdb_store.ensure_analytics_schema(conn)  # views exist, zero events
        finally:
            conn.close()

        collector = SessionCollector(db_path=str(sqlite_db))
        cutoff_date = (datetime.now() - timedelta(days=3650)).strftime("%Y-%m-%d")
        try:
            duckdb_metrics = collector._collect_duckdb(cutoff_date)
        except Exception as exc:  # pragma: no cover - failure path, not the happy path
            pytest.fail(
                "_collect_duckdb raised instead of returning the empty-view result "
                f"(the DuckDB branch was skipped rather than exercised): {exc!r}"
            )
        assert duckdb_metrics is not None
        assert duckdb_metrics["total_sessions"] == 0

        metrics = collector.collect(days=3650)
        assert metrics["total_sessions"] == 1
        assert metrics["by_project"] == {"proj-sqlite": 1}
