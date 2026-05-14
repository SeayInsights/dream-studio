from __future__ import annotations

from core.projects.external_validation import (
    PIPELINE_MODE_PLANNING_ONLY,
    PIPELINE_MODE_READ_ONLY_VALIDATION,
    build_external_project_validation_pipeline,
    validate_external_project_validation_pipeline,
)


def test_paused_external_target_gets_planning_only_pipeline() -> None:
    plan = build_external_project_validation_pipeline(
        {
            "target_id": "external-a",
            "status": "paused",
            "source_boundary": "external_project",
            "dirty_state": "unknown",
        },
        requested_checks=["unit", "smoke"],
    )

    assert plan["pipeline_mode"] == PIPELINE_MODE_PLANNING_ONLY
    assert plan["execution_allowed"] is False
    assert plan["external_repo_inspected"] is False
    assert plan["external_repo_mutated"] is False
    assert plan["commit_policy"]["commit_allowed"] is False
    assert plan["requires_operator_approval"] is True
    assert validate_external_project_validation_pipeline(plan) == []


def test_resume_ready_external_target_allows_read_only_validation_plan_only() -> None:
    plan = build_external_project_validation_pipeline(
        {
            "target_id": "external-b",
            "status": "paused",
            "source_boundary": "external_project",
            "dirty_state": "clean",
            "repo_clean": True,
            "operator_approval_refs": ["meta/work-orders/wo-external/approvals/approval.json"],
            "source_evidence_refs": ["meta/audit/external-boundary.md"],
        }
    )

    assert plan["pipeline_mode"] == PIPELINE_MODE_READ_ONLY_VALIDATION
    assert plan["target_policy"]["resume_allowed"] is True
    assert plan["validation_profile"]["allowed_modes"] == ["read_only", "dry_run"]
    assert "target_repo_mutation_eval" in plan["evidence_requirements"]
    assert all(step["mutation_allowed"] is False for step in plan["work_order_sequence"])
    assert validate_external_project_validation_pipeline(plan) == []


def test_dirty_state_blocks_commit_even_when_approval_refs_exist() -> None:
    plan = build_external_project_validation_pipeline(
        {
            "target_id": "external-c",
            "status": "paused",
            "source_boundary": "external_project",
            "dirty_state": "dirty",
            "repo_clean": True,
            "operator_approval_refs": ["approval.json"],
            "source_evidence_refs": ["boundary.md"],
        }
    )

    assert plan["dirty_state"] == "dirty"
    assert plan["commit_policy"]["stage_allowed"] is False
    assert plan["commit_policy"]["push_allowed"] is False
    assert plan["commit_policy"]["reason"] == "target_dirty_state_requires_review"


def test_pipeline_validator_rejects_execution_or_repo_mutation_flags() -> None:
    issues = validate_external_project_validation_pipeline(
        {
            "derived_view": True,
            "primary_authority": False,
            "execution_allowed": True,
            "external_repo_inspected": True,
            "external_repo_mutated": True,
            "commit_policy": {"commit_allowed": True},
            "work_order_sequence": [],
            "evidence_requirements": [],
        }
    )

    assert "pipeline_must_not_execute_by_default" in issues
    assert "external_repo_inspection_not_part_of_plan_generation" in issues
    assert "external_repo_mutation_forbidden" in issues
    assert "commit_must_not_be_allowed_in_validation_plan" in issues
    assert "work_order_sequence_required" in issues
    assert "target_repo_mutation_eval_required" in issues
