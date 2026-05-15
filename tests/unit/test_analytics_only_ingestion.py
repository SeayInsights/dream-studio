from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from core.analytics_ingestion import (
    analytics_only_profile_status,
    ingest_analytics_payload,
)
from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from projections.api.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_analytics_only_ingestion_writes_current_authority_without_orchestration(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "analytics-only" / "studio.db"
    project_path = tmp_path / "project"
    project_path.mkdir()

    with _connect(db_path) as conn:
        register_default_adapter_authority_profiles(conn)
        dry_run = ingest_analytics_payload(
            conn,
            _payload(project_path),
            execute=False,
        )
        result = ingest_analytics_payload(
            conn,
            _payload(project_path),
            execute=True,
        )
        repeat = ingest_analytics_payload(
            conn,
            _payload(project_path),
            execute=True,
        )

        assert dry_run["dry_run"] is True
        assert dry_run["records_written"] == {}
        assert result["db_write_authorized"] is True
        assert result["hooks_required"] is False
        assert result["agents_required"] is False
        assert result["workflows_required"] is False
        assert result["claude_required"] is False
        assert result["codex_required"] is False
        assert result["docker_required"] is False
        assert result["repo_mutation_required"] is False
        assert repeat["records_written"] == result["records_written"]

        assert _count(conn, "reg_projects") == 1
        assert _count(conn, "validation_results") == 1
        assert _count(conn, "security_findings") == 1
        assert _count(conn, "token_usage_records") == 1
        assert _count(conn, "ai_usage_operational_records") == 1
        assert _count(conn, "pi_components") == 2
        assert _count(conn, "pi_dependencies") == 1
        assert _count(conn, "prd_documents") == 1
        assert _count(conn, "production_readiness_assessment_runs") == 1
        assert _count(conn, "project_health_scorecards") == 1
        assert _count(conn, "project_readiness_scorecards") == 1

        token = conn.execute("SELECT * FROM token_usage_records").fetchone()
        usage = conn.execute("SELECT * FROM ai_usage_operational_records").fetchone()
        assert token["total_tokens"] == 30
        assert token["cost_visibility"] == "unavailable"
        assert token["cost_source"] == "unavailable"
        assert token["estimated_cost"] == 0
        assert usage["cost_visibility"] == "unknown"
        assert usage["cost_amount"] is None


def test_analytics_only_dashboard_routes_consume_imported_state(
    tmp_path: Path,
    monkeypatch,
) -> None:
    db_path = tmp_path / "analytics-only" / "studio.db"
    project_path = tmp_path / "project"
    project_path.mkdir()

    with _connect(db_path) as conn:
        register_default_adapter_authority_profiles(conn)
        ingest_analytics_payload(conn, _payload(project_path), execute=True)

    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    client = TestClient(app)

    try:
        projects = client.get("/api/v1/projects?limit=20")
        details = client.get("/api/v1/projects/analytics-project/details")
        analytics = client.get("/api/shared-intelligence/analytics-only")
        tokens = client.get("/api/v1/metrics/tokens")

        assert projects.status_code == 200
        assert details.status_code == 200
        assert analytics.status_code == 200
        assert tokens.status_code == 200

        project_ids = {project["project_id"] for project in projects.json()["projects"]}
        assert "analytics-project" in project_ids
        assert details.json()["readiness_score"]["status"] == "partial"
        assert details.json()["security_status"]["open_findings"] == 1
        assert analytics.json()["hooks_required"] is False
        assert analytics.json()["docker_required"] is False
        assert analytics.json()["write_authorization"] == "explicit_ingestion_execute_only"
        assert tokens.json()["total_tokens"] == 30
    finally:
        DatabaseRuntime.reset_instance()


def test_ds_analytics_ingest_runs_from_outside_repo_against_rehearsal_home(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    outside = tmp_path / "outside"
    outside.mkdir()
    project_path = tmp_path / "project"
    project_path.mkdir()
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(_payload(project_path)), encoding="utf-8")
    ds = REPO_ROOT / "interfaces" / "cli" / "ds.py"

    subprocess.run(
        [
            sys.executable,
            str(ds),
            "--source-root",
            str(REPO_ROOT),
            "--home",
            str(home),
            "install",
            "--rehearsal",
            "--profile",
            "analytics_only",
        ],
        cwd=outside,
        capture_output=True,
        text=True,
        check=True,
    )
    dry_run = subprocess.run(
        [
            sys.executable,
            str(ds),
            "--source-root",
            str(REPO_ROOT),
            "--home",
            str(home),
            "analytics-ingest",
            "--file",
            str(payload_path),
        ],
        cwd=outside,
        capture_output=True,
        text=True,
        check=True,
    )
    execute = subprocess.run(
        [
            sys.executable,
            str(ds),
            "--source-root",
            str(REPO_ROOT),
            "--home",
            str(home),
            "analytics-ingest",
            "--file",
            str(payload_path),
            "--execute",
        ],
        cwd=outside,
        capture_output=True,
        text=True,
        check=True,
    )

    dry_payload = json.loads(dry_run.stdout)
    execute_payload = json.loads(execute.stdout)
    assert dry_payload["dry_run"] is True
    assert dry_payload["records_written"] == {}
    assert execute_payload["execute"] is True
    assert execute_payload["records_written"]["reg_projects"] == 1

    with _connect(home / "state" / "studio.db") as conn:
        status = analytics_only_profile_status(conn)
        assert status["dashboard_api_available"] is True
        assert _count(conn, "reg_projects") == 1


def _payload(project_path: Path) -> dict[str, object]:
    return {
        "source_refs": ["test:analytics-only"],
        "evidence_refs": ["test:evidence"],
        "projects": [
            {
                "project_id": "analytics-project",
                "project_name": "Analytics Project",
                "project_path": str(project_path),
                "project_type": "external_project",
                "stack_detected": "python",
                "stack_json": {"languages": ["python"], "frameworks": ["fastapi"]},
                "health_score": 88,
                "security_score": 70,
            }
        ],
        "validations": [
            {
                "validation_id": "validation-ci-1",
                "project_id": "analytics-project",
                "validation_type": "ci",
                "status": "passed",
                "command": "ci",
                "summary": "CI passed",
            }
        ],
        "security_findings": [
            {
                "finding_id": "finding-1",
                "project_id": "analytics-project",
                "severity": "high",
                "category": "dependency_supply_chain",
                "rule_id": "DEP-1",
                "status": "open",
                "description": "Imported finding",
                "file_path": "requirements.txt",
                "line": 1,
                "remediation_path": "Update dependency.",
            }
        ],
        "token_usage": [
            {
                "token_usage_id": "token-1",
                "project_id": "analytics-project",
                "adapter_id": "codex",
                "provider": "openai",
                "model_id": "gpt",
                "input_tokens": 10,
                "output_tokens": 20,
                "billing_mode": "subscription_plan",
                "token_visibility": "exact",
                "cost_visibility": "unavailable",
                "usage_source": "local_telemetry",
                "cost_source": "unavailable",
            }
        ],
        "ai_usage": [
            {
                "usage_record_id": "usage-1",
                "project_id": "analytics-project",
                "adapter_id": "codex",
                "provider": "openai",
                "model_id": "gpt",
                "billing_mode": "subscription_plan",
                "token_visibility": "exact",
                "cost_visibility": "unknown",
                "usage_source": "local_telemetry",
                "cost_source": "unknown",
                "confidence": "medium",
                "total_tokens": 30,
                "validation_result": "passed",
                "success": True,
                "files_touched": ["app.py"],
                "commands_run": ["pytest"],
            }
        ],
        "components": [
            {
                "component_id": "component-app",
                "project_id": "analytics-project",
                "path": "app.py",
                "name": "app",
                "component_type": "module",
            },
            {
                "component_id": "component-sqlite",
                "project_id": "analytics-project",
                "path": "state/studio.db",
                "name": "sqlite",
                "component_type": "module",
            },
        ],
        "dependencies": [
            {
                "dependency_id": "dep-1",
                "project_id": "analytics-project",
                "from_component": "component-app",
                "to_component": "component-sqlite",
                "dependency_type": "references",
                "strength": 1,
            }
        ],
        "prds": [
            {
                "prd_id": "prd-1",
                "project_id": "analytics-project",
                "title": "Analytics Project PRD",
                "status": "current",
                "total_tasks": 1,
                "completed_tasks": 1,
            }
        ],
        "readiness_assessments": [
            {
                "assessment_id": "assessment-1",
                "project_id": "analytics-project",
                "status": "partial",
                "confidence": "medium",
                "health_score": 82,
                "readiness_score": 61,
                "missing_evidence": ["accessibility review"],
                "blocking_factors": [],
                "release_readiness_effect": "needs_manual_review",
                "controls": [
                    {
                        "result_id": "control-1",
                        "control_id": "accessibility_review",
                        "control_family": "accessibility",
                        "status": "manual_review",
                        "applicability": "applicable",
                        "severity": "medium",
                    }
                ],
            }
        ],
    }


def _count(conn, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
