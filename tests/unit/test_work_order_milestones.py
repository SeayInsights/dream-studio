from __future__ import annotations

from pathlib import Path

from core.work_orders.milestones import (
    NEXT_ACTION_COMPLETE_MILESTONE,
    NEXT_ACTION_CONTINUE_INTERNAL,
    NEXT_ACTION_GENERATE_HANDOFF,
    NEXT_ACTION_HARD_STOP,
    NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL,
    classify_next_action,
    handoff_required_for_decision,
    validate_authority_pack,
    validate_milestone_completion_criteria,
)


def _state(step: dict | None = None, **milestone_overrides) -> dict:
    milestone = {
        "id": "milestone-prd-driven-execution",
        "status": "in_progress",
        "pending_internal_steps": [step or {"id": "review", "type": "checklist_review"}],
        "next_milestone": "handoff_gating",
        "handoff_policy": "stop_gate_or_milestone_completion",
        "auto_continue_low_risk": True,
    }
    milestone.update(milestone_overrides)
    return {
        "prd": {"prd_id": "prd-dream-studio", "product_goals": ["milestone execution"]},
        "stage_gate": {
            "stage_gate_id": "operational_loop_authority",
            "milestone_sequence": [
                "prd_authority_pack",
                "milestone_execution_classifier",
                "handoff_gating",
            ],
            "blocked_milestones": ["bill_stack_resume", "dreamysuite_resume", "torii_resume"],
        },
        "milestone": milestone,
        "strategic_constraints": {
            "paused_external_projects": ["Bill Stack", "DreamySuite", "TORII"],
        },
    }


def test_low_risk_review_checklist_and_evidence_steps_continue_internal() -> None:
    for step_type in ("review", "checklist_review", "package_review", "evidence_creation"):
        decision = classify_next_action(_state({"id": step_type, "type": step_type}))

        assert decision["next_action"] == NEXT_ACTION_CONTINUE_INTERNAL
        assert decision["handoff_required"] is False
        assert "low_risk_internal_step" in decision["reasons"]


def test_backup_and_restore_rehearsal_remain_inside_approved_milestone() -> None:
    for step_type in ("backup", "restore_rehearsal"):
        decision = classify_next_action(
            _state({"id": step_type, "type": step_type, "auto_continue_allowed": True})
        )

        assert decision["next_action"] == NEXT_ACTION_CONTINUE_INTERNAL
        assert handoff_required_for_decision(decision) is False


def test_checklist_package_report_and_evidence_steps_do_not_generate_handoffs() -> None:
    for step_type in ("checklist_review", "package_review", "report_writing", "evidence_creation"):
        decision = classify_next_action(_state({"id": step_type, "type": step_type}))

        assert decision["next_action"] == NEXT_ACTION_CONTINUE_INTERNAL
        assert decision["handoff_required"] is False
        assert handoff_required_for_decision(decision) is False


def test_mutation_without_approval_requires_operator_approval() -> None:
    decision = classify_next_action(
        _state({"id": "edit-source", "type": "source_code_mutation", "requires_approval": True})
    )

    assert decision["next_action"] == NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL
    assert decision["handoff_required"] is True
    assert decision["handoff_reason"] == "operator_approval_required"


def test_failed_validation_generates_reasoned_handoff() -> None:
    decision = classify_next_action(
        _state({"id": "validate", "type": "non_mutating_validation", "validation_result": "failed"})
    )

    assert decision["next_action"] == NEXT_ACTION_GENERATE_HANDOFF
    assert decision["handoff_required"] is True
    assert decision["handoff_reason"] == "failed_validation"


def test_failed_validation_with_rollback_uncertainty_is_hard_stop() -> None:
    decision = classify_next_action(
        _state(
            {"id": "validate", "type": "non_mutating_validation", "validation_result": "failed"},
            rollback_uncertain=True,
        )
    )

    assert decision["next_action"] == NEXT_ACTION_HARD_STOP
    assert decision["handoff_required"] is True
    assert "rollback_uncertainty" in decision["reasons"]


def test_milestone_completion_returns_complete_and_policy_handoff() -> None:
    decision = classify_next_action(
        _state(
            pending_internal_steps=[],
            status="complete",
            handoff_policy="milestone_completion_only",
        )
    )

    assert decision["next_action"] == NEXT_ACTION_COMPLETE_MILESTONE
    assert decision["handoff_required"] is True
    assert decision["handoff_reason"] == "milestone_completion_policy_requires_handoff"


def test_milestone_completion_can_suppress_handoff_when_policy_says_none() -> None:
    decision = classify_next_action(
        _state(
            pending_internal_steps=[],
            status="complete",
            handoff_policy="none",
        )
    )

    assert decision["next_action"] == "start_next_milestone"
    assert decision["handoff_required"] is False


def test_milestone_completion_routes_to_next_milestone_without_handoff() -> None:
    decision = classify_next_action(
        _state(
            pending_internal_steps=[],
            status="complete",
            handoff_policy="stop_gate_or_milestone_completion",
            next_milestone="handoff_gating",
        )
    )

    assert decision["next_action"] == "start_next_milestone"
    assert decision["handoff_required"] is False
    assert decision["next_internal_action"] == "start milestone handoff_gating"


