from __future__ import annotations

import sqlite3
from pathlib import Path

from core.config.sqlite_bootstrap import bootstrap_database, latest_migration_version
from core.telemetry.dashboard_freshness import dashboard_data_freshness_status


def _drift_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "dashboard-drift.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(38, '2026-05-14T00:00:00Z')"
        )
        conn.execute("CREATE TABLE raw_sessions(session_id TEXT PRIMARY KEY, created_at TEXT)")
        conn.execute(
            "CREATE TABLE raw_token_usage("
            "id INTEGER PRIMARY KEY, session_id TEXT, project_id TEXT, skill_name TEXT, "
            "input_tokens INTEGER, output_tokens INTEGER, model TEXT, recorded_at TEXT, event_id TEXT)"
        )
        conn.execute(
            "INSERT INTO raw_token_usage(session_id, project_id, skill_name, input_tokens, output_tokens, model, recorded_at, event_id) "
            "VALUES('s1', 'dream-studio', 'ds-core', 10, 15, 'gpt', '2026-05-14T00:00:00Z', 'event-1')"
        )
        conn.execute("CREATE TABLE raw_skill_telemetry(skill_name TEXT, invoked_at TEXT)")
        conn.execute(
            "INSERT INTO raw_skill_telemetry(skill_name, invoked_at) VALUES('ds-core', '2026-05-14T00:00:00Z')"
        )
        conn.execute("CREATE TABLE execution_events(event_id TEXT, created_at TEXT)")
        conn.execute(
            "INSERT INTO execution_events(event_id, created_at) VALUES('event-1', '2026-05-14T00:00:00Z')"
        )
        conn.execute("CREATE TABLE dashboard_attention_items(attention_id TEXT, created_at TEXT)")
        conn.execute(
            "CREATE TABLE token_usage_records("
            "token_usage_id TEXT, input_tokens INTEGER, output_tokens INTEGER, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO token_usage_records(token_usage_id, input_tokens, output_tokens, created_at) "
            "VALUES('token-1', 10, 15, '2026-05-14T00:00:00Z')"
        )
        conn.execute("CREATE TABLE validation_results(validation_id TEXT, created_at TEXT)")
        conn.execute("CREATE VIEW vw_security_summary AS SELECT 1 AS placeholder")
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_dashboard_freshness_classifies_schema_drift_and_backfill_candidates(
    tmp_path: Path,
) -> None:
    db_path = _drift_db(tmp_path)

    status = dashboard_data_freshness_status(db_path)

    assert status["model_name"] == "dashboard_data_freshness_status"
    assert status["derived_view"] is True
    assert status["primary_authority"] is False
    assert status["db_status"]["schema_version"] == 38
    sections = {item["section_id"]: item for item in status["section_statuses"]}
    assert sections["telemetry_overview"]["classification"] == "fresh"
    assert (
        sections["component_usage"]["classification"]
        == "missing because telemetry is not backfilled"
    )
    assert (
        sections["legacy_session_metrics"]["classification"]
        == "missing because live DB schema is behind repo migrations"
    )
    assert sections["legacy_token_metrics"]["classification"] == "fresh"
    assert (
        sections["security_dashboard"]["classification"]
        == "missing because live DB schema is behind repo migrations"
    )
    assert (
        sections["alerts_dashboard"]["classification"]
        == "missing because live DB schema is behind repo migrations"
    )
    assert status["backfill_status"]["execution_authorized"] is False
    assert status["backfill_status"]["candidate_count"] >= 1


def test_dashboard_freshness_has_no_authority_drift_after_latest_bootstrap(tmp_path: Path) -> None:
    db_path = tmp_path / "current-dashboard-authority.db"
    bootstrap_database(db_path)

    status = dashboard_data_freshness_status(db_path)

    assert status["db_status"]["schema_version"] == latest_migration_version()
    drift_objects = {item["object"] for item in status["schema_drift"]}
    assert "raw_sessions" not in drift_objects
    assert "vw_security_summary" not in drift_objects
    assert "alert_rules" not in drift_objects
    assert "alert_history" not in drift_objects

    sections = {item["section_id"]: item for item in status["section_statuses"]}
    assert sections["legacy_session_metrics"]["classification"] == "empty by design"
    assert sections["security_dashboard"]["classification"] == "empty by design"
    assert sections["alerts_dashboard"]["classification"] == "empty by design"
