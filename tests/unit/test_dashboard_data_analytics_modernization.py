from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.config.sqlite_bootstrap import latest_migration_version
from projections.api.main import app


def _client_for_db(db_path: Path, monkeypatch) -> TestClient:
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app)


def _modern_dashboard_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "dashboard-modernization.db"
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
        conn.execute(
            "CREATE TABLE reg_projects("
            "project_id TEXT PRIMARY KEY, project_path TEXT, project_name TEXT, project_type TEXT, "
            "git_remote TEXT, last_session_at TEXT, total_sessions INTEGER, total_tokens INTEGER, created_at TEXT, "
            "stack_detected TEXT, stack_json TEXT, adapter TEXT, health_score REAL, security_score REAL, "
            "maintainability_score REAL, total_files INTEGER, lines_of_code INTEGER, first_analyzed TEXT, "
            "last_analyzed TEXT, project_source TEXT, github_url TEXT, is_temp INTEGER, planning_path TEXT, "
            "sessions_path TEXT, project_uuid TEXT, deactivated_at TEXT, deactivation_reason TEXT, "
            "last_verified TEXT, auto_discovered INTEGER, status TEXT)"
        )
        conn.execute(
            "INSERT INTO reg_projects("
            "project_id, project_path, project_name, project_type, total_sessions, total_tokens, created_at, "
            "stack_detected, stack_json, health_score, security_score, maintainability_score, total_files, "
            "lines_of_code, first_analyzed, last_analyzed, is_temp, status"
            ") VALUES(?, ?, 'Dream Studio', 'local_first_ai_ops', 7, 1200, '2026-05-14T00:00:00Z', "
            "'Python FastAPI', ?, 91, 88, 93, 42, 4200, '2026-05-01T00:00:00Z', "
            "'2026-05-14T00:00:00Z', 0, 'active')",
            (
                "dream-studio",
                str(project_root),
                json.dumps(
                    {
                        "framework": "Python FastAPI",
                        "dependencies": ["fastapi", "pytest"],
                        "config_files": ["pyproject.toml"],
                        "entry_points": ["projections/api/main.py"],
                    }
                ),
            ),
        )
        for project_id in ("a", "b", "p1", "p2", "proj-1"):
            conn.execute(
                "INSERT INTO reg_projects(project_id, project_path, project_name, is_temp, status) "
                "VALUES(?, ?, ?, 1, 'quarantined')",
                (project_id, f"/{project_id}", "placeholder"),
            )
        conn.execute(
            "INSERT INTO reg_projects(project_id, project_path, project_name, is_temp, status) "
            "VALUES('core', '/missing/core', 'core', 0, 'quarantined')"
        )
        conn.execute(
            "CREATE TABLE prd_documents("
            "prd_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, status TEXT, created_at TEXT, "
            "approved_at TEXT, completed_at TEXT, total_tasks INTEGER, completed_tasks INTEGER)"
        )
        conn.execute(
            "INSERT INTO prd_documents(prd_id, project_id, title, status, created_at, total_tasks, completed_tasks) "
            "VALUES('prd-1', 'dream-studio', 'Current PRD', 'active', '2026-05-14T00:00:00Z', 10, 6)"
        )
        conn.execute("CREATE TABLE pi_bugs(project_id TEXT, status TEXT, severity TEXT)")
        conn.execute(
            "INSERT INTO pi_bugs(project_id, status, severity) VALUES('dream-studio', 'open', 'critical')"
        )
        conn.execute("CREATE TABLE pi_violations(project_id TEXT, status TEXT, severity TEXT)")
        conn.execute(
            "INSERT INTO pi_violations(project_id, status, severity) VALUES('dream-studio', 'open', 'high')"
        )
        conn.execute(
            "CREATE TABLE pi_dependencies(project_id TEXT, from_component TEXT, to_component TEXT, dependency_type TEXT, strength REAL)"
        )
        conn.execute(
            "INSERT INTO pi_dependencies(project_id, from_component, to_component, dependency_type, strength) "
            "VALUES('dream-studio', 'dashboard', 'telemetry_api', 'api_route', 1.0)"
        )
        conn.execute(
            "CREATE TABLE pi_improvements(project_id TEXT, status TEXT, priority_score REAL)"
        )
        conn.execute(
            "INSERT INTO pi_improvements(project_id, status, priority_score) VALUES('dream-studio', 'open', 8.5)"
        )
        conn.execute(
            "CREATE TABLE pi_analysis_runs("
            "run_id TEXT, project_id TEXT, run_type TEXT, started_at TEXT, completed_at TEXT, duration_seconds REAL, "
            "status TEXT, violations_found INTEGER, bugs_found INTEGER, improvements_suggested INTEGER)"
        )
        conn.execute(
            "INSERT INTO pi_analysis_runs(run_id, project_id, run_type, started_at, completed_at, duration_seconds, "
            "status, violations_found, bugs_found, improvements_suggested) "
            "VALUES('run-1', 'dream-studio', 'dashboard_authority', '2026-05-14T00:00:00Z', "
            "'2026-05-14T00:01:00Z', 60, 'completed', 1, 1, 1)"
        )
        # execution_events from migration 037 (_built_from_event_id added by migration 059)
        conn.execute(
            "CREATE TABLE execution_events("
            "event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, event_name TEXT NOT NULL, "
            "project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT, "
            "parent_event_id TEXT, actor_type TEXT, actor_id TEXT, agent_id TEXT, "
            "skill_id TEXT, workflow_id TEXT, hook_id TEXT, tool_id TEXT, model_id TEXT, "
            "adapter_id TEXT, source_refs_json TEXT NOT NULL DEFAULT '[]', "
            "evidence_refs_json TEXT NOT NULL DEFAULT '[]', metadata_json TEXT NOT NULL DEFAULT '{}', "
            "outcome_status TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _current_authority_without_legacy_project_intelligence_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "dashboard-current-authority.db"
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
        conn.execute(
            "CREATE TABLE reg_projects("
            "project_id TEXT PRIMARY KEY, project_path TEXT, project_name TEXT, stack_detected TEXT, stack_json TEXT, "
            "health_score REAL, security_score REAL, maintainability_score REAL, total_files INTEGER, lines_of_code INTEGER, "
            "first_analyzed TEXT, last_analyzed TEXT, total_sessions INTEGER, is_temp INTEGER, status TEXT)"
        )
        conn.execute(
            "INSERT INTO reg_projects(project_id, project_path, project_name, stack_detected, stack_json, "
            "health_score, security_score, maintainability_score, total_files, lines_of_code, first_analyzed, "
            "last_analyzed, total_sessions, is_temp, status) VALUES(?, ?, 'Dream Studio', 'Python FastAPI', ?, "
            "91, 88, 93, 42, 4200, '2026-05-01T00:00:00Z', '2026-05-14T00:00:00Z', 7, 0, 'active')",
            ("dream-studio", str(project_root), json.dumps({"framework": "Python FastAPI"})),
        )
        conn.execute(
            "CREATE TABLE prd_documents("
            "prd_id TEXT PRIMARY KEY, project_id TEXT, title TEXT, status TEXT, created_at TEXT, approved_at TEXT, "
            "completed_at TEXT, total_tasks INTEGER, completed_tasks INTEGER)"
        )
        conn.execute(
            "CREATE TABLE security_findings("
            "finding_id TEXT PRIMARY KEY, project_id TEXT, severity TEXT, category TEXT, file_path TEXT, "
            "start_line INTEGER, description TEXT, status TEXT, created_at TEXT)"
        )
        conn.execute(
            "INSERT INTO security_findings(finding_id, project_id, severity, category, file_path, start_line, "
            "description, status, created_at) VALUES('finding-1', 'dream-studio', 'high', 'guardrail', "
            "'app.py', 42, 'Real finding', 'open', '2026-05-14T00:00:00Z')"
        )
        conn.execute(
            "CREATE TABLE execution_events("
            "event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, event_name TEXT NOT NULL, "
            "project_id TEXT, milestone_id TEXT, task_id TEXT, process_run_id TEXT, "
            "parent_event_id TEXT, actor_type TEXT, actor_id TEXT, agent_id TEXT, "
            "skill_id TEXT, workflow_id TEXT, hook_id TEXT, tool_id TEXT, model_id TEXT, "
            "adapter_id TEXT, source_refs_json TEXT NOT NULL DEFAULT '[]', "
            "evidence_refs_json TEXT NOT NULL DEFAULT '[]', metadata_json TEXT NOT NULL DEFAULT '{}', "
            "outcome_status TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        conn.execute(
            "INSERT INTO execution_events(event_id, event_type, event_name, project_id, outcome_status, created_at) "
            "VALUES('event-1', 'validation', 'Dashboard smoke', 'dream-studio', 'passed', '2026-05-14T00:00:00Z')"
        )
        conn.execute(
            "CREATE TABLE pi_dependencies(project_id TEXT, from_component TEXT, to_component TEXT)"
        )
        conn.execute(
            "INSERT INTO pi_dependencies(project_id, from_component, to_component) "
            "VALUES('dream-studio', 'dashboard', 'telemetry_api')"
        )
        conn.commit()
    finally:
        conn.close()
    return db_path


def test_project_dashboard_excludes_quarantined_mock_rows_and_exposes_authority_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client_for_db(_modern_dashboard_db(tmp_path), monkeypatch)
    try:
        response = client.get("/api/v1/projects?limit=100")

        assert response.status_code == 200
        payload = response.json()
        assert payload["derived_view"] is True
        assert payload["primary_authority"] is False
        assert payload["source_status"]["classification"] == "fresh"
        assert payload["total"] == 1
        projects = payload["projects"]
        assert {project["project_id"] for project in projects} == {"dream-studio"}
        assert not {"a", "b", "p1", "p2", "proj-1", "core"} & {
            project["project_id"] for project in projects
        }

        project = projects[0]
        assert project["critical_bug_count"] == 1
        assert project["violation_count"] == 1
        assert project["dependency_count"] == 1
        assert project["path_status"] == "confirmed"
        assert project["stack_evidence"]["classification"] == "confirmed"
        assert project["stack_evidence"]["framework"] == "Python FastAPI"
        assert project["stack_evidence"]["dependency_count"] == 2
        assert project["dependency_source_status"]["classification"] == "confirmed"
    finally:
        DatabaseRuntime.reset_instance()


def test_project_health_drilldown_exposes_stack_and_confirmed_dependency_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client_for_db(_modern_dashboard_db(tmp_path), monkeypatch)
    try:
        response = client.get("/api/v1/projects/dream-studio/health")

        assert response.status_code == 200
        payload = response.json()
        project = payload["project"]
        assert project["stack_evidence"]["entry_points"] == ["projections/api/main.py"]
        assert (
            project["dependency_source_status"]["reason"]
            == "Dependency edges are read from pi_dependencies."
        )
        assert payload["bugs"]["critical"] == 1
        assert payload["violations"]["high"] == 1
        assert payload["improvements"]["high"] == 1
    finally:
        DatabaseRuntime.reset_instance()


def test_project_drilldowns_remove_absent_legacy_surfaces_and_bridge_current_authority(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client_for_db(
        _current_authority_without_legacy_project_intelligence_db(tmp_path), monkeypatch
    )
    try:
        health = client.get("/api/v1/projects/dream-studio/health")
        security = client.get("/api/v1/projects/dream-studio/security")
        activity = client.get("/api/v1/projects/dream-studio/activity")
        dependencies = client.get("/api/v1/projects/dream-studio/dependencies")

        assert health.status_code == 200
        payload = health.json()
        assert payload["available_surfaces"]["security"] is True
        assert payload["available_surfaces"]["activity"] is True
        assert payload["available_surfaces"]["dependencies"] is True
        assert payload["available_surfaces"]["health_trend"] is False
        assert payload["available_surfaces"]["bugs_summary"] is False
        assert payload["available_surfaces"]["violations_summary"] is False
        assert "health_trend" in payload["removed_surfaces"]
        assert "bugs_summary" in payload["removed_surfaces"]
        assert "violations_summary" in payload["removed_surfaces"]

        assert security.status_code == 200
        assert security.json()["source_status"]["source_tables"] == ["security_findings"]
        assert security.json()["findings"][0]["id"] == "finding-1"

        assert activity.status_code == 200
        assert activity.json()["source_status"]["source_tables"] == ["execution_events"]
        assert activity.json()["activities"][0]["message"] == "Dashboard smoke"

        assert dependencies.status_code == 200
        edge = dependencies.json()["edges"][0]
        assert edge["type"] == "confirmed"
        assert edge["strength"] == 1.0
    finally:
        DatabaseRuntime.reset_instance()
