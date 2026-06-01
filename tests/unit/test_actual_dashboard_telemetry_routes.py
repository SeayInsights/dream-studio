from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from projections.api.main import app
from tests.unit.test_telemetry_read_models import _db, _seed


def _client_with_db(tmp_path: Path, monkeypatch) -> tuple[TestClient, Path]:
    db_path = _db(tmp_path)
    _seed(db_path)
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    return TestClient(app), db_path


def test_actual_app_mounts_telemetry_summary_route_with_authority_metadata(
    tmp_path: Path, monkeypatch
) -> None:
    client, _db_path = _client_with_db(tmp_path, monkeypatch)

    response = client.get("/api/telemetry/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_name"] == "global_telemetry_summary"
    assert payload["derived_view"] is True
    assert payload["primary_authority"] is False
    assert payload["routing_authority"] is False
    assert payload["dashboard_consumable"] is True
    assert "execution_events" in payload["source_tables"]
    assert payload["entity_counts"]["projects"] == 1
    assert payload["component_usage"]["skill"][0]["component_id"] == "ds-core"
    assert payload["token_usage"][0]["total_tokens"] == 225
    assert payload["findings"][0]["severity"] == "high"
    assert payload["validation_outcomes"][0]["status"] == "passed"
    assert payload["research_decisions"]["decisions"][0]["selected_option"] == "derived_view"
    assert payload["route_explainability"][0]["explainability"]["has_evidence_refs"] is True
    assert (
        payload["drilldown_entry_points"]["projects"][0]["api_path"]
        == "/api/telemetry/projects/dream-studio"
    )
    assert payload["module_availability"]


def test_actual_app_exposes_project_milestone_task_and_process_run_routes(
    tmp_path: Path, monkeypatch
) -> None:
    client, _db_path = _client_with_db(tmp_path, monkeypatch)

    project = client.get("/api/telemetry/projects/dream-studio")
    milestone = client.get(
        "/api/telemetry/milestones/dashboard_read_models_for_telemetry_spine",
        params={"project_id": "dream-studio"},
    )
    task = client.get(
        "/api/telemetry/tasks/read-model-test",
        params={
            "project_id": "dream-studio",
            "milestone_id": "dashboard_read_models_for_telemetry_spine",
        },
    )
    process_run = client.get("/api/telemetry/process-runs/process-run-read-model-test")

    assert project.status_code == 200
    assert milestone.status_code == 200
    assert task.status_code == 200
    assert process_run.status_code == 200
    assert project.json()["events"][0]["event_id"] == "event-read-model-test"
    assert milestone.json()["component_usage"]["tool"][0]["component_id"] == "pytest"
    assert task.json()["tokens"][0]["model_id"] == "gpt"
    assert process_run.json()["events"][0]["event_id"] == "event-read-model-test"


def test_actual_app_exposes_component_attention_and_module_empty_state_routes(
    tmp_path: Path, monkeypatch
) -> None:
    client, _db_path = _client_with_db(tmp_path, monkeypatch)

    component = client.get("/api/telemetry/components/skill/ds-core")
    attention = client.get("/api/telemetry/attention", params={"status": "open"})
    modules = client.get("/api/telemetry/modules")
    security_modules = client.get("/api/telemetry/modules", params={"segment": "security_only"})
    empty_project = client.get("/api/telemetry/projects/missing-project")

    assert component.status_code == 200
    assert attention.status_code == 200
    assert modules.status_code == 200
    assert security_modules.status_code == 200
    assert empty_project.status_code == 200
    assert component.json()["usage"]["skill"]["rows"][0]["component_id"] == "ds-core"
    assert component.json()["hardening_intelligence"]["skill"][0]["validation_count"] == 1
    assert attention.json()["open_items"][0]["attention_id"] == "attention-read-model-test"
    assert attention.json()["grouped_items"][0]["attention_type"] == "security_finding"
    assert modules.json()["modules"]
    assert security_modules.json()["active_segment"] == "security_only"
    assert security_modules.json()["modules"][0]["module_id"] == "security_analytics"
    assert modules.json()["derived_view"] is True
    assert empty_project.json()["events"] == []
    assert empty_project.json()["empty_state_behavior"]


def test_actual_app_exposes_dashboard_data_freshness_status(tmp_path: Path, monkeypatch) -> None:
    client, _db_path = _client_with_db(tmp_path, monkeypatch)

    response = client.get("/api/telemetry/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["model_name"] == "dashboard_data_freshness_status"
    assert payload["derived_view"] is True
    assert payload["primary_authority"] is False
    assert payload["routing_authority"] is False
    assert payload["db_status"]["schema_version"] >= 37
    assert payload["backfill_status"]["dry_run"] is True
    assert payload["backfill_status"]["execution_authorized"] is False
    assert {section["section_id"] for section in payload["section_statuses"]}
    assert "module_availability" in payload


def test_actual_app_uses_injected_db_path_without_live_db_writes(
    tmp_path: Path, monkeypatch
) -> None:
    client, db_path = _client_with_db(tmp_path, monkeypatch)
    before = Path(db_path).stat()

    response = client.get("/api/telemetry/summary")

    after = Path(db_path).stat()
    assert response.status_code == 200
    assert before.st_size == after.st_size
    assert Path(db_path).is_file()


def test_actual_app_rejects_unsupported_component_type(tmp_path: Path, monkeypatch) -> None:
    client, _db_path = _client_with_db(tmp_path, monkeypatch)

    response = client.get("/api/telemetry/components/model/gpt")

    assert response.status_code == 404
