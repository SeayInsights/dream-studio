"""TA5-followup: project_name resolution + SessionMetrics None outcomes fix."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timedelta, UTC
from unittest import mock

# ── fixture UUIDs ──────────────────────────────────────────────────────────────

PROJECT_KNOWN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
PROJECT_UNMAPPED = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
KNOWN_NAME = "Dream Studio"
# Anchor test data relative to now so it stays inside any days=N query window.
# A hardcoded absolute date is a time-bomb: it silently falls outside the 30-day
# cutoff once wall-clock passes it (this broke CI on 2026-06-21).
NOW = (datetime.now(UTC) - timedelta(days=7)).isoformat()


# ── in-memory DB helpers ───────────────────────────────────────────────────────


def _make_db() -> sqlite3.Connection:
    """Create an in-memory DB with both canonical_events and ds_projects tables."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE canonical_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            trace JSON NOT NULL,
            severity TEXT NOT NULL,
            payload JSON NOT NULL,
            actor JSON,
            confidence_score REAL,
            source_type TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX idx_ce_event_type ON canonical_events(event_type);
        CREATE INDEX idx_ce_timestamp ON canonical_events(timestamp);

        CREATE TABLE business_projects (
            project_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn


def _insert_project(conn: sqlite3.Connection, project_id: str, name: str) -> None:
    conn.execute(
        "INSERT INTO business_projects (project_id, name, description, status, created_at, updated_at)"
        " VALUES (?, ?, '', 'active', ?, ?)",
        (project_id, name, NOW, NOW),
    )
    conn.commit()


def _insert_token_event(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = PROJECT_KNOWN,
    model: str = "claude-sonnet-4-6",
    input_tokens: int = 100,
    output_tokens: int = 50,
    ts: str = NOW,
) -> None:
    trace = {"project_id": project_id, "attribution_status": "partial"}
    payload = {
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    conn.execute(
        "INSERT INTO canonical_events (event_id, event_type, timestamp, trace, severity, payload)"
        " VALUES (?, 'token.consumed', ?, ?, 'info', ?)",
        (str(uuid.uuid4()), ts, json.dumps(trace), json.dumps(payload)),
    )
    conn.commit()


def _patch_conn(conn: sqlite3.Connection):
    return mock.patch(
        "projections.api.queries.token_attribution.get_connection",
        side_effect=lambda: conn,
    )


# ==============================================================================
# Fix 1: canonical_token_metrics — project_name resolution
# ==============================================================================


class TestCanonicalTokenMetricsProjectName:
    def test_resolves_known_project_name(self):
        from projections.api.queries.token_attribution import canonical_token_metrics

        conn = _make_db()
        _insert_project(conn, PROJECT_KNOWN, KNOWN_NAME)
        _insert_token_event(conn, project_id=PROJECT_KNOWN, input_tokens=200, output_tokens=100)

        with _patch_conn(conn):
            result = canonical_token_metrics(days=30)

        assert PROJECT_KNOWN in result["by_project"]
        assert result["by_project"][PROJECT_KNOWN]["project_name"] == KNOWN_NAME

    def test_fallback_for_unmapped_project_id(self):
        from projections.api.queries.token_attribution import canonical_token_metrics

        conn = _make_db()
        # No row in ds_projects for PROJECT_UNMAPPED
        _insert_token_event(conn, project_id=PROJECT_UNMAPPED, input_tokens=100, output_tokens=50)

        with _patch_conn(conn):
            result = canonical_token_metrics(days=30)

        assert PROJECT_UNMAPPED in result["by_project"]
        name = result["by_project"][PROJECT_UNMAPPED]["project_name"]
        assert "Unmapped" in name
        assert PROJECT_UNMAPPED in name

    def test_mixed_known_and_unmapped(self):
        from projections.api.queries.token_attribution import canonical_token_metrics

        conn = _make_db()
        _insert_project(conn, PROJECT_KNOWN, KNOWN_NAME)
        _insert_token_event(conn, project_id=PROJECT_KNOWN, input_tokens=100, output_tokens=50)
        _insert_token_event(conn, project_id=PROJECT_UNMAPPED, input_tokens=50, output_tokens=25)

        with _patch_conn(conn):
            result = canonical_token_metrics(days=30)

        assert result["by_project"][PROJECT_KNOWN]["project_name"] == KNOWN_NAME
        assert "Unmapped" in result["by_project"][PROJECT_UNMAPPED]["project_name"]

    def test_empty_db_returns_empty_by_project(self):
        from projections.api.queries.token_attribution import canonical_token_metrics

        conn = _make_db()

        with _patch_conn(conn):
            result = canonical_token_metrics(days=30)

        assert result["by_project"] == {}
        assert result["data_status"] == "empty"

    def test_project_name_present_in_tokens_equal_to_zero(self):
        """by_project is empty when there are no token events — no name lookup needed."""
        from projections.api.queries.token_attribution import canonical_token_metrics

        conn = _make_db()
        _insert_project(conn, PROJECT_KNOWN, KNOWN_NAME)

        with _patch_conn(conn):
            result = canonical_token_metrics(days=30)

        # No token events, so by_project should be empty
        assert result["by_project"] == {}


# ==============================================================================
# Fix 2: SessionCollector — outcomes None key
# ==============================================================================


class TestSessionMetricsNoneOutcomes:
    def test_pydantic_model_accepts_none_mapped_to_unknown(self):
        """SessionMetrics should not raise if outcomes dict has 'unknown' key."""
        from projections.api.models.metrics import SessionMetrics

        data = {
            "total_sessions": 5,
            "outcomes": {"completed": 3, "unknown": 2},  # 'unknown' mapped from None
            "avg_duration_minutes": 12.5,
            "by_project": {},
            "timeline": [],
            "day_of_week": {},
            "success_rate": 0.6,
        }
        model = SessionMetrics(**data)
        assert model.outcomes["unknown"] == 2
        assert model.outcomes["completed"] == 3

    def test_session_collector_maps_none_outcome_to_unknown(self, tmp_path):
        """SessionCollector.collect() should not produce None keys in outcomes."""
        import sqlite3 as _sqlite3

        from projections.core.collectors.session_collector import SessionCollector

        db_file = tmp_path / "test.db"
        conn = _sqlite3.connect(str(db_file))
        conn.executescript(f"""
            CREATE TABLE raw_sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                outcome TEXT,
                project_id TEXT
            );
            INSERT INTO raw_sessions (session_id, started_at, ended_at, outcome, project_id) VALUES ('s1', '{NOW[:10]}T10:00:00', '{NOW[:10]}T10:05:00', NULL, NULL);
            INSERT INTO raw_sessions (session_id, started_at, ended_at, outcome, project_id) VALUES ('s2', '{NOW[:10]}T10:10:00', '{NOW[:10]}T10:15:00', 'completed', NULL);
        """)
        conn.commit()
        conn.close()

        collector = SessionCollector(str(db_file))
        result = collector.collect(days=30)

        # None key must not appear — should be mapped to "unknown"
        assert None not in result["outcomes"]
        assert "unknown" in result["outcomes"] or "completed" in result["outcomes"]

    def test_session_collector_none_outcome_counted_correctly(self, tmp_path, monkeypatch):
        """NULL outcome rows count toward 'unknown', not silently dropped.

        collect() prefers the DuckDB analytics store and only falls back to the
        seeded SQLite db_path when DuckDB is empty — so without isolating the
        DuckDB source this test reads the real analytics store (deterministic only
        on a clean CI runner). Force the SQLite path the test is exercising."""
        import sqlite3 as _sqlite3

        from projections.core.collectors.session_collector import SessionCollector

        monkeypatch.setattr(SessionCollector, "_collect_duckdb", lambda self, cutoff: None)

        db_file = tmp_path / "test.db"
        conn = _sqlite3.connect(str(db_file))
        conn.executescript(f"""
            CREATE TABLE raw_sessions (
                session_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                outcome TEXT,
                project_id TEXT
            );
            INSERT INTO raw_sessions (session_id, started_at, ended_at, outcome, project_id) VALUES ('s1', '{NOW[:10]}T10:00:00', NULL, NULL, NULL);
            INSERT INTO raw_sessions (session_id, started_at, ended_at, outcome, project_id) VALUES ('s2', '{NOW[:10]}T10:01:00', NULL, NULL, NULL);
            INSERT INTO raw_sessions (session_id, started_at, ended_at, outcome, project_id) VALUES ('s3', '{NOW[:10]}T10:02:00', NULL, 'completed', NULL);
        """)
        conn.commit()
        conn.close()

        collector = SessionCollector(str(db_file))
        result = collector.collect(days=30)

        assert None not in result["outcomes"]
        assert result["outcomes"].get("unknown", 0) == 2
        assert result["outcomes"].get("completed", 0) == 1
