from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from projections.api.main import app


def _client_for_db(db_path: Path, monkeypatch) -> TestClient:
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app)


def _minimal_db_without_alert_tables(tmp_path: Path) -> Path:
    db_path = tmp_path / "alerts-missing.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(77, '2026-05-14T00:00:00Z')"
        )
        conn.execute(
            "CREATE TABLE sla_definitions("
            "sla_id TEXT PRIMARY KEY, name TEXT, metric TEXT, target REAL, window INTEGER, sla_type TEXT, created_at TEXT, updated_at TEXT)"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _legacy_db_with_alert_history_only(tmp_path: Path) -> Path:
    db_path = tmp_path / "alerts-history-only.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(77, '2026-05-14T00:00:00Z')"
        )
        conn.execute(
            "CREATE TABLE alert_history("
            "alert_id TEXT PRIMARY KEY, rule_id TEXT, triggered_at TEXT NOT NULL, metric_value REAL, severity TEXT)"
        )
        conn.execute(
            "INSERT INTO alert_history(alert_id, rule_id, triggered_at, metric_value, severity) "
            "VALUES('alert-1', 'rule-1', '2026-05-14T00:00:00Z', 10.0, 'warning')"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_alert_routes_return_dashboard_safe_empty_states_when_tables_are_missing(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client_for_db(_minimal_db_without_alert_tables(tmp_path), monkeypatch)
    try:
        rules = client.get("/api/v1/alerts/rules")
        history = client.get("/api/v1/alerts/history")
        analytics = client.get("/api/v1/alerts/analytics")

        assert rules.status_code == 200
        assert history.status_code == 200
        assert analytics.status_code == 200
        assert rules.json() == []
        assert history.json() == []
        assert analytics.json()["top_triggered"] == []
        assert analytics.json()["resolution_times"][0]["range"] == "< 5 min"
        assert analytics.json()["source_status"]["classification"] == "empty by design"
    finally:
        DatabaseRuntime.reset_instance()


def test_alert_history_and_analytics_fall_back_when_rules_table_is_missing(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client_for_db(_legacy_db_with_alert_history_only(tmp_path), monkeypatch)
    try:
        rules = client.get("/api/v1/alerts/rules")
        history = client.get("/api/v1/alerts/history")
        analytics = client.get("/api/v1/alerts/analytics")

        assert rules.status_code == 200
        assert history.status_code == 200
        assert analytics.status_code == 200
        assert rules.json() == []
        assert history.json()[0]["alert_id"] == "alert-1"
        assert history.json()[0]["rule_name"] == "Unknown"
        assert analytics.json()["top_triggered"][0] == {"rule_name": "rule-1", "count": 1}
    finally:
        DatabaseRuntime.reset_instance()
