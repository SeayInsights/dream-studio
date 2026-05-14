from __future__ import annotations

from core.release.goal_to_release import (
    build_goal_to_release_validation_packet,
    validate_goal_to_release_validation_packet,
)


def test_goal_to_release_packet_validates_complete_loop() -> None:
    packet = build_goal_to_release_validation_packet(
        goal="Ship local dogfood safely",
        milestones=[{"id": "m1", "status": "complete", "evidence_ref": "m1.yaml"}],
        work_orders=[{"work_order_id": "wo-1", "status": "complete", "executed": True}],
        telemetry_refs=["telemetry.yaml"],
        dashboard_refs=["dashboard.yaml"],
        validation_refs=["validation.yaml"],
        release_refs=["release.yaml"],
        approval_boundaries=["push_requires_operator_approval"],
    )

    assert packet["validated"] is True
    assert packet["missing_stages"] == []
    assert packet["primary_authority"] is False
    assert packet["push_or_deploy_executed"] is False
    assert validate_goal_to_release_validation_packet(packet) == []


def test_goal_to_release_packet_reports_missing_stages() -> None:
    packet = build_goal_to_release_validation_packet(
        goal="",
        milestones=[],
        work_orders=[],
        telemetry_refs=[],
        dashboard_refs=[],
        validation_refs=[],
        release_refs=[],
        approval_boundaries=[],
    )

    assert packet["validated"] is False
    assert "goal" in packet["missing_stages"]
    assert "execution" in packet["missing_stages"]
    issues = validate_goal_to_release_validation_packet(packet)
    assert any(issue.startswith("missing_loop_stages:") for issue in issues)


def test_goal_to_release_validator_rejects_forbidden_execution_flags() -> None:
    issues = validate_goal_to_release_validation_packet(
        {
            "missing_stages": [],
            "primary_authority": True,
            "forbidden_actions_executed": True,
            "push_or_deploy_executed": True,
        }
    )

    assert "packet_must_not_be_primary_authority" in issues
    assert "forbidden_actions_must_not_execute" in issues
    assert "push_or_deploy_must_not_execute" in issues
