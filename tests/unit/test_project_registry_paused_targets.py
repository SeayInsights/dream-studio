from __future__ import annotations

from core.projects.paused_targets import (
    ROUTE_ACTIVE_INTERNAL,
    ROUTE_KEEP_PAUSED,
    ROUTE_RESUME_AFTER_OPERATOR_APPROVAL,
    build_project_target_registry_policy,
    classify_project_target,
    validate_project_target_policy,
)


def test_paused_external_target_forbids_mutation_until_file_backed_resume_approval() -> None:
    policy = classify_project_target(
        {
            "target_id": "dreamysuite",
            "status": "paused",
            "source_boundary": "external_project",
            "repo_clean": False,
            "validation_profile": "external-ui-smoke",
        }
    )

    assert policy["recommended_route"] == ROUTE_KEEP_PAUSED
    assert policy["resume_allowed"] is False
    assert policy["mutation_allowed"] is False
    assert policy["external_validation_allowed"] is False
    assert "operator_approval_missing" in policy["reasons"]
    assert "target_repo_mutation" in policy["forbidden_actions"]
    assert validate_project_target_policy(policy) == []


def test_paused_target_can_be_marked_resume_ready_without_granting_mutation() -> None:
    policy = classify_project_target(
        {
            "target_id": "torii",
            "status": "paused",
            "source_boundary": "external_project",
            "repo_clean": True,
            "operator_approval_refs": ["meta/work-orders/wo-torii-resume/approvals/approval.json"],
            "source_evidence_refs": ["meta/audit/torii-boundary.md"],
        }
    )

    assert policy["recommended_route"] == ROUTE_RESUME_AFTER_OPERATOR_APPROVAL
    assert policy["resume_allowed"] is True
    assert policy["mutation_allowed"] is False
    assert policy["requires_operator_approval"] is False
    assert validate_project_target_policy(policy) == []


def test_active_local_dream_studio_target_can_continue_internal_when_clean() -> None:
    policy = classify_project_target(
        {
            "target_id": "dream-studio",
            "status": "active",
            "source_boundary": "local_repo",
            "repo_clean": True,
            "validation_profile": {"id": "focused-local-pytest"},
        }
    )

    assert policy["recommended_route"] == ROUTE_ACTIVE_INTERNAL
    assert policy["resume_allowed"] is True
    assert policy["mutation_allowed"] is True
    assert policy["validation_profile"] == "focused-local-pytest"
    assert validate_project_target_policy(policy) == []


def test_registry_policy_summarizes_paused_resume_ready_and_active_targets() -> None:
    registry = build_project_target_registry_policy(
        [
            {
                "target_id": "dream-studio",
                "status": "active",
                "source_boundary": "local_repo",
                "repo_clean": True,
            },
            {
                "target_id": "bill-stack",
                "status": "paused",
                "source_boundary": "external_project",
                "repo_clean": False,
            },
            {
                "target_id": "torii",
                "status": "paused",
                "source_boundary": "external_project",
                "repo_clean": True,
                "operator_approval_refs": ["approval.json"],
                "source_evidence_refs": ["boundary.md"],
            },
        ]
    )

    assert registry["derived_view"] is True
    assert registry["primary_authority"] is False
    assert registry["summary"]["target_count"] == 3
    assert registry["summary"]["paused_count"] == 1
    assert registry["summary"]["resume_ready_count"] == 1


def test_policy_validator_rejects_unsafe_external_or_paused_mutation() -> None:
    issues = validate_project_target_policy(
        {
            "target_id": "external",
            "source_boundary": "external_project",
            "recommended_route": ROUTE_KEEP_PAUSED,
            "resume_allowed": False,
            "mutation_allowed": True,
        }
    )

    assert "paused_target_allows_mutation" in issues
    assert "external_or_evidence_target_allows_mutation" in issues
