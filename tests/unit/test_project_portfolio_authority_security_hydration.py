from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from core.production_readiness import build_secure_production_readiness_gate
from projections.api.main import app


def _client_for_db(db_path: Path, monkeypatch) -> TestClient:
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app)


def _portfolio_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "project-portfolio-authority.db"
    project_root = tmp_path / "dream-studio"
    project_root.mkdir()
    (project_root / "pyproject.toml").write_text(
        """
[project]
name = "dream-studio"
dependencies = ["fastapi", "pydantic"]
""".strip(),
        encoding="utf-8",
    )
    (project_root / ".github" / "workflows").mkdir(parents=True)
    (project_root / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\n",
        encoding="utf-8",
    )
    (project_root / "projections" / "api" / "routes").mkdir(parents=True)
    (project_root / "projections" / "api" / "routes" / "example.py").write_text(
        "from fastapi import APIRouter\nrouter = APIRouter()\n",
        encoding="utf-8",
    )
    legacy_root = tmp_path / "historical-prd-project"
    legacy_root.mkdir()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE _schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO _schema_version(version, applied_at) VALUES(77, '2026-05-14T00:00:00Z')"
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
        demo_root = tmp_path / "demo-project"
        demo_root.mkdir()
        conn.execute(
            "INSERT INTO reg_projects(project_id, project_path, project_name, stack_detected, stack_json, "
            "health_score, security_score, maintainability_score, total_files, lines_of_code, first_analyzed, "
            "last_analyzed, total_sessions, is_temp, status, project_source) "
            "VALUES('demo-project', ?, 'demo-project', 'unknown', '{}', "
            "0, 0, 0, 1, 1, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', 0, 0, 'active', 'local_builds')",
            (str(demo_root),),
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
        conn.execute(
            "CREATE TABLE execution_events("
            "event_id TEXT PRIMARY KEY, event_type TEXT NOT NULL, event_name TEXT NOT NULL, "
            "project_id TEXT, outcome_status TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')))"
        )
        conn.execute(
            "INSERT INTO execution_events(event_id, event_type, event_name, project_id, outcome_status) "
            "VALUES('event-1', 'bootstrap.test', 'Test event', 'dream-studio', 'passed')"
        )
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
            "CREATE TABLE pi_components(component_id TEXT, project_id TEXT, path TEXT, name TEXT, component_type TEXT)"
        )
        conn.execute(
            "INSERT INTO pi_components VALUES('dashboard', 'dream-studio', 'projections/frontend/dashboard.html', 'Dashboard', 'frontend')"
        )
        conn.execute(
            "INSERT INTO pi_components VALUES('telemetry_api', 'dream-studio', 'projections/api/routes/telemetry.py', 'Telemetry API', 'api')"
        )
        conn.execute(
            "INSERT INTO pi_dependencies VALUES('dream-studio', 'dashboard', 'telemetry_api')"
        )
        # Migration 040: production readiness tables required by build_secure_production_readiness_gate.
        conn.execute(
            "CREATE TABLE production_readiness_assessment_runs("
            "assessment_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, workflow_id TEXT NOT NULL, "
            "lifecycle_event TEXT NOT NULL, status TEXT NOT NULL, confidence TEXT NOT NULL, "
            "full_review_required INTEGER NOT NULL DEFAULT 0, release_readiness_effect TEXT NOT NULL, "
            "health_score_json TEXT NOT NULL DEFAULT '{}', readiness_score_json TEXT NOT NULL DEFAULT '{}', "
            "missing_evidence_json TEXT NOT NULL DEFAULT '[]', blocking_factors_json TEXT NOT NULL DEFAULT '[]', "
            "source_refs_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE production_readiness_control_results("
            "result_id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL, project_id TEXT NOT NULL, "
            "control_id TEXT NOT NULL, control_family TEXT NOT NULL, name TEXT NOT NULL, "
            "skill_owner TEXT NOT NULL, workflow_owner TEXT NOT NULL, applicability TEXT NOT NULL, "
            "status TEXT NOT NULL, severity TEXT NOT NULL, blocking INTEGER NOT NULL DEFAULT 0, "
            "score_impact REAL, evidence_refs_json TEXT NOT NULL DEFAULT '[]', "
            "source_refs_json TEXT NOT NULL DEFAULT '[]', file_path TEXT, line INTEGER, "
            "remediation_work_order TEXT, reason_not_applicable TEXT, created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE production_readiness_findings("
            "finding_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, assessment_id TEXT NOT NULL, "
            "control_id TEXT NOT NULL, control_family TEXT NOT NULL, skill_owner TEXT NOT NULL, "
            "workflow_owner TEXT NOT NULL, applicability TEXT NOT NULL, status TEXT NOT NULL, "
            "severity TEXT NOT NULL, blocking INTEGER NOT NULL DEFAULT 0, score_impact REAL, "
            "evidence_refs_json TEXT NOT NULL DEFAULT '[]', source_refs_json TEXT NOT NULL DEFAULT '[]', "
            "file_path TEXT, line INTEGER, remediation_work_order TEXT, reason_not_applicable TEXT, "
            "created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE production_readiness_remediation_work_orders("
            "remediation_work_order_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, "
            "assessment_id TEXT NOT NULL, control_id TEXT NOT NULL, finding_id TEXT, "
            "status TEXT NOT NULL, recommended_phase_type TEXT NOT NULL, objective TEXT NOT NULL, "
            "evidence_refs_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE production_readiness_skill_control_mappings("
            "mapping_id TEXT PRIMARY KEY, control_id TEXT NOT NULL, control_family TEXT NOT NULL, "
            "existing_skill_or_check TEXT NOT NULL, proposed_canonical_owner TEXT NOT NULL, "
            "overlap_reason TEXT NOT NULL, decision TEXT NOT NULL, evidence_json TEXT NOT NULL DEFAULT '[]', "
            "validation_requirement TEXT NOT NULL, rollback_or_supersession_plan TEXT NOT NULL, "
            "dashboard_project_health_impact TEXT NOT NULL, contract_atlas_impact TEXT NOT NULL, "
            "created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE project_readiness_scorecards("
            "scorecard_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, assessment_id TEXT NOT NULL, "
            "readiness_score REAL, confidence TEXT NOT NULL, status TEXT NOT NULL, "
            "missing_evidence_json TEXT NOT NULL DEFAULT '[]', blocking_factors_json TEXT NOT NULL DEFAULT '[]', "
            "evidence_refs_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE project_health_scorecards("
            "scorecard_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, assessment_id TEXT NOT NULL, "
            "health_score REAL, confidence TEXT NOT NULL, status TEXT NOT NULL, "
            "missing_evidence_json TEXT NOT NULL DEFAULT '[]', blocking_factors_json TEXT NOT NULL DEFAULT '[]', "
            "evidence_refs_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE release_readiness_records("
            "release_readiness_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, assessment_id TEXT NOT NULL, "
            "status TEXT NOT NULL, release_readiness_effect TEXT NOT NULL, "
            "blocker_count INTEGER NOT NULL DEFAULT 0, manual_review_count INTEGER NOT NULL DEFAULT 0, "
            "evidence_refs_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE compliance_review_flags("
            "flag_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, assessment_id TEXT NOT NULL, "
            "control_id TEXT NOT NULL, flag_type TEXT NOT NULL, status TEXT NOT NULL, reason TEXT NOT NULL, "
            "evidence_refs_json TEXT NOT NULL DEFAULT '[]', created_at TEXT NOT NULL)"
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
        assert payload["source_status"]["excluded_from_default_view"]["count"] == 1
        assert (
            "demo-project"
            in payload["source_status"]["excluded_from_default_view"]["sample_project_ids"]
        )
        project = payload["projects"][0]
        assert project["project_authority_status"]["include_in_default_operator_view"] is True
        assert project["project_authority_status"]["classification"] == "current_legitimate_project"
        assert project["prd_status"]["status"] == "needs_update"
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


def test_project_security_uses_high_confidence_legacy_alias(tmp_path: Path, monkeypatch) -> None:
    db_path = _portfolio_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO security_findings(finding_id, project_id, severity, category, file_path, start_line, "
            "description, status, created_at) VALUES('finding-alias', 'project_dream_studio', 'HIGH', 'legacy', "
            "'core/security/lifecycle.py', 10, 'Legacy mapped finding', 'open', '2026-05-14T00:00:00Z')"
        )
        conn.commit()
    client = _client_for_db(db_path, monkeypatch)
    try:
        health = client.get("/api/v1/projects/dream-studio/health").json()
        assert health["project"]["security_package_status"]["open_findings"] == 2

        security = client.get("/api/v1/projects/dream-studio/security").json()
        assert security["count"] == 2
        alias = [finding for finding in security["findings"] if finding["id"] == "finding-alias"][0]
        assert alias["project_id"] == "dream-studio"
        assert alias["source_project_id"] == "project_dream_studio"
        assert "project_dream_studio" in security["alias_policy"]["aliases"]
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


def test_project_details_separates_health_and_sqlite_readiness_authority(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = _portfolio_db(tmp_path)
    with _connect(db_path) as conn:
        build_secure_production_readiness_gate(
            conn=conn,
            project_id="dream-studio",
            lifecycle_event="release_merge",
            persist=True,
        )
    client = _client_for_db(db_path, monkeypatch)
    try:
        response = client.get("/api/v1/projects/dream-studio/details")

        assert response.status_code == 200
        payload = response.json()
        assert payload["health_score"]["overall_score"] is not None
        assert payload["readiness_score"]["status"] == "partial"
        assert payload["readiness_control_coverage"]["total"] > 47
        assert payload["enterprise_security_controls"]["source_control_count"] == 47
        assert payload["enterprise_security_control_status"]["controls"]
        assert payload["stack_evidence"]["repo_scan"]["classification"] == "confirmed"
        assert payload["stack_evidence"]["repo_scan"]["secret_contents_read"] is False
        assert payload["confirmed_dependencies"]["edge_count"] == 1
        assert payload["confirmed_dependencies"]["edges"][0]["confirmation_status"] == "confirmed"
        assert payload["confirmed_dependencies"]["edges"][0]["rendered_by_default"] is True
        assert payload["inferred_or_unverified_dependencies"]["edge_count"] >= 2
        assert payload["inferred_or_unverified_dependencies"]["rendered_by_default"] is False
        assert payload["dependency_drilldown"]["confirmed_edges_only_by_default"] is True
        assert "analytics_only" in [
            profile["profile_id"]
            for profile in payload["module_runtime_profile_fit"]["candidate_profiles"]
        ]
        assert "external_project" in payload["module_runtime_profile_fit"]["fit_modules"]
        assert payload["validation_state"]["recent"]["recent_count"] == 2
        assert payload["attention_items"]["open_count"] == 1
        assert payload["manual_review_controls"]
        assert payload["remediation_work_orders"]
        assert payload["source_status"]["classification"] == "fresh"
    finally:
        DatabaseRuntime.reset_instance()


def test_project_dependencies_render_confirmed_edges_only_by_default(
    tmp_path: Path, monkeypatch
) -> None:
    client = _client_for_db(_portfolio_db(tmp_path), monkeypatch)
    try:
        response = client.get("/api/v1/projects/dream-studio/dependencies")

        assert response.status_code == 200
        payload = response.json()
        assert payload["edge_count"] == 1
        assert payload["confirmed_edge_count"] == 1
        assert payload["inferred_edge_count"] == 0
        assert payload["unverified_edge_count"] == 0
        assert payload["knowledge_graph_status"]["classification"] == "confirmed"
        assert payload["knowledge_graph_status"]["placeholder_edges_rendered"] is False
        assert payload["knowledge_graph_status"]["confirmed_edges_rendered_by_default"] is True
        assert payload["knowledge_graph_status"]["inferred_edges_rendered_by_default"] is False
        edge = payload["edges"][0]
        assert edge["confirmation_status"] == "confirmed"
        assert edge["source_tables"] == ["pi_dependencies"]
        assert edge["source_refs"]
        assert payload["nodes"][0]["source_tables"] == ["pi_components", "pi_dependencies"]
        assert payload["drilldown"]["confirmed_edges_only_by_default"] is True
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
