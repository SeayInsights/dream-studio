from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from core.config.database import DB_PATH_ENV, DatabaseRuntime
from core.event_store.studio_db import _connect
from core.shared_intelligence.adapter_alignment import register_default_adapter_authority_profiles
from core.shared_intelligence.capability_center import capability_center_summary
from core.shared_intelligence.task_attribution import (
    project_recent_attributed_work,
    record_task_attribution,
    task_attribution_summary,
    validate_task_attribution_summary,
    work_order_task_attribution,
)
from core.shared_intelligence.usage_accounting import (
    adapter_usage_accounting_summary,
    record_ai_usage_operational_record,
)
from projections.api.main import app


def test_task_attribution_persists_completed_work_order_context(tmp_path: Path) -> None:
    with _connect(_db(tmp_path)) as conn:
        _seed_example_attribution(conn)
        summary = task_attribution_summary(conn, project_id="dream-studio")
        work_order = work_order_task_attribution(conn, "wo-dashboard-modernization-001-data-truth")
        project = project_recent_attributed_work(conn, "dream-studio")

    assert validate_task_attribution_summary(summary) == []
    assert summary["record_count"] == 1
    record = summary["records"][0]
    assert record["adapter_id"] == "claude"
    assert record["provider"] == "unknown"
    assert record["model_id"] == "unknown"
    assert record["model_visibility"] == "unknown"
    assert record["skill_ids"] == ["ds-core", "ds-quality"]
    assert record["workflow_ids"] == ["intentional_implementation_workflow"]
    assert record["files_touched"] == ["projections/api/routes/projects.py"]
    assert record["validations"][0]["command"] == "pytest tests/unit/test_dashboard.py"
    assert record["validation_status"] == "passed"
    assert record["outcome_status"] == "committed"
    assert record["commit_refs"] == ["abc123"]
    assert record["rework_needed"] is False
    assert record["security_impact"]["new_findings"] == 0
    assert record["readiness_impact"]["dashboard_authority"] == "improved"
    assert record["cost_amount"] is None
    assert work_order["record_count"] == 1
    assert project["records"][0]["work_order_id"] == "wo-dashboard-modernization-001-data-truth"


def test_task_attribution_marks_untracked_unknowns_without_fake_precision(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        record_task_attribution(
            conn,
            attribution_id="attr-untracked",
            project_id="dream-studio",
            adapter_id="chatgpt",
            source_class="untracked",
            files_touched_status="unavailable",
            files_touched_unavailable_reason="Imported conversation did not include file list.",
            outcome_status="manual_review_required",
            confidence="low",
        )
        summary = task_attribution_summary(conn, project_id="dream-studio")

    record = summary["records"][0]
    assert record["provider"] == "unknown"
    assert record["model_id"] == "unknown"
    assert record["files_touched"] == []
    assert record["files_touched_status"] == "unavailable"
    assert record["outcome_status"] == "manual_review_required"
    assert summary["policy"]["token_cost_precision_not_inferred"] is True
    assert validate_task_attribution_summary(summary) == []


def test_adapter_usage_and_capability_center_consume_task_outcomes(
    tmp_path: Path,
) -> None:
    with _connect(_db(tmp_path)) as conn:
        register_default_adapter_authority_profiles(conn)
        record_ai_usage_operational_record(
            conn,
            usage_record_id="usage-attr-1",
            project_id="dream-studio",
            work_order_id="wo-dashboard-modernization-001-data-truth",
            adapter_id="claude",
            provider="unknown",
            model_id="unknown",
            billing_mode="subscription_plan",
            token_visibility="partial",
            cost_visibility="unavailable",
            validation_result="passed",
            success=True,
            rework_needed=False,
        )
        _seed_example_attribution(conn, ai_usage_record_id="usage-attr-1")
        usage = adapter_usage_accounting_summary(conn, project_id="dream-studio")
        capability = capability_center_summary(
            conn,
            project_id="dream-studio",
            repo_root=Path(__file__).resolve().parents[2],
        )

    assert usage["task_attribution"]["record_count"] == 1
    assert usage["task_attribution"]["outcome_counts"] == {"committed": 1}
    assert usage["by_adapter"]["claude"]["cost_display"] == "unknown"
    skills = {
        item["skill_id"]: item
        for item in capability["sections"]["skills"]["items"]
        if item["skill_id"] in {"ds-core", "ds-quality"}
    }
    assert skills["ds-core"]["success_count"] == 1
    assert skills["ds-quality"]["attributed_outcomes"] == {"committed": 1}


def test_shared_intelligence_task_attribution_routes_are_derived(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = _db(tmp_path)
    with _connect(db_path) as conn:
        _seed_example_attribution(conn)
    DatabaseRuntime.reset_instance()
    monkeypatch.setenv(DB_PATH_ENV, str(db_path))

    client = TestClient(app)
    summary = client.get(
        "/api/shared-intelligence/task-attribution",
        params={"project_id": "dream-studio"},
    )
    work_order = client.get(
        "/api/shared-intelligence/task-attribution/work-orders/"
        "wo-dashboard-modernization-001-data-truth"
    )

    assert summary.status_code == 200, summary.text
    assert work_order.status_code == 200, work_order.text
    assert summary.json()["dashboard_consumable"] is True
    assert summary.json()["execution_authorized"] is False
    assert summary.json()["records"][0]["adapter_id"] == "claude"
    assert work_order.json()["record_count"] == 1


def _seed_example_attribution(
    conn,
    *,
    ai_usage_record_id: str | None = None,
) -> None:
    record_task_attribution(
        conn,
        attribution_id="attr-dashboard-stale-rows",
        project_id="dream-studio",
        milestone_id="dashboard_data_analytics_and_visual_modernization",
        task_id="fix-dashboard-stale-project-rows",
        work_order_id="wo-dashboard-modernization-001-data-truth",
        process_run_id="process-dashboard-stale-rows",
        adapter_id="claude",
        provider="unknown",
        model_id="unknown",
        model_visibility="unknown",
        skill_ids=["ds-core", "ds-quality"],
        workflow_ids=["intentional_implementation_workflow"],
        tool_ids=["shell", "pytest"],
        files_touched=["projections/api/routes/projects.py"],
        commands_run=["pytest tests/unit/test_dashboard.py"],
        validations=[
            {
                "command": "pytest tests/unit/test_dashboard.py",
                "status": "passed",
                "evidence_ref": "tests/unit/test_dashboard.py",
            }
        ],
        validation_status="passed",
        security_impact={"new_findings": 0, "status": "no_new_findings"},
        readiness_impact={"dashboard_authority": "improved"},
        outcome_status="committed",
        outcome_summary="Dashboard stale project rows removed from normal operator view.",
        commit_refs=["abc123"],
        rework_needed=False,
        rework_status="none",
        ai_usage_record_id=ai_usage_record_id,
        source_class="dream_studio_routed",
        confidence="high",
        evidence_refs=["tests/unit/test_dashboard.py"],
    )


def _db(tmp_path: Path) -> Path:
    return tmp_path / "task-attribution" / "studio.db"
