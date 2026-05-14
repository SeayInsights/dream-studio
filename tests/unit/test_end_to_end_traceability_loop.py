from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.config.sqlite_bootstrap import latest_migration_version
from core.event_store.studio_db import _connect
from core.telemetry.execution_spine import record_process_run
from core.telemetry.emitters import (
    MODE_STRICT,
    TelemetryContext,
    emit_decision_record,
    emit_hook_tool_activity,
    emit_research_evidence_record,
    emit_route_decision,
    emit_security_finding,
    emit_skill_invocations,
    emit_token_usage_record,
    emit_validation_result,
    emit_workflow_invocation,
)
from projections.api.main import app

PROJECT_ID = "dream-studio"
MILESTONE_ID = "validate_end_to_end_traceability_loop"
TASK_ID = "traceability-loop-test"
PROCESS_RUN_ID = "process-traceability-loop-test"


def _temp_db(tmp_path: Path) -> Path:
    db_path = tmp_path / "traceability-loop.db"
    conn = _connect(db_path)
    conn.close()
    return db_path


def _context() -> TelemetryContext:
    return TelemetryContext(
        project_id=PROJECT_ID,
        milestone_id=MILESTONE_ID,
        task_id=TASK_ID,
        process_run_id=PROCESS_RUN_ID,
        source_refs=("tests/unit/test_end_to_end_traceability_loop.py",),
        evidence_refs=("api_route_validation_evidence.yaml",),
        current_stage_gate="structured_authority_projection",
        current_milestone=MILESTONE_ID,
        next_stage_gate="structured_authority_projection",
        next_milestone="integrate_telemetry_into_frontend_dashboard_surface",
    )


def _generate_controlled_traceability_activity(db_path: Path) -> None:
    ctx = _context()
    with _connect(db_path) as conn:
        record_process_run(
            conn,
            project_id=PROJECT_ID,
            milestone_id=MILESTONE_ID,
            task_id=TASK_ID,
            process_run_id=PROCESS_RUN_ID,
            run_type="validation",
            status="completed",
            summary="End-to-end traceability loop validation.",
        )
        conn.commit()
    results = [
        emit_route_decision(
            {
                "route_decision": "continue_internal",
                "handoff_required": False,
                "operator_action_required": False,
                "current_stage_gate": "structured_authority_projection",
                "current_milestone": MILESTONE_ID,
                "next_stage_gate": "structured_authority_projection",
                "next_milestone": "integrate_telemetry_into_frontend_dashboard_surface",
                "recommended_next_work_order": "none",
                "decision_rationale": "backend telemetry traceability loop validation has no stop gate",
            },
            context=ctx,
            db_path=db_path,
            mode=MODE_STRICT,
        ),
        emit_hook_tool_activity(
            hook_name="on-tool-activity",
            tool_name="Read",
            tool_input={"file_path": "projections/api/routes/telemetry.py"},
            context=ctx,
            db_path=db_path,
            mode=MODE_STRICT,
        ),
        emit_skill_invocations(
            [{"name": "ds-core", "mode": "verify"}],
            success=True,
            context=ctx,
            db_path=db_path,
            mode=MODE_STRICT,
        ),
        emit_token_usage_record(
            session_name="traceability-loop-validation",
            model="gpt-test",
            input_tokens=50,
            output_tokens=70,
            total_tokens=120,
            context=ctx,
            db_path=db_path,
            mode=MODE_STRICT,
        ),
        emit_validation_result(
            validation_type="focused_pytest",
            status="passed",
            command="python -m pytest tests/unit/test_end_to_end_traceability_loop.py -q --tb=line",
            scope="unit",
            summary="End-to-end traceability loop validation passed.",
            pass_count=1,
            fail_count=0,
            context=ctx,
            db_path=db_path,
            mode=MODE_STRICT,
        ),
        emit_security_finding(
            severity="high",
            category="test",
            rule_id="TRACEABILITY-SEC-001",
            file_path="projections/api/routes/telemetry.py",
            start_line=1,
            end_line=1,
            description="Synthetic high-severity traceability finding.",
            recommendation="Confirm security rollup reaches telemetry API.",
            scan_id="scan-traceability-loop-test",
            context=ctx,
            db_path=db_path,
            mode=MODE_STRICT,
        ),
        emit_workflow_invocation(
            workflow_id="traceability-loop",
            status="completed",
            run_key=PROCESS_RUN_ID,
            node_id="validate",
            yaml_path="workflows/traceability-loop.yaml",
            nodes={"validate": {"status": "completed"}},
            context=ctx,
            db_path=db_path,
            mode=MODE_STRICT,
        ),
        emit_research_evidence_record(
            question="Can the backend telemetry traceability loop be validated without frontend mutation?",
            decision_class="no_research_needed",
            confidence="high",
            sources=[{"url": "file://repo/tests", "tier": "local"}],
            source_summary="Local repo code and focused tests are sufficient.",
            decision_impact="continue_internal",
            operator_verification_required=False,
            context=ctx,
            db_path=db_path,
            mode=MODE_STRICT,
        ),
        emit_decision_record(
            decision_type="dashboard.traceability_validation",
            decision_status="recorded",
            selected_option="validate_backend_api_first",
            rationale="Frontend integration remains a separate dashboard surface task.",
            options_considered=["backend_api_only", "frontend_ui_now"],
            route_impact="continue_internal",
            approval_required=False,
            source_decision_id="decision-traceability-loop-test",
            context=ctx,
            db_path=db_path,
            mode=MODE_STRICT,
        ),
    ]
    assert all(result.emitted for result in results)


