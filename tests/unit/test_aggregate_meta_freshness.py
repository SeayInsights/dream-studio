"""WO-DASH-COHERENCE T2: derive_events_fact stamps _aggregate_meta.last_aggregated_at on every
refresh, so the dashboard freshness signal reflects the actual events_fact state.

The bug: the incremental runner path (the sole steady-state events_fact writer) never updated the
stamp, so it read a stale 'last aggregated' time (days old) while events_fact was in fact current —
a misleading freshness signal. The fix stamps on every refresh, including the 0-new-rows steady
state.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from core.analytics import duckdb_store
from core.config.sqlite_bootstrap import bootstrap_database


def _analytics_conn(tmp_path: Path):
    conn = duckdb_store.connect_analytics(tmp_path / "aggregate_metrics.db", read_only=False)
    duckdb_store.ensure_analytics_schema(conn)
    return conn


def _stamp(conn) -> str | None:
    row = conn.execute(
        "SELECT value FROM _aggregate_meta WHERE key = 'last_aggregated_at'"
    ).fetchone()
    return row[0] if row else None


def test_refresh_stamps_freshness_even_with_no_new_events(tmp_path: Path):
    studio = tmp_path / "studio.db"
    bootstrap_database(studio)  # fresh: canonical event tables exist but are empty
    conn = _analytics_conn(tmp_path)
    try:
        assert _stamp(conn) is None, "precondition: no stamp before any refresh"
        duckdb_store.derive_events_fact(conn, str(studio))  # 0 new rows, but must still stamp
        stamp = _stamp(conn)
        assert stamp is not None, "refresh must set last_aggregated_at even with no new events"
        age = (datetime.now(UTC) - datetime.fromisoformat(stamp)).total_seconds()
        assert 0 <= age < 120, f"stamp should be ~now, got age {age}s"
    finally:
        conn.close()


def test_stamp_advances_on_subsequent_refresh(tmp_path: Path):
    studio = tmp_path / "studio.db"
    bootstrap_database(studio)
    conn = _analytics_conn(tmp_path)
    try:
        duckdb_store.derive_events_fact(conn, str(studio))
        first = _stamp(conn)
        duckdb_store.derive_events_fact(conn, str(studio))
        second = _stamp(conn)
        assert second >= first, "the freshness stamp must not go backwards on re-refresh"
    finally:
        conn.close()
