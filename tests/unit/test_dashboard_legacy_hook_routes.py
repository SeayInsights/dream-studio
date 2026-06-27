from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from projections.api.main import app

# Migration 129 (WO-READMODELS-DUCKDB) dropped the SQLite hook_executions projection table.
# The /hooks/executions, /hooks/stats and /hooks/performance routes now read the DuckDB
# hook_executions VIEW (over system.hook.execution.logged events in events_fact). These tests
# isolate BOTH stores by pointing DREAM_STUDIO_HOME at a temp dir (which relocates the DuckDB
# aggregate_metrics.db via state_dir()) and seed the DuckDB store directly.

_HOOK_EVENT = "system.hook.execution.logged"


def _seed_duckdb_hook_event(
    home: Path,
    *,
    event_id: str,
    hook_name: str,
    hook_type: str,
    status: str,
    duration_ms: int,
    exit_code: int,
    timestamp: str,
    output: str | None = None,
    error_message: str | None = None,
) -> None:
    """Insert one hook-execution event_fact row into the temp DuckDB store."""
    import json

    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema

    conn = connect_analytics(home / "state" / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(conn)
        payload = {
            "hook_name": hook_name,
            "hook_type": hook_type,
            "started_at": timestamp,
            "completed_at": timestamp,
            "duration_ms": duration_ms,
            "exit_code": exit_code,
            "status": status,
            "output": output,
            "error_message": error_message,
        }
        conn.execute(
            "INSERT INTO events_fact (event_id, source, event_type, event_timestamp, "
            "duration_ms, exit_code, status, payload) VALUES (?, 'ai', ?, ?, ?, ?, ?, ?)",
            [event_id, _HOOK_EVENT, timestamp, duration_ms, exit_code, status, json.dumps(payload)],
        )
    finally:
        conn.close()


def _client_with_isolated_stores(tmp_path: Path) -> tuple[TestClient, Path]:
    """A TestClient with both the SQLite authority and DuckDB analytics store isolated to tmp.

    The DuckDB analytics schema (tables + read-model views) is created so an empty store
    presents the dashboard-safe empty shape — mirroring a fresh install where
    ensure_analytics_schema() runs at startup.
    """
    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema

    home = tmp_path / "ds-home"
    (home / "state").mkdir(parents=True, exist_ok=True)
    os.environ["DREAM_STUDIO_HOME"] = str(home)
    db_path = home / "state" / "studio.db"
    conn = _connect(db_path)
    conn.close()
    # Initialise the (empty) DuckDB analytics store so hook_executions VIEW exists.
    agg = connect_analytics(home / "state" / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(agg)
    finally:
        agg.close()
    DatabaseRuntime.reset_instance()
    os.environ[DB_PATH_ENV] = str(db_path)
    return TestClient(app), home


def _reset_env() -> None:
    DatabaseRuntime.reset_instance()
    os.environ.pop(DB_PATH_ENV, None)
    os.environ.pop("DREAM_STUDIO_HOME", None)


def test_legacy_hook_routes_return_empty_dashboard_safe_shapes(tmp_path: Path) -> None:
    client, _home = _client_with_isolated_stores(tmp_path)
    try:
        executions = client.get("/api/v1/hooks/executions", params={"limit": 50})
        stats = client.get("/api/v1/hooks/stats")

        assert executions.status_code == 200
        assert stats.status_code == 200
        # Empty DuckDB store → dashboard-safe empty shape.
        body = executions.json()
        assert body["count"] == 0
        assert body["executions"] == []
        assert stats.json()["summary"] == {
            "total_executions": 0,
            "total_successes": 0,
            "total_failures": 0,
            "overall_success_rate": 0.0,
        }
        assert stats.json()["by_hook"] == {}
    finally:
        _reset_env()


def test_legacy_hook_routes_return_seeded_dashboard_safe_shapes(tmp_path: Path) -> None:
    client, home = _client_with_isolated_stores(tmp_path)
    try:
        _seed_duckdb_hook_event(
            home,
            event_id="evt-hook-1",
            hook_name="on-tool-activity",
            hook_type="runtime",
            status="success",
            duration_ms=125,
            exit_code=0,
            timestamp="2026-05-13T19:00:00Z",
            output="ok",
        )

        executions = client.get("/api/v1/hooks/executions", params={"limit": 50})
        stats = client.get("/api/v1/hooks/stats")
        performance = client.get("/api/v1/hooks/performance")

        assert executions.status_code == 200
        assert stats.status_code == 200
        assert performance.status_code == 200
        payload = executions.json()
        assert payload["count"] == 1
        assert payload["executions"][0]["hook_name"] == "on-tool-activity"
        assert payload["executions"][0]["status"] == "success"
        assert payload["executions"][0]["is_anomaly"] is False
        assert stats.json()["summary"]["total_executions"] == 1
        assert stats.json()["summary"]["total_failures"] == 0
        assert stats.json()["summary"] == performance.json()["summary"]
    finally:
        _reset_env()


def test_legacy_hook_stats_counts_failures_from_duckdb(tmp_path: Path) -> None:
    client, home = _client_with_isolated_stores(tmp_path)
    try:
        _seed_duckdb_hook_event(
            home,
            event_id="evt-hook-fail",
            hook_name="on-pulse",
            hook_type="runtime",
            status="failed",
            duration_ms=200,
            exit_code=1,
            timestamp="2026-05-13T19:10:00Z",
            error_message="simulated failure",
        )

        stats = client.get("/api/v1/hooks/stats")
        performance = client.get("/api/v1/hooks/performance")

        assert stats.status_code == 200
        assert performance.status_code == 200
        assert stats.json()["summary"] == performance.json()["summary"]
        assert stats.json()["summary"]["total_executions"] == 1
        assert stats.json()["summary"]["total_failures"] == 1
        assert stats.json()["by_hook"]["on-pulse"]["failure_count"] == 1
    finally:
        _reset_env()


def test_telemetry_routes_still_pass_with_hook_route_db_injection(tmp_path: Path) -> None:
    client, _home = _client_with_isolated_stores(tmp_path)
    try:
        summary = client.get("/api/telemetry/summary")
        modules = client.get("/api/telemetry/modules")

        assert summary.status_code == 200
        assert modules.status_code == 200
        assert summary.json()["derived_view"] is True
        assert summary.json()["primary_authority"] is False
    finally:
        _reset_env()
