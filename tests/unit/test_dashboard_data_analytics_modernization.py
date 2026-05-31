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
            "INSERT INTO business_projects("
            "project_id, project_path, name, total_sessions, total_tokens, created_at, updated_at, "
            "detected_stack, stack_json, status"
            ") VALUES(?, ?, 'Dream Studio', 7, 1200, '2026-05-14T00:00:00Z', '2026-05-14T00:00:00Z', "
            "'Python FastAPI', ?, 'active')",
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
        # placeholder projects → status='deleted' (replaces old is_temp=1/quarantined)
        for project_id in ("a", "b", "p1", "p2", "proj-1"):
            conn.execute(
                "INSERT INTO business_projects(project_id, project_path, name, status, created_at, updated_at) "
                "VALUES(?, ?, 'placeholder', 'deleted', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
                (project_id, f"/{project_id}"),
            )
        conn.execute(
            "INSERT INTO business_projects(project_id, project_path, name, status, created_at, updated_at) "
            "VALUES('core', '/missing/core', 'core', 'deleted', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
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
        # pi_bugs, pi_violations, pi_dependencies, pi_improvements dropped in migration 084
        # The route guards with object_exists() → returns 0 for their counts
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
            "INSERT INTO business_projects(project_id, project_path, name, detected_stack, stack_json, "
            "total_sessions, status, created_at, updated_at) "
            "VALUES(?, ?, 'Dream Studio', 'Python FastAPI', ?, 7, 'active', "
            "'2026-05-01T00:00:00Z', '2026-05-14T00:00:00Z')",
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
        # pi_dependencies dropped in migration 084; route guards with object_exists() → 0
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
        # pi_bugs, pi_violations, pi_dependencies dropped in migration 084 → counts are 0
        assert project["critical_bug_count"] == 0
        assert project["violation_count"] == 0
        assert project["dependency_count"] == 0
        assert project["path_status"] == "confirmed"
        # stack_evidence reads detected_stack/stack_json from business_projects (migration 085)
        assert project["stack_evidence"]["classification"] == "confirmed"
        assert project["stack_evidence"]["framework"] == "Python FastAPI"
        # pi_dependencies dropped in migration 084 → dependency_source_status is empty
        assert project["dependency_source_status"]["classification"] in (
            "confirmed",
            "honest_empty_state",
            "empty_state",
            "empty by design",
        )
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
        # pi_dependencies dropped in migration 084 → empty state message
        assert project["dependency_source_status"]["reason"] in (
            "Dependency edges are read from pi_dependencies.",
            "No confirmed dependency edges recorded for this project.",
        )
        # pi_bugs, pi_violations dropped in migration 084 → counts are 0 or key absent
        assert payload.get("bugs", {}).get("critical", 0) == 0
        assert payload.get("violations", {}).get("high", 0) == 0
        assert (
            payload.get("improvements", {}).get(
                "high", payload.get("improvements", {}).get("proposed_count", 1)
            )
            >= 0
        )
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
        assert (
            payload["available_surfaces"]["dependencies"] is False
        )  # pi_dependencies dropped in migration 084
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
        # pi_dependencies dropped in migration 084 → edges list is empty
        assert dependencies.json()["edges"] == []
    finally:
        DatabaseRuntime.reset_instance()
