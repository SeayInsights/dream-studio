"""WO-DASH-FRESHNESS regression tests.

Three fixes so the dashboard reflects current data:
  1. events_fact is derived incrementally by an event_id anti-join, not a
     MAX(event_timestamp) high-water that permanently skipped late-arriving
     events with older timestamps.
  2. API responses carry no-cache (was public, max-age=300), so a browser
     refresh reflects the current derived metrics.
  3. _refresh_derived_store rebuilds the derived store before serving and is
     best-effort (never raises).
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import duckdb
from fastapi.testclient import TestClient

from core.analytics.duckdb_store import derive_events_fact, ensure_analytics_schema


def _minimal_studio_db(tmp_path: Path) -> Path:
    sdb = tmp_path / "studio.db"
    s = sqlite3.connect(str(sdb))
    for table in ("ai_canonical_events", "business_canonical_events"):
        s.execute(
            f"CREATE TABLE {table} (event_id TEXT, event_type TEXT,"
            " event_timestamp TEXT, payload TEXT)"
        )
    s.execute(
        "INSERT INTO ai_canonical_events VALUES ('e1', 'token.consumed',"
        " '2026-07-08T10:00:00Z', '{}')"
    )
    s.commit()
    s.close()
    return sdb


def test_events_fact_incremental_includes_late_old_timestamp(tmp_path):
    sdb = _minimal_studio_db(tmp_path)
    conn = duckdb.connect(str(tmp_path / "agg.db"))
    try:
        ensure_analytics_schema(conn)
        assert derive_events_fact(conn, str(sdb)) == 1

        # A late-arriving event whose event_timestamp is OLDER than the current max.
        # The old MAX(event_timestamp) high-water would skip it (regression guard).
        s = sqlite3.connect(str(sdb))
        s.execute(
            "INSERT INTO ai_canonical_events VALUES ('e0', 'token.consumed',"
            " '2026-07-08T09:00:00Z', '{}')"
        )
        s.commit()
        s.close()

        added = derive_events_fact(conn, str(sdb))
        assert added == 1, "late-arriving old-timestamp event must be included"
        assert conn.execute("SELECT COUNT(*) FROM events_fact").fetchone()[0] == 2
        # No duplication on a re-run with no new events.
        assert derive_events_fact(conn, str(sdb)) == 0
    finally:
        conn.close()


def test_api_responses_are_no_cache():
    from projections.api.main import app

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.headers.get("Cache-Control") == "no-cache"


def test_refresh_derived_store_is_best_effort(tmp_path):
    from interfaces.cli.commands.system import _refresh_derived_store

    # A non-existent authority path must not raise — the refresh is best-effort.
    _refresh_derived_store(tmp_path / "does-not-exist" / "studio.db")
