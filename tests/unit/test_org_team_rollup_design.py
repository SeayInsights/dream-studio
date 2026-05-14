from __future__ import annotations

from core.telemetry.org_rollups import (
    build_org_team_rollup_design,
    validate_org_team_rollup_design,
)


def test_org_rollup_design_is_local_first_and_sanitized() -> None:
    design = build_org_team_rollup_design(
        [
            {
                "operator_id": "op-a",
                "team_id": "team-a",
                "project_count": 2,
                "validation_pass_count": 4,
                "token_total": 100,
                "raw_prompt": "do not export",
                "local_path": "do not export",
            }
        ]
    )

    summary = design["operator_summaries"][0]
    assert design["local_first"] is True
    assert design["raw_state_exposed"] is False
    assert design["cloud_required"] is False
    assert "raw_prompt" not in summary
    assert "local_path" not in summary
    assert summary["project_count"] == 2
    assert validate_org_team_rollup_design(design) == []


def test_org_rollup_design_aggregates_team_summaries_without_raw_state() -> None:
    design = build_org_team_rollup_design(
        [
            {"operator_id": "op-a", "team_id": "team-a", "project_count": 2, "blocked_count": 1},
            {"operator_id": "op-b", "team_id": "team-a", "project_count": 3, "blocked_count": 0},
        ]
    )

    team = design["team_rollups"][0]
    assert team["team_id"] == "team-a"
    assert team["operator_count"] == 2
    assert team["project_count"] == 5
    assert team["blocked_count"] == 1


def test_org_rollup_validator_rejects_raw_state_exposure() -> None:
    issues = validate_org_team_rollup_design(
        {
            "local_first": False,
            "raw_state_exposed": True,
            "cloud_required": True,
            "operator_summaries": [{"operator_id": "op-a", "raw_prompt": "secret-ish"}],
        }
    )

    assert "rollup_must_preserve_local_first" in issues
    assert "raw_state_must_not_be_exposed" in issues
    assert "cloud_must_not_be_required" in issues
    assert "operator_summary_0_contains_forbidden_fields:raw_prompt" in issues
