from __future__ import annotations

from pathlib import Path

from core.event_store.studio_db import _connect
from core.production_readiness import (
    build_secure_production_readiness_gate,
    production_readiness_control_catalog,
    production_readiness_dashboard_summary,
)
from core.production_readiness.controls import classify_production_readiness_impact


def test_production_readiness_catalog_maps_existing_skills_without_duplicates() -> None:
    catalog = production_readiness_control_catalog()

    assert catalog["canonical_security_framework"] == "47_enterprise_security_controls"
    assert catalog["control_count"] > 47
    assert catalog["no_duplicate_skill_policy"] is True
    decisions = {item["decision"] for item in catalog["overlap_matrix"]}
    assert {
        "keep_existing",
        "map_existing_skill_to_control",
        "strengthen_existing_skill",
        "create_new_skill",
    } <= decisions
    assert all(item["rollback_supersession_plan"] for item in catalog["overlap_matrix"])


def test_targeted_readiness_checks_classify_representative_changes() -> None:
    api = classify_production_readiness_impact(
        ["projections/api/routes/project_intelligence.py"],
        lifecycle_event="code_change",
    )
    database = classify_production_readiness_impact(
        ["core/event_store/migrations/040_production_readiness_authority.sql"],
        lifecycle_event="code_change",
    )
    dashboard = classify_production_readiness_impact(
        ["projections/frontend/dashboard.html"],
        lifecycle_event="code_change",
    )

    assert "api_surface" in api["impact_categories"]
    assert "database_change" in database["impact_categories"]
    assert "dashboard_runtime" in dashboard["impact_categories"]


def test_full_release_review_includes_security_and_readiness_controls() -> None:
    gate = build_secure_production_readiness_gate(lifecycle_event="release_merge")

    assert gate["full_review_required"] is True
    assert gate["security_lifecycle_gate"]["source_framework"]["source_control_count"] == 47
    assert gate["control_summary"]["total"] > 47
    assert gate["control_summary"]["manual_review"] > 0
    assert gate["project_readiness_score"]["status"] == "partial"
    assert gate["release_readiness"]["status"] == "hold"
    assert gate["db_write_authorized"] is False


def test_not_applicable_controls_record_reasons_for_tiny_doc_change() -> None:
    gate = build_secure_production_readiness_gate(
        lifecycle_event="code_change",
        changed_files=["docs/notes/context.md"],
    )

    not_applicable = [
        item for item in gate["control_results"] if item["status"] == "not_applicable"
    ]
    assert not_applicable
    assert all(item["reason_not_applicable"] for item in not_applicable)


def test_readiness_records_persist_to_sqlite_authority(tmp_path: Path) -> None:
    db_path = tmp_path / "studio.db"
    with _connect(db_path) as conn:
        gate = build_secure_production_readiness_gate(
            conn=conn,
            project_id="dream-studio",
            lifecycle_event="release_merge",
            persist=True,
        )
        summary = production_readiness_dashboard_summary(conn, project_id="dream-studio")

    assert gate["persisted"] is True
    assert summary["assessment_id"] == gate["assessment_id"]
    assert summary["control_summary"]["total"] == gate["control_summary"]["total"]
    assert summary["readiness_score"]["status"] == "partial"
    assert summary["remediation_work_orders"]
    assert set(summary["source_tables"]) >= {
        "production_readiness_assessment_runs",
        "production_readiness_control_results",
        "project_readiness_scorecards",
    }
