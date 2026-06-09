from __future__ import annotations

from core.telemetry.multi_operator_authority import (
    build_multi_operator_authority_model,
    validate_multi_operator_authority_model,
)


def test_multi_operator_model_preserves_local_authority_and_strips_raw_state() -> None:
    model = build_multi_operator_authority_model(
        [
            {
                "authority_mode": "local_instance",
                "summary_hash": "sha256:abc",
                "summary": {
                    "operator_id": "op-a",
                    "team_id": "team-a",
                    "project_count": 2,
                    "raw_prompt": "private",
                },
                "raw": {"file_contents": "private"},
            }
        ]
    )

    contribution = model["contributions"][0]
    assert model["operator_local_authority_preserved"] is True
    assert model["raw_state_exposed"] is False
    assert "raw_prompt" not in contribution["summary"]
    assert "file_contents" not in contribution["raw"]
    assert contribution["raw_fields_rejected"] == ["file_contents", "raw_prompt"]
    assert validate_multi_operator_authority_model(model) == []


def test_multi_operator_model_rolls_up_sanitized_summaries() -> None:
    model = build_multi_operator_authority_model(
        [
            {
                "summary_hash": "sha256:a",
                "summary": {"operator_id": "op-a", "team_id": "t", "project_count": 1},
            },
            {
                "summary_hash": "sha256:b",
                "summary": {"operator_id": "op-b", "team_id": "t", "project_count": 4},
            },
        ]
    )

    rollup = model["rollup_design"]["team_rollups"][0]
    assert rollup["team_id"] == "t"
    assert rollup["operator_count"] == 2
    assert rollup["project_count"] == 5


def test_multi_operator_validator_rejects_missing_hash_and_raw_state() -> None:
    issues = validate_multi_operator_authority_model(
        {
            "operator_local_authority_preserved": False,
            "raw_state_exposed": True,
            "contributions": [{"summary_hash": "", "raw": {"secret": "nope"}}],
        }
    )

    assert "operator_local_authority_must_be_preserved" in issues
    assert "raw_state_must_not_be_exposed" in issues
    assert "contribution_0_contains_forbidden_raw_fields:secret" in issues
    assert "contribution_0_missing_summary_hash" in issues
