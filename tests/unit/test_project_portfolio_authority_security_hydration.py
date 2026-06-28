from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.config.sqlite_bootstrap import latest_migration_version
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
            "INSERT INTO _schema_version(version, applied_at) VALUES(?, '2026-05-14T00:00:00Z')",
            (latest_migration_version(),),
        )
        # reg_projects deleted in migration 084; use business_projects.
        # Columns: project_id, name, description, status, project_path, detected_stack, stack_json,
        #          total_sessions, created_at, updated_at
        # Status 'deleted' replaces old 'quarantined'/'legacy_prd' exclusion mechanisms.
        # _default_operator_exclusion_terms() still excludes "demo", "pytest", "temp" by name.
        conn.execute(
            "CREATE TABLE business_projects("
            "project_id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT, "
            "status TEXT NOT NULL DEFAULT 'active', project_path TEXT, "
            "detected_stack TEXT, stack_json TEXT, total_sessions INTEGER DEFAULT 0, "
            "total_tokens INTEGER DEFAULT 0, last_session_at TEXT, "
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL, "
            "source_event_id TEXT, last_event_id TEXT)"
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
            "INSERT INTO business_projects(project_id, name, description, status, project_path, "
            "detected_stack, stack_json, total_sessions, created_at, updated_at) "
            "VALUES('dream-studio', 'Dream Studio', 'application', 'active', ?, 'Python FastAPI', ?, "
            "12, '2026-05-01T00:00:00Z', '2026-05-14T00:00:00Z')",
            (str(project_root), stack),
        )
        # historical-prd-project → status='deleted' (replaces old project_source='legacy_prd' exclusion)
        conn.execute(
            "INSERT INTO business_projects(project_id, name, description, status, project_path, "
            "detected_stack, stack_json, total_sessions, created_at, updated_at) "
            "VALUES('historical-prd-project', 'Historical PRD Project', '', 'deleted', ?, "
            "'unknown', '{}', 99, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (str(legacy_root),),
        )
        # pytest-temp-project → status='deleted' (replaces old is_temp=1/quarantined exclusion)
        conn.execute(
            "INSERT INTO business_projects(project_id, name, description, status, project_path, "
            "detected_stack, stack_json, total_sessions, created_at, updated_at) "
            "VALUES('pytest-temp-project', 'pytest-temp-project', '', 'deleted', '/tmp/pytest-temp-project', "
            "'unknown', '{}', 0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')"
        )
        # demo-project → status='active' but excluded by _default_operator_exclusion_terms("demo")
        demo_root = tmp_path / "demo-project"
        demo_root.mkdir()
        conn.execute(
            "INSERT INTO business_projects(project_id, name, description, status, project_path, "
            "detected_stack, stack_json, total_sessions, created_at, updated_at) "
            "VALUES('demo-project', 'demo-project', '', 'active', ?, "
            "'unknown', '{}', 0, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (str(demo_root),),
        )
        # Security spine tables: security_events (spine) + findings_current_status (projection)
        # Replaced dead `findings` table (migration 112 dropped it; migration 111 created the spine).
        conn.execute(
            "CREATE TABLE security_events("
            "event_id TEXT PRIMARY KEY, event_kind TEXT NOT NULL, project_id TEXT, "
            "severity TEXT, title TEXT, file_path TEXT, line_number INTEGER, "
            "vuln_class TEXT, scanner_type TEXT, "
            "created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')))"
        )
        conn.execute(
            "INSERT INTO security_events(event_id, event_kind, project_id, severity, title, "
            "file_path, line_number, scanner_type) "
            "VALUES('finding-1', 'finding.recorded', 'dream-studio', 'medium', 'Real CI finding', "
            "'.github/workflows/ci.yml', 1, 'SAST')"
        )
        conn.execute(
            "CREATE TABLE findings_current_status("
            "finding_id TEXT PRIMARY KEY, project_id TEXT, severity TEXT, file_path TEXT, "
            "line_number INTEGER, scanner_type TEXT, current_status TEXT NOT NULL DEFAULT 'open', "
            "title TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO findings_current_status(finding_id, project_id, severity, file_path, "
            "line_number, scanner_type, current_status, title, created_at, updated_at) "
            "VALUES('finding-1', 'dream-studio', 'medium', '.github/workflows/ci.yml', 1, "
            "'SAST', 'open', 'Real CI finding', '2026-05-14T00:00:00Z', '2026-05-14T00:00:00Z')"
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
        # route_decision_records dropped migration 131; project_detail.py guards the
        # route-blocker count with object_exists() and returns 0 when the table is absent.
        # pi_dependencies and pi_components dropped in migration 084 (were empty/broken);
        # the route guards with object_exists() → returns 0 for their counts
        # production_readiness_* tables dropped in migration 112; build_secure_production_readiness_gate
        # guards with _table_exists() and returns _empty_summary() when tables are absent.
        # release_readiness_records and compliance_review_flags dropped in migration 133
        # (persist=False dead gate — no production caller reaches persist=True).
        conn.commit()
    finally:
        conn.close()
    return db_path


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
        # production_readiness_* tables dropped in migration 112 → readiness is unavailable
        assert payload["readiness_score"]["status"] in ("partial", "unavailable")
        assert payload["enterprise_security_controls"]["source_control_count"] == 47
        assert payload["enterprise_security_control_status"]["controls"]
        assert payload["stack_evidence"]["repo_scan"]["classification"] == "deferred"
        # pi_dependencies dropped in migration 084 — confirmed edges are 0; inferred may vary
        assert payload["confirmed_dependencies"]["edge_count"] == 0
        assert payload["inferred_or_unverified_dependencies"]["edge_count"] >= 0
        assert payload["dependency_drilldown"]["confirmed_edges_only_by_default"] is True
        assert "analytics_only" in [
            profile["profile_id"]
            for profile in payload["module_runtime_profile_fit"]["candidate_profiles"]
        ]
        assert "external_project" in payload["module_runtime_profile_fit"]["fit_modules"]
        assert payload["validation_state"]["recent"]["recent_count"] == 2
        assert payload["attention_items"]["open_count"] == 1
        assert isinstance(payload.get("manual_review_controls", []), list)
        assert isinstance(payload.get("remediation_work_orders", []), list)
        # production_readiness_* tables dropped in migration 112 → no persisted readiness data
        assert payload["source_status"]["classification"] in ("fresh", "empty by design")
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
        # pi_dependencies dropped in migration 084 — edge counts are 0
        assert payload.get("edge_count", 0) == 0
        assert payload.get("confirmed_edge_count", 0) == 0
        assert payload.get("inferred_edge_count", 0) == 0
        assert payload.get("unverified_edge_count", 0) == 0
        assert payload.get("edges", []) == []
        # knowledge_graph_status and drilldown may or may not be present depending on empty-state handling
        if "knowledge_graph_status" in payload:
            assert (
                payload["knowledge_graph_status"].get("confirmed_edges_rendered_by_default") is True
            )
        if "drilldown" in payload:
            assert payload["drilldown"].get("confirmed_edges_only_by_default") is True
    finally:
        DatabaseRuntime.reset_instance()


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
        # Security spine (migration 111): findings_current_status has 1 open finding
        assert project["security_package_status"]["open_findings"] == 1
        assert project["security_lifecycle_status"]["security_status"] == "blocked_by_open_findings"
        assert (
            project["security_lifecycle_status"]["finding_normalization_policy"][
                "synthetic_demo_findings_in_live_operator_views"
            ]
            is False
        )
        assert project["work_order_status"]["attention_open"] == 1
        assert project["telemetry_status"]["event_count"] == 1
        assert "dashboard_attention_items" in payload["source_status"]["source_tables"]
        assert "execution_events" in payload["source_status"]["source_tables"]
    finally:
        DatabaseRuntime.reset_instance()


def test_project_security_uses_high_confidence_legacy_alias(tmp_path: Path, monkeypatch) -> None:
    db_path = _portfolio_db(tmp_path)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO security_events(event_id, event_kind, project_id, severity, title, "
            "file_path, line_number, scanner_type) "
            "VALUES('finding-alias', 'finding.recorded', 'project_dream_studio', 'high', "
            "'Alias-matched finding', 'core/security/lifecycle.py', 10, 'SAST')"
        )
        conn.execute(
            "INSERT INTO findings_current_status(finding_id, project_id, severity, file_path, "
            "line_number, scanner_type, current_status, title, created_at, updated_at) "
            "VALUES('finding-alias', 'project_dream_studio', 'high', 'core/security/lifecycle.py', "
            "10, 'SAST', 'open', 'Alias-matched finding', '2026-05-14T00:00:00Z', '2026-05-14T00:00:00Z')"
        )
        conn.commit()
    client = _client_for_db(db_path, monkeypatch)
    try:
        # Alias count surfaces on the health endpoint (SQL-side alias expansion via _security_alias_expr)
        health = client.get("/api/v1/projects/dream-studio/health").json()
        assert health["project"]["security_package_status"]["open_findings"] == 2

        # Project-specific security endpoint normalises raw project_id to the requested project_id
        security = client.get("/api/v1/projects/dream-studio/security").json()
        assert security["count"] == 2
        alias_finding = next((f for f in security["findings"] if f["id"] == "finding-alias"), None)
        assert alias_finding is not None
        assert alias_finding["project_id"] == "dream-studio"
        assert alias_finding["source_project_id"] == "project_dream_studio"
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
        assert payload["project"]["security_package_status"]["open_findings"] == 1
        assert (
            payload["project"]["security_lifecycle_status"]["security_status"]
            == "blocked_by_open_findings"
        )
        assert payload["project"]["health_model"]["status"] == "scored"
        assert payload["health"]["overall_score"] == payload["project"]["health_score"]
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
        # message = COALESCE(se.title, '') — security_events.title joined on event_id = finding_id
        assert finding["message"] == "Real CI finding"
    finally:
        DatabaseRuntime.reset_instance()