def test_enforced_milestone_completion_requires_file_backed_criteria() -> None:
    decision = classify_next_action(
        _state(
            pending_internal_steps=[],
            status="complete",
            handoff_policy="none",
            enforce_completion_criteria=True,
            completion_criteria={
                "evidence_refs": ["evidence/validation.yaml"],
                "validation": {"status": "passed"},
                "boundary_confirmation": {"confirmed": True},
                "route_state": {"handoff_required": False},
                "known_gaps": [{"id": "empty-state", "classification": "accepted_non_blocker"}],
            },
        )
    )

    assert decision["next_action"] == "start_next_milestone"
    assert decision["handoff_required"] is False


def test_enforced_milestone_completion_blocks_missing_criteria() -> None:
    decision = classify_next_action(
        _state(
            pending_internal_steps=[],
            status="complete",
            handoff_policy="none",
            enforce_completion_criteria=True,
            completion_criteria={"validation": {"status": "passed"}},
        )
    )

    assert decision["next_action"] == NEXT_ACTION_HARD_STOP
    assert decision["handoff_required"] is True
    assert "milestone_completion_criteria_not_met" in decision["reasons"]


def test_milestone_completion_criteria_reports_unclassified_gaps() -> None:
    result = validate_milestone_completion_criteria(
        {
            "completion_criteria": {
                "evidence_refs": ["evidence.yaml"],
                "validation": {"status": "passed"},
                "boundary_confirmation": {"confirmed": True},
                "route_state": {"handoff_required": False},
                "known_gaps": [{"id": "mystery", "classification": "unknown"}],
            }
        }
    )

    assert result["complete"] is False
    assert result["failed"] == ["known_gaps"]
    assert result["unclassified_gaps"] == ["mystery"]


def test_stage_gate_blocks_strategically_invalid_next_phase() -> None:
    decision = classify_next_action(
        _state(pending_internal_steps=[], status="complete", next_milestone="torii_resume")
    )

    assert decision["next_action"] == NEXT_ACTION_HARD_STOP
    assert decision["handoff_required"] is True
    assert "stage_gate_blocks_next_milestone" in decision["reasons"]


def test_external_project_work_is_blocked_while_strategic_pause_active() -> None:
    decision = classify_next_action(
        _state(
            {
                "id": "resume-dreamysuite",
                "type": "target_repo_work",
                "target_project": "DreamySuite",
                "work_kind": "implementation",
            }
        )
    )

    assert decision["next_action"] == NEXT_ACTION_HARD_STOP
    assert decision["handoff_required"] is True
    assert "external_project_pause_active" in decision["reasons"]


def test_executable_design_artifact_cannot_route_to_execution_without_approval() -> None:
    decision = classify_next_action(
        _state(
            {
                "id": "execute-draft-sql",
                "type": "executable_design_artifact_execution",
                "requires_approval": True,
            }
        )
    )

    assert decision["next_action"] == NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL
    assert decision["handoff_required"] is True
    assert decision["handoff_reason"] == "operator_approval_required"


def test_database_runtime_package_and_external_boundaries_stop() -> None:
    expected = {
        "commit": "commit_required",
        "database_mutation": "database_mutation_required",
        "runtime_browser_validation": "runtime_or_browser_validation_required",
        "package_manager": "package_or_dependency_operation_required",
        "external_project_resume": "external_project_resume_required",
    }
    for step_type, handoff_reason in expected.items():
        step = {"id": step_type, "type": step_type, "requires_approval": True}
        if step_type == "external_project_resume":
            step.update({"target_project": "TORII", "work_kind": "external_project_resume"})
        decision = classify_next_action(_state(step))

        assert decision["handoff_required"] is True
        assert decision["handoff_reason"] == handoff_reason
        assert decision["why_internal_continuation_is_not_allowed"]


def test_post_commit_route_verification_starts_structured_authority_milestone() -> None:
    decision = classify_next_action(
        {
            "prd": {"prd_id": "prd-dream-studio", "product_goals": ["route-first execution"]},
            "stage_gate": {
                "stage_gate_id": "structured_authority_projection",
                "milestone_sequence": ["structured_state_authority_projection"],
                "blocked_milestones": ["bill_stack_resume", "dreamysuite_resume", "torii_resume"],
            },
            "milestone": {
                "id": "handoff_routing_repair",
                "status": "complete",
                "pending_internal_steps": [],
                "next_milestone": "structured_state_authority_projection",
                "handoff_policy": "stop_gate_or_milestone_completion",
            },
            "strategic_constraints": {
                "paused_external_projects": ["Bill Stack", "DreamySuite", "TORII"],
            },
        }
    )

    assert decision["route_decision"] == "start_next_milestone"
    assert decision["handoff_required"] is False
    assert decision["next_milestone"] == "structured_state_authority_projection"


def test_authority_pack_validator_requires_prd_fields() -> None:
    missing = validate_authority_pack({"product_identity": "Dream Studio"})

    assert "primary_user" in missing
    assert "paused_validation_targets" in missing


def test_prd_authority_pack_files_exist() -> None:
    root = Path(__file__).resolve().parents[2]

    for relative in (
        "docs/product/dream-studio-prd.md",
        "docs/product/dream-studio-stage-gates.yaml",
        "docs/product/dream-studio-architecture-brief.md",
        "docs/product/dream-studio-artifact-requirements.md",
        "docs/product/dream-studio-definition-of-done.md",
    ):
        path = root / relative
        assert path.is_file(), relative
        text = path.read_text(encoding="utf-8")
        if relative == "docs/product/dream-studio-prd.md":
            assert "Status: current public product authority" in text
        else:
            assert "draft_generated" in text
