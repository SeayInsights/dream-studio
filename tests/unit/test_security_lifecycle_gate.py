from __future__ import annotations

from core.security.lifecycle import (
    build_security_lifecycle_gate,
    classify_security_impact,
)


def test_security_lifecycle_gate_loads_canonical_47_control_framework() -> None:
    gate = build_security_lifecycle_gate(lifecycle_event="code_change")

    assert gate["source_framework"]["canonical_framework"] == "47_enterprise_security_controls"
    assert gate["source_framework"]["source_control_count"] == 47
    assert gate["source_framework"]["catalog_scan_count"] == 75
    assert gate["applicability_summary"]["source_control_count"] == 47
    assert gate["execution_authorized"] is False
    assert gate["db_write_authorized"] is False


def test_lightweight_change_records_not_applicable_reasons() -> None:
    gate = build_security_lifecycle_gate(
        lifecycle_event="code_change",
        changed_files=["docs/notes/operator-context.md"],
    )

    assert gate["full_review_required"] is False
    assert gate["security_status"] == "ready"
    assert gate["applicability_summary"]["not_applicable"] == 47
    assert all(row["reason"] for row in gate["applicability"])
    assert {row["status"] for row in gate["applicability"]} == {"not_applicable"}


def test_dependency_change_triggers_full_review_and_manual_deferred_controls() -> None:
    gate = build_security_lifecycle_gate(
        lifecycle_event="code_change",
        changed_files=["pyproject.toml", "requirements-dev.txt"],
    )

    assert gate["full_review_required"] is True
    assert "dependency_supply_chain" in gate["impact_classification"]["impact_categories"]
    assert gate["applicability_summary"]["applicable"] > 0
    assert gate["applicability_summary"]["manual_review_required"] > 0
    assert gate["security_status"] == "needs_manual_review"
    assert gate["release_readiness_effect"] == "hold_manual_review"


def test_release_merge_requires_applicable_47_control_review_without_unknowns() -> None:
    gate = build_security_lifecycle_gate(lifecycle_event="release_merge")

    assert gate["full_review_required"] is True
    assert gate["applicability_summary"]["not_applicable"] == 0
    assert gate["applicability_summary"]["unknown"] == 0
    assert (
        gate["applicability_summary"]["applicable"]
        + gate["applicability_summary"]["manual_review_required"]
        == 47
    )
    assert gate["security_status"] == "needs_manual_review"


def test_security_skill_mapping_and_finding_contract_are_exposed() -> None:
    gate = build_security_lifecycle_gate(lifecycle_event="code_change")

    modes = {item["skill_mode"] for item in gate["security_skill_control_mapping"]}
    assert {"security:review", "security:scan", "security:dast", "security:comply"} <= modes
    assert set(gate["finding_schema_requirements"]) >= {
        "project_id",
        "file_path",
        "line",
        "severity",
        "control_id",
        "status",
        "evidence",
        "remediation_path",
    }
    assert (
        gate["finding_normalization_policy"]["synthetic_demo_findings_in_live_operator_views"]
        is False
    )


def test_security_impact_classification_marks_release_and_runtime_events() -> None:
    release = classify_security_impact([], lifecycle_event="release_merge")
    runtime = classify_security_impact(["hooks/run.py"], lifecycle_event="code_change")

    assert "compliance_governance_operational" in release["impact_categories"]
    assert "runtime_change" in runtime["impact_categories"]
