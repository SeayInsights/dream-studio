from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from projections.api.main import app


def _client_for_db(db_path: Path, monkeypatch) -> TestClient:
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app)


def _portfolio_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "project-portfolio-authority.db"
    project_root = tmp_path / "dream-studio"
    project_root.mkdir()
    legacy_root = tmp_path / "historical-prd-project"
    legacy_root.mkdir()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(39, '2026-05-14T00:00:00Z')"
        )
        conn.execute(
            "CREATE TABLE reg_projects("
            "project_id TEXT PRIMARY KEY, project_path TEXT, project_name TEXT, stack_detected TEXT, stack_json TEXT, "
            "health_score REAL, security_score REAL, maintainability_score REAL, total_files INTEGER, lines_of_code INTEGER, "
            "first_analyzed TEXT, last_analyzed TEXT, total_sessions INTEGER, is_temp INTEGER, status TEXT, project_source TEXT)"
        )
        stack = json.dumps(
            {
                "framework": "Python FastAPI",
                "dependencies": ["fastapi", "sqlite"],
                "config_files": ["pyproject.toml", ".github/workflows/ci.yml"],
                "entry_points": ["projections/api/main.py", "projections/frontend/dashboard.html"],
            }
        )
        conn.execute(
            "INSERT INTO reg_projects(project_id, project_path, project_name, stack_detected, stack_json, "
            "health_score, security_score, maintainability_score, total_files, lines_of_code, first_analyzed, "
            "last_analyzed, total_sessions, is_temp, status, project_source) "
            "VALUES('dream-studio', ?, 'Dream Studio', 'Python FastAPI', ?, 99, 99, 99, 120, 12000, "
            "'2026-05-01T00:00:00Z', '2026-05-14T00:00:00Z', 12, 0, 'active', 'local_builds')",
            (str(project_root), stack),
        )
        conn.execute(
            "INSERT INTO reg_projects(project_id, project_path, project_name, stack_detected, stack_json, "
            "health_score, security_score, maintainability_score, total_files, lines_of_code, first_analyzed, "
            "last_analyzed, total_sessions, is_temp, status, project_source) "
            "VALUES('historical-prd-project', ?, 'Historical PRD Project', 'unknown', '{}', 10, 10, 10, 1, 1, "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 99, 0, 'active', 'legacy_prd')",
            (str(legacy_root),),
        )
        conn.execute(
            "INSERT INTO reg_projects(project_id, project_path, project_name, stack_detected, stack_json, "
            "health_score, security_score, maintainability_score, total_files, lines_of_code, first_analyzed, "
            "last_analyzed, total_sessions, is_temp, status, project_source) "
            "VALUES('pytest-temp-project', '/tmp/pytest-temp-project', 'pytest-temp-project', 'unknown', '{}', "
            "0, 0, 0, 0, 0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 0, 1, 'quarantined', 'local_builds')"
        )
        conn.execute(
            "CREATE TABLE prd_documents("
            "prd_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, status TEXT, file_path TEXT, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO prd_documents(prd_id, project_id, title, status, file_path, created_at) "
            "VALUES('dream-studio-current', 'dream-studio', 'Dream Studio PRD', 'in-progress', "
            "'docs/product/dream-studio-prd.md', '2026-05-14T00:00:00Z')"
        )
        conn.execute(
            "CREATE TABLE security_findings("
            "finding_id TEXT PRIMARY KEY, project_id TEXT, severity TEXT, category TEXT, file_path TEXT, "
            "start_line INTEGER, description TEXT, status TEXT, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO security_findings(finding_id, project_id, severity, category, file_path, start_line, "
            "description, status, created_at) VALUES('finding-1', 'dream-studio', 'medium', 'ci', "
            "'.github/workflows/ci.yml', 1, 'Real CI finding', 'open', '2026-05-14T00:00:00Z')"
        )
        conn.execute(
            "CREATE TABLE dashboard_attention_items(item_id TEXT, project_id TEXT, status TEXT)"
        )
        conn.execute(
            "INSERT INTO dashboard_attention_items VALUES('attention-1', 'dream-studio', 'open')"
        )
        conn.execute(
            "CREATE TABLE validation_results(result_id TEXT, project_id TEXT, status TEXT)"
        )
        conn.execute(
            "INSERT INTO validation_results VALUES('validation-1', 'dream-studio', 'passed')"
        )
        conn.execute(
            "INSERT INTO validation_results VALUES('validation-2', 'dream-studio', 'failed')"
        )
        conn.execute("CREATE TABLE execution_events(event_id TEXT, project_id TEXT)")
        conn.execute("INSERT INTO execution_events VALUES('event-1', 'dream-studio')")
        conn.execute(
            "CREATE TABLE route_decision_records("
            "record_id TEXT, project_id TEXT, handoff_required INTEGER, operator_action_required INTEGER, "
            "prompt_required INTEGER, recommended_next_work_order TEXT)"
        )
        conn.execute(
            "INSERT INTO route_decision_records VALUES('route-1', 'dream-studio', 0, 0, 0, 'none')"
        )
        conn.execute(
            "CREATE TABLE pi_dependencies(project_id TEXT, from_component TEXT, to_component TEXT)"
        )
        conn.execute(
            "INSERT INTO pi_dependencies VALUES('dream-studio', 'dashboard', 'telemetry_api')"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_all_projects_defaults_to_current_local_builds_authority(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client_for_db(_portfolio_db(tmp_path), monkeypatch)
    try:
        response = client.get("/api/v1/projects?limit=100")

        assert response.status_code == 200
        payload = response.json()
        assert payload["derived_view"] is True
        assert payload["primary_authority"] is False
        assert payload["total"] == 1
        assert {project["project_id"] for project in payload["projects"]} == {"dream-studio"}
        project = payload["projects"][0]
        assert project["prd_status"]["latest_status"] == "in-progress"
        assert project["security_package_status"]["open_findings"] == 1
        assert (
            project["security_lifecycle_status"]["source_framework"]["source_control_count"] == 47
        )
        assert project["security_lifecycle_status"]["security_status"] == "blocked_by_open_findings"
        assert (
            project["security_lifecycle_status"]["finding_normalization_policy"][
                "synthetic_demo_findings_in_live_operator_views"
            ]
            is False
        )
        assert project["work_order_status"]["attention_open"] == 1
        assert project["telemetry_status"]["event_count"] == 1
        assert project["health_model"]["derived_view"] is True
        assert project["health_model"]["primary_authority"] is False
        assert project["health_model"]["signals"]["validation_failed_count"] == 1
        assert project["health_score"] == project["health_model"]["score"] / 10
        assert "security_findings" in payload["source_status"]["source_tables"]
        assert "dashboard_attention_items" in payload["source_status"]["source_tables"]
        assert "execution_events" in payload["source_status"]["source_tables"]
    finally:
        DatabaseRuntime.reset_instance()


def test_project_health_uses_current_authority_when_legacy_tables_are_absent(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client_for_db(_portfolio_db(tmp_path), monkeypatch)
    try:
        response = client.get("/api/v1/projects/dream-studio/health")

        assert response.status_code == 200
        payload = response.json()
        assert payload["project"]["prd_status"]["count"] == 1
        assert payload["project"]["security_package_status"]["open_findings"] == 1
        assert (
            payload["project"]["security_lifecycle_status"]["security_status"]
            == "blocked_by_open_findings"
        )
        assert payload["project"]["health_model"]["status"] == "scored"
        assert payload["health"]["overall_score"] == payload["project"]["health_score"]
        assert payload["health"]["security_score"] == payload["project"]["security_score"]
        assert payload["available_surfaces"]["bugs_summary"] is False
        assert payload["available_surfaces"]["violations_summary"] is False
        assert "bugs_summary" in payload["removed_surfaces"]
        assert "violations_summary" in payload["removed_surfaces"]
    finally:
        DatabaseRuntime.reset_instance()


def test_security_dashboard_findings_keep_project_attribution(tmp_path: Path, monkeypatch) -> None:
    client = _client_for_db(_portfolio_db(tmp_path), monkeypatch)
    try:
        response = client.get("/api/v1/security/findings?limit=100")

        assert response.status_code == 200
        payload = response.json()
        assert payload["count"] == 1
        finding = payload["findings"][0]
        assert finding["id"] == "finding-1"
        assert finding["project_id"] == "dream-studio"
        assert finding["file_path"] == ".github/workflows/ci.yml"
        assert finding["message"] == "Real CI finding"
    finally:
        DatabaseRuntime.reset_instance()
