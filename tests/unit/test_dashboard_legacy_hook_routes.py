from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect, insert_hook_execution
from projections.api.main import app


def _client_with_db(tmp_path: Path) -> tuple[TestClient, Path]:
    db_path = tmp_path / "legacy-hooks.db"
    conn = _connect(db_path)
    conn.close()
    DatabaseRuntime.reset_instance()
    os.environ[DB_PATH_ENV] = str(db_path)
    return TestClient(app), db_path


def _reset_db_runtime() -> None:
    DatabaseRuntime.reset_instance()
    os.environ.pop(DB_PATH_ENV, None)


def test_legacy_hook_routes_return_empty_dashboard_safe_shapes(tmp_path: Path) -> None:
    client, db_path = _client_with_db(tmp_path)
    live_db_path = Path.home() / ".dream-studio" / "state" / "studio.db"
    try:
        executions = client.get("/api/v1/hooks/executions", params={"limit": 50})
        stats = client.get("/api/v1/hooks/stats")

        assert executions.status_code == 200
        assert stats.status_code == 200
        assert executions.json() == {
            "executions": [],
            "count": 0,
            "filters": {
                "hook_name": None,
                "status": None,
                "since": None,
                "limit": 50,
            },
        }
        assert stats.json()["summary"] == {
            "total_executions": 0,
            "total_successes": 0,
            "total_failures": 0,
            "overall_success_rate": 0.0,
        }
        assert stats.json()["by_hook"] == {}
        assert db_path != live_db_path
    finally:
        _reset_db_runtime()


def test_legacy_hook_routes_return_seeded_dashboard_safe_shapes(tmp_path: Path) -> None:
    client, db_path = _client_with_db(tmp_path)
    try:
        insert_hook_execution(
            hook_name="on-tool-activity",
            hook_type="runtime",
            trigger_context={"tool": "Read"},
            started_at="2026-05-13T19:00:00Z",
            completed_at="2026-05-13T19:00:01Z",
            duration_ms=125,
            exit_code=0,
            status="success",
            output="ok",
            db_path=db_path,
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
        _reset_db_runtime()


def test_legacy_hook_stats_tolerates_placeholder_performance_view(tmp_path: Path) -> None:
    client, db_path = _client_with_db(tmp_path)
    try:
        conn = _connect(db_path)
        conn.execute("DROP VIEW IF EXISTS vw_hook_performance")
        conn.execute("CREATE VIEW vw_hook_performance AS SELECT 1 AS placeholder")
        conn.commit()
        conn.close()

        insert_hook_execution(
            hook_name="on-pulse",
            hook_type="runtime",
            trigger_context={"source": "legacy-placeholder-view"},
            started_at="2026-05-13T19:10:00Z",
            completed_at="2026-05-13T19:10:02Z",
            duration_ms=200,
            exit_code=1,
            status="failed",
            error_message="simulated failure",
            db_path=db_path,
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
        _reset_db_runtime()


def test_telemetry_routes_still_pass_with_hook_route_db_injection(tmp_path: Path) -> None:
    client, _db_path = _client_with_db(tmp_path)
    try:
        summary = client.get("/api/telemetry/summary")
        modules = client.get("/api/telemetry/modules")

        assert summary.status_code == 200
        assert modules.status_code == 200
        assert summary.json()["derived_view"] is True
        assert summary.json()["primary_authority"] is False
    finally:
        _reset_db_runtime()
