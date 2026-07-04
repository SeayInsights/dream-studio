from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, UTC
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.config.sqlite_bootstrap import latest_migration_version
from projections.api.main import app


def _schema_drift_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "dashboard-live-schema-drift.db"
    project_root = tmp_path / "dream-studio"
    project_root.mkdir()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, '2026-05-14T00:00:00Z')",
            (latest_migration_version(),),
        )
        conn.execute("CREATE TABLE raw_sessions(session_id TEXT PRIMARY KEY, created_at TEXT)")
        conn.execute(
            "CREATE TABLE raw_token_usage("
            "id INTEGER PRIMARY KEY, session_id TEXT, project_id TEXT, skill_name TEXT, "
            "input_tokens INTEGER, output_tokens INTEGER, model TEXT, recorded_at TEXT, event_id TEXT)"
        )
        conn.execute(
            "INSERT INTO raw_token_usage(session_id, project_id, skill_name, input_tokens, output_tokens, model, recorded_at, event_id) "
            "VALUES('s1', 'dream-studio', 'ds-core', 10, 20, 'gpt', '2026-05-14T00:00:00Z', 'event-1')"
        )
        conn.execute(
            "CREATE TABLE token_usage_records("
            "token_usage_id TEXT PRIMARY KEY, project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT, "
            "agent_id TEXT, skill_id TEXT, workflow_id TEXT, hook_id TEXT, model_id TEXT, provider TEXT, "
            "input_tokens INTEGER, output_tokens INTEGER, cached_tokens INTEGER, total_tokens INTEGER, "
            "estimated_cost REAL, purpose TEXT, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO token_usage_records(token_usage_id, project_id, process_run_id, skill_id, model_id, provider, "
            "input_tokens, output_tokens, cached_tokens, total_tokens, estimated_cost, purpose, created_at) "
            "VALUES('token-1', 'dream-studio', 's1', 'ds-core', 'gpt', 'openai', 10, 20, 0, 30, 0.0, "
            "'migrated historical token usage', '2026-05-14T00:00:00Z')"
        )
        # reg_projects deleted in migration 084; use business_projects
        conn.execute(
            "CREATE TABLE business_projects("
            "project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, "
            "status TEXT NOT NULL DEFAULT 'active', project_path TEXT, "
            "detected_stack TEXT, stack_json TEXT, total_sessions INTEGER DEFAULT 0, "
            "total_tokens INTEGER DEFAULT 0, last_session_at TEXT, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "source_event_id TEXT, last_event_id TEXT)"
        )
        conn.execute(
            "INSERT INTO business_projects(project_id, name, description, status, project_path, "
            "detected_stack, total_sessions, created_at, updated_at) "
            "VALUES('dream-studio', 'Dream Studio', 'application', 'active', ?, 'python', "
            "5, '2026-05-01T00:00:00Z', '2026-05-14T00:00:00Z')",
            (str(project_root),),
        )
        # pytest-temp-project → status='deleted' (replaces old is_temp=1/inactive exclusion)
        conn.execute(
            "INSERT INTO business_projects(project_id, name, description, status, project_path, "
            "detected_stack, total_sessions, created_at, updated_at) "
            "VALUES('pytest-temp-project', 'pytest-temp-project', '', 'deleted', "
            "'C:/Temp/pytest-temp-project', 'python', 0, '2026-05-01T00:00:00Z', '2026-05-14T00:00:00Z')"
        )
        conn.execute("CREATE VIEW vw_security_summary AS SELECT 1 AS placeholder")
        # canonical_events required by /api/v1/metrics/tokens (canonical_token_metrics reads from it).
        conn.execute(
            "CREATE TABLE canonical_events("
            "event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, timestamp TEXT NOT NULL, "
            "trace JSON NOT NULL DEFAULT '{}', severity TEXT NOT NULL DEFAULT 'info', "
            "payload JSON NOT NULL DEFAULT '{}', actor JSON, confidence_score REAL, "
            "source_type TEXT, raw_prompt_retained INTEGER NOT NULL DEFAULT 0, "
            "raw_tool_output_retained INTEGER NOT NULL DEFAULT 0, "
            "schema_version INTEGER NOT NULL DEFAULT 1, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, invocation_mode TEXT)"
        )
        recent_ts = (datetime.now(UTC) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        conn.execute(
            "INSERT INTO canonical_events(event_id, event_type, timestamp, trace, severity, payload) "
            "VALUES('token-evt-1', 'token.consumed', ?, "
            "'{\"project_id\": \"dream-studio\"}', 'info', "
            '\'{"input_tokens": 10, "output_tokens": 20}\')',
            (recent_ts,),
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _client(tmp_path: Path, monkeypatch) -> TestClient:
    db_path = _schema_drift_db(tmp_path)
    # Isolate the DuckDB analytics store too: /hooks/stats reads the DuckDB
    # hook_executions VIEW (migration 129, WO-READMODELS-DUCKDB), not SQLite. Point
    # DREAM_STUDIO_HOME at tmp so state_dir()/aggregate_metrics.db is an isolated,
    # empty analytics store and the route returns the dashboard-safe zero shape.
    home = tmp_path / "ds-home"
    (home / "state").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("DREAM_STUDIO_HOME", str(home))
    from core.analytics.duckdb_store import connect_analytics, ensure_analytics_schema

    agg = connect_analytics(home / "state" / "aggregate_metrics.db", read_only=False)
    try:
        ensure_analytics_schema(agg)
    finally:
        agg.close()
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app)


def test_legacy_dashboard_routes_tolerate_live_schema_drift(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    try:
        expectations = {
            "/api/v1/metrics/sessions": 200,
            "/api/v1/metrics/tokens": 200,
            "/api/v1/projects?limit=50": 200,
            "/api/v1/security/findings?limit=50": 200,
            "/api/v1/security/stats": 200,
            "/api/v1/analytics/anomalies": 200,
            "/api/v1/analytics/trends": 200,
            "/api/v1/analytics/performance": 200,
            "/api/v1/hooks/executions?limit=50": 200,
            "/api/v1/hooks/stats": 200,
        }

        for path, status_code in expectations.items():
            assert client.get(path).status_code == status_code, path
    finally:
        DatabaseRuntime.reset_instance()


def test_legacy_dashboard_route_empty_and_fallback_shapes_are_dashboard_safe(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    try:
        sessions = client.get("/api/v1/metrics/sessions").json()
        tokens = client.get("/api/v1/metrics/tokens").json()
        projects = client.get("/api/v1/projects?limit=50").json()
        security = client.get("/api/v1/security/findings?limit=50").json()
        hooks = client.get("/api/v1/hooks/stats").json()

        assert sessions["total_sessions"] == 0
        assert tokens["total_tokens"] == 30
        assert tokens["by_project"]["dream-studio"]["total_tokens"] == 30
        assert projects["projects"][0]["prd_count"] == 0
        assert projects["total"] == 1
        assert {project["project_id"] for project in projects["projects"]} == {"dream-studio"}
        assert (
            security["findings"] == []
        )  # security_events absent in drift schema → empty by design (findings_current_status dropped migration 140)
        assert (
            hooks["summary"]["total_executions"] == 0
        )  # hook_executions absent in drift schema → 0
    finally:
        DatabaseRuntime.reset_instance()
