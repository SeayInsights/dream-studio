from __future__ import annotations

from core.recovery.rollback_policy import (
    build_failure_recovery_plan,
    validate_failure_recovery_plan,
)


def test_failed_validation_recovery_can_continue_when_evidence_exists() -> None:
    plan = build_failure_recovery_plan(
        failure_type="failed_validation",
        evidence_refs=["meta/evidence/failure.yaml"],
        validation_refs=["meta/evidence/validation.yaml"],
    )

    assert plan["rollback_executed"] is False
    assert plan["cleanup_executed"] is False
    assert plan["route_decision"]["route_decision"] == "continue_internal"
    assert "preserve_failed_run_logs" in plan["preservation_requirements"]
    assert validate_failure_recovery_plan(plan) == []


def test_corrupted_state_recovery_hard_stops_without_backup_ref() -> None:
    plan = build_failure_recovery_plan(
        failure_type="corrupted_state",
        evidence_refs=["meta/evidence/corruption.yaml"],
    )

    assert plan["route_decision"]["route_decision"] == "hard_stop"
    assert plan["route_decision"]["operator_action_required"] is True
    assert any(step["step"] == "verify_backup_before_restore" for step in plan["steps"])


def test_recovery_plan_validator_rejects_executed_or_mutating_plan() -> None:
    issues = validate_failure_recovery_plan(
        {
            "rollback_executed": True,
            "cleanup_executed": True,
            "live_state_mutation_required": True,
            "evidence_refs": [],
            "steps": [],
        }
    )

    assert "rollback_must_not_execute_in_plan" in issues
    assert "cleanup_must_not_execute_in_plan" in issues
    assert "plan_must_not_require_live_state_mutation" in issues
    assert "evidence_refs_required" in issues
    assert "recovery_steps_required" in issues