def test_end_to_end_traceability_loop_reaches_actual_telemetry_api(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = _temp_db(tmp_path)
    _generate_controlled_traceability_activity(db_path)
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    client = TestClient(app)

    summary = client.get("/api/telemetry/summary")
    project = client.get(f"/api/telemetry/projects/{PROJECT_ID}")
    milestone = client.get(
        f"/api/telemetry/milestones/{MILESTONE_ID}", params={"project_id": PROJECT_ID}
    )
    task = client.get(
        f"/api/telemetry/tasks/{TASK_ID}",
        params={"project_id": PROJECT_ID, "milestone_id": MILESTONE_ID},
    )
    process_run = client.get(f"/api/telemetry/process-runs/{PROCESS_RUN_ID}")
    component = client.get("/api/telemetry/components/skill/ds-core")
    attention = client.get("/api/telemetry/attention")
    modules = client.get("/api/telemetry/modules")

    assert summary.status_code == 200
    assert project.status_code == 200
    assert milestone.status_code == 200
    assert task.status_code == 200
    assert process_run.status_code == 200
    assert component.status_code == 200
    assert attention.status_code == 200
    assert modules.status_code == 200

    summary_payload = summary.json()
    assert summary_payload["derived_view"] is True
    assert summary_payload["primary_authority"] is False
    assert summary_payload["routing_authority"] is False
    assert summary_payload["entity_counts"]["projects"] == 1
    assert summary_payload["route_status"][0]["handoff_required"] == 0
    assert summary_payload["route_status"][0]["recommended_next_work_order"] == "none"
    assert summary_payload["token_usage"][0]["total_tokens"] == 120
    assert (
        summary_payload["security_findings"][0]["file_path"]
        == "projections/api/routes/telemetry.py"
    )
    assert summary_payload["validation_outcomes"][0]["status"] == "passed"
    assert (
        summary_payload["research_decisions"]["research"][0]["decision_class"]
        == "no_research_needed"
    )
    assert (
        summary_payload["research_decisions"]["decisions"][0]["selected_option"]
        == "validate_backend_api_first"
    )

    process_payload = process_run.json()
    assert process_payload["process_run"]["process_run_id"] == PROCESS_RUN_ID
    assert process_payload["events"]
    assert process_payload["invocations"]["skill"][0]["skill_id"] == "ds-core"
    assert process_payload["tokens"][0]["total_tokens"] == 120
    assert process_payload["security_findings"][0]["rule_id"] == "TRACEABILITY-SEC-001"
    assert process_payload["research"][0]["confidence"] == "high"
    assert process_payload["decisions"][0]["decision_type"] == "dashboard.traceability_validation"

    assert component.json()["usage"]["skill"]["rows"][0]["component_id"] == "ds-core"
    assert attention.json()["open_items"]
    assert modules.json()["derived_view"] is True
    assert modules.json()["primary_authority"] is False


def test_end_to_end_traceability_loop_writes_expected_temp_db_tables(tmp_path: Path) -> None:
    db_path = _temp_db(tmp_path)
    _generate_controlled_traceability_activity(db_path)

    expected_min_counts = {
        "execution_events": 9,
        "route_decision_records": 1,
        "hook_invocations": 1,
        "tool_invocations": 1,
        "skill_invocations": 1,
        "token_usage_records": 1,
        "validation_results": 1,
        "security_findings": 1,
        "workflow_invocations": 1,
        "research_evidence_records": 1,
        "decision_records": 1,
        "dashboard_attention_items": 1,
        "outcome_records": 1,
    }
    with _connect(db_path) as conn:
        schema_version = conn.execute("SELECT MAX(version) FROM _schema_version").fetchone()[0]
        assert schema_version == latest_migration_version()
        assert schema_version >= 37
        for table, minimum in expected_min_counts.items():
            count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count >= minimum, f"{table} expected at least {minimum}, got {count}"


def test_end_to_end_traceability_loop_uses_injected_db_not_live_db(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = _temp_db(tmp_path)
    _generate_controlled_traceability_activity(db_path)
    live_db_path = Path.home() / ".dream-studio" / "state" / "studio.db"
    live_before = live_db_path.stat() if live_db_path.exists() else None
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))
    client = TestClient(app)

    response = client.get("/api/telemetry/summary")

    live_after = live_db_path.stat() if live_db_path.exists() else None
    assert response.status_code == 200
    assert db_path.is_file()
    assert db_path != live_db_path
    if live_before and live_after:
        assert live_before.st_size == live_after.st_size
        assert live_before.st_mtime == live_after.st_mtime
