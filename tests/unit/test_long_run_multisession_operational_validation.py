from __future__ import annotations

from core.release.local_dogfood_stability import (
    REQUIRED_MULTISESSION_CYCLES,
    build_long_run_multisession_operational_validation,
    validate_long_run_multisession_report,
)


def test_long_run_multisession_validation_passes_when_cycles_and_hash_guard_pass() -> None:
    cycles = [
        {
            "cycle_id": cycle_id,
            "status": "pass",
            "evidence_refs": [f"evidence/{cycle_id}.json"],
        }
        for cycle_id in REQUIRED_MULTISESSION_CYCLES
    ]

    report = build_long_run_multisession_operational_validation(
        cycles,
        sqlite_hash_before="abc123",
        sqlite_hash_after="abc123",
    )

    assert report["status"] == "pass"
    assert report["verdict"] == "LONG_RUN_MULTISESSION_OPERATIONAL_VALIDATION_COMPLETE"
    assert report["docker_not_executed"] is True
    assert report["external_projects_remained_paused"] is True
    assert validate_long_run_multisession_report(report) == []


def test_long_run_multisession_validation_blocks_boundary_regressions() -> None:
    report = build_long_run_multisession_operational_validation(
        [
            {
                "cycle_id": "dashboard_authority_inspection",
                "status": "fail",
                "evidence_refs": [],
                "external_project_mutation": True,
                "docker_executed": True,
                "live_sqlite_mutated_unintentionally": True,
                "synthetic_data_leaked": True,
            }
        ],
        sqlite_hash_before="before",
        sqlite_hash_after="after",
    )

    assert report["status"] == "fail"
    assert "missing_required_cycles" in report["failures"]
    assert "live_sqlite_hash_changed" in report["failures"]
    assert "dashboard_authority_inspection_external_project_mutation" in report["failures"]
    assert "dashboard_authority_inspection_docker_executed_without_approval" in report["failures"]
    assert "dashboard_authority_inspection_unintended_sqlite_mutation" in report["failures"]
    assert "dashboard_authority_inspection_synthetic_data_leaked" in report["failures"]
