"""Regression tests for WO-DASH-GRAPHS-500.

The dashboard "trends" and "performance" graphs rendered blank because their
endpoints 500'd on the VARCHAR timestamp columns of the DuckDB raw_sessions
view (started_at = events_fact.event_timestamp, a VARCHAR ISO string):

  * /api/v1/analytics/trends mixed DATE(started_at) -> datetime.date (sessions)
    with substr(created_at) -> str (tokens) in one sorted(set(...)) -> TypeError.
  * /api/v1/analytics/performance called strftime(started_at, '%w'/'%H') on a
    VARCHAR -> DuckDB BinderException.

These tests seed one session event into an isolated DuckDB store (started_at as
a VARCHAR ISO string, the shape that broke both handlers) and assert both
endpoints return 200 with a usable shape. The seed timestamp is anchored
relative to now so it always falls inside the default query window (never a
hardcoded absolute date).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from projections.api.main import app


def _client_with_isolated_stores(tmp_path: Path) -> tuple[TestClient, Path]:
    """TestClient with the SQLite authority and DuckDB analytics store isolated to tmp."""
    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema

    home = tmp_path / "ds-home"
    (home / "state").mkdir(parents=True, exist_ok=True)
    os.environ["DREAM_STUDIO_HOME"] = str(home)
    db_path = home / "state" / "studio.db"
    _connect(db_path).close()
    agg = connect_analytics(home / "state" / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(agg)
    finally:
        agg.close()
    DatabaseRuntime.reset_instance()
    os.environ[DB_PATH_ENV] = str(db_path)
    return TestClient(app), home


def _seed_session(home: Path, *, session_id: str, started_at: str, outcome: str) -> None:
    """Insert one system.session.recorded row so the raw_sessions view has a
    started_at (= event_timestamp, a VARCHAR ISO string — the bug's trigger)."""
    from core.analytics.duckdb_store import connect_analytics

    conn = connect_analytics(home / "state" / "aggregate_metrics.db", read_only=False)
    try:
        conn.execute(
            "INSERT INTO events_fact (event_id, source, event_type, event_timestamp, "
            "session_id, outcome, input_tokens, output_tokens, payload) "
            "VALUES (?, 'ai', 'system.session.recorded', ?, ?, ?, ?, ?, ?)",
            [
                f"evt-{session_id}",
                started_at,
                session_id,
                outcome,
                100,
                50,
                json.dumps({"session_id": session_id, "outcome": outcome}),
            ],
        )
    finally:
        conn.close()


def _reset_env() -> None:
    DatabaseRuntime.reset_instance()
    os.environ.pop(DB_PATH_ENV, None)
    os.environ.pop("DREAM_STUDIO_HOME", None)


def _recent_iso() -> str:
    """A full ISO timestamp one day ago — inside the default 30-day window."""
    return (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()


def test_trends_200(tmp_path: Path) -> None:
    client, home = _client_with_isolated_stores(tmp_path)
    try:
        _seed_session(home, session_id="s-trends", started_at=_recent_iso(), outcome="success")
        resp = client.get("/api/v1/analytics/trends", params={"days": 30})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "trends" in body and "dates" in body
        # The seeded session must appear as a string date (no mixed-type sort crash).
        assert all(isinstance(d, str) for d in body["dates"])
        assert body["dates"], "seeded session should produce at least one trend date"
    finally:
        _reset_env()


def test_performance_200(tmp_path: Path) -> None:
    client, home = _client_with_isolated_stores(tmp_path)
    try:
        _seed_session(home, session_id="s-perf", started_at=_recent_iso(), outcome="success")
        resp = client.get("/api/v1/analytics/performance", params={"days": 30})
        assert resp.status_code == 200, resp.text
        body = resp.json()
        # strftime over the VARCHAR started_at must not crash; shape is present.
        assert "day_of_week" in body and len(body["day_of_week"]) == 7
        assert "hourly_activity" in body
        assert body["session_flow"]["started"] >= 1
    finally:
        _reset_env()
