from __future__ import annotations

from pathlib import Path

from core.release.github_pr_cicd_gate import (
    MERGE_POLICY_AUTO,
    build_dream_studio_cicd_profile,
    build_failure_work_orders,
    build_release_branch_name,
    build_release_gate_packet,
    discover_workflow_files,
    evaluate_merge_decision,
    load_cicd_profile,
    validate_cicd_profile,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "runtime" / "config" / "release-gates" / "dream-studio.json"


def _success_checks(profile):
    return [
        {"name": name, "status": "COMPLETED", "conclusion": "SUCCESS"}
        for name in profile.required_checks
    ]


def test_dream_studio_profile_records_release_gate_contract() -> None:
    profile = load_cicd_profile(PROFILE_PATH)
    discovered = discover_workflow_files(REPO_ROOT)

    assert profile.project_id == "dream-studio"
    assert profile.default_branch == "main"
    assert profile.github_remote == "https://github.com/SeayInsights/dream-studio.git"
    assert profile.merge_policy == MERGE_POLICY_AUTO
    assert profile.deployment_policy == "separate_approval_required"
    assert ".github/workflows/ci.yml" in profile.workflow_files
    assert ".github/workflows/full-ci.yml" in profile.workflow_files
    assert ".github/workflows/release-validation.yml" in profile.workflow_files
    assert profile.required_checks == ("pr-smoke",)
    assert "full-ci" in profile.optional_checks
    assert profile.manual_workflows == (".github/workflows/full-ci.yml",)
    assert profile.release_workflows == (".github/workflows/release-validation.yml",)
    assert profile.github_actions_role == "lightweight_remote_confidence_layer"
    assert profile.heavy_validation_layer == "local_dream_studio_release_gate"
    assert "avoid_full_matrix_on_push" in profile.github_actions_minutes_policy
    assert "local_release_gate" in profile.github_actions_unavailable_policy
    assert any("ci_gate.py" in command for command in profile.local_preflight_commands)
    assert validate_cicd_profile(profile, discovered_workflows=discovered) == []


def test_release_branch_builder_refuses_default_branch() -> None:
    profile = build_dream_studio_cicd_profile(str(REPO_ROOT))

    assert (
        build_release_branch_name(profile, "phase3-plus-phase1-phase2")
        == "integration/phase3-plus-phase1-phase2"
    )

    main_profile = profile.__class__(
        **{
            **profile.as_dict(),
            "release_branch_naming": "{milestone_or_release}",
        }
    )
    try:
        build_release_branch_name(main_profile, "main")
    except ValueError as exc:
        assert "default branch" in str(exc)
    else:  # pragma: no cover - defensive
        raise AssertionError("default branch release path was not rejected")


def test_merge_decision_allows_merge_only_after_required_checks_pass() -> None:
    profile = build_dream_studio_cicd_profile(str(REPO_ROOT))

    decision = evaluate_merge_decision(
        profile=profile,
        current_branch="integration/phase3-plus-phase1-phase2",
        target_branch="main",
        checks=_success_checks(profile),
    )

    assert decision["can_merge"] is True
    assert decision["reason"] == "required_checks_passed_and_no_release_blockers"
    assert decision["deployment_allowed"] is False


def test_merge_decision_blocks_direct_to_main_and_failed_required_checks() -> None:
    profile = build_dream_studio_cicd_profile(str(REPO_ROOT))

    direct = evaluate_merge_decision(
        profile=profile,
        current_branch="main",
        target_branch="main",
        checks=_success_checks(profile),
    )
    assert direct["can_merge"] is False
    assert direct["reason"] == "direct_to_main_release_path_forbidden"

    failed_checks = _success_checks(profile)
    failed_checks[0] = {
        "name": profile.required_checks[0],
        "status": "COMPLETED",
        "conclusion": "FAILURE",
    }
    failed = evaluate_merge_decision(
        profile=profile,
        current_branch="integration/phase3-plus-phase1-phase2",
        target_branch="main",
        checks=failed_checks,
    )
    assert failed["can_merge"] is False
    assert failed["reason"] == "required_checks_failed"
    assert failed["failed_required_checks"] == ["pr-smoke"]


def test_ci_billing_blocker_requires_operator_action_not_repo_repair() -> None:
    profile = build_dream_studio_cicd_profile(str(REPO_ROOT))
    checks = _success_checks(profile)
    checks[0] = {
        "name": "pr-smoke",
        "status": "COMPLETED",
        "conclusion": "FAILURE",
        "annotation": "The job was not started because recent account payments have failed or your spending limit needs to be increased.",
    }

    decision = evaluate_merge_decision(
        profile=profile,
        current_branch="integration/phase3-plus-phase1-phase2",
        target_branch="main",
        checks=checks,
    )

    assert decision["can_merge"] is False
    assert decision["reason"] == "ci_infrastructure_or_billing_blocked"
    assert decision["requires_operator_action"] is True


def test_github_actions_unavailable_does_not_block_local_development() -> None:
    profile = build_dream_studio_cicd_profile(str(REPO_ROOT))

    decision = evaluate_merge_decision(
        profile=profile,
        current_branch="integration/lightweight-ci",
        target_branch="main",
        checks=[],
    )

    assert decision["can_merge"] is False
    assert decision["reason"] == "github_actions_unavailable_or_disabled"
    assert decision["development_blocked"] is False
    assert decision["local_release_gate_remains_primary"] is True


def test_failure_work_orders_are_generated_from_failed_checks() -> None:
    profile = build_dream_studio_cicd_profile(str(REPO_ROOT))
    work_orders = build_failure_work_orders(
        profile=profile,
        checks=[
            {
                "name": "test (ubuntu-latest / py3.10)",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
            },
            {
                "name": "pr-smoke",
                "status": "COMPLETED",
                "conclusion": "FAILURE",
                "annotation": "The job was not started because recent account payments have failed.",
            },
            {"name": "dependency audit", "status": "COMPLETED", "conclusion": "SUCCESS"},
        ],
    )

    assert [item["source_check"] for item in work_orders] == [
        "test (ubuntu-latest / py3.10)",
        "pr-smoke",
    ]
    assert work_orders[0]["recommended_route"] == "continue_internal_bounded_repair"
    assert work_orders[1]["recommended_route"] == "require_operator_action"
    assert all("direct_push_to_main" in item["forbidden_actions"] for item in work_orders)


def test_release_gate_packet_is_dashboard_consumable_and_non_authoritative() -> None:
    profile = build_dream_studio_cicd_profile(str(REPO_ROOT))

    packet = build_release_gate_packet(
        profile=profile,
        current_branch="integration/phase3-plus-phase1-phase2",
        target_branch="main",
        pr_url="https://github.com/SeayInsights/dream-studio/pull/132",
        checks=_success_checks(profile),
    )

    assert packet["derived_view"] is True
    assert packet["primary_authority"] is False
    assert packet["routing_authority"] is False
    assert packet["release_branch_required"] is True
    assert packet["direct_to_main_allowed"] is False
    assert packet["github_actions_role"] == "lightweight_remote_confidence_layer"
    assert packet["heavy_validation_layer"] == "local_dream_studio_release_gate"
    assert packet["merge_decision"]["can_merge"] is True


def test_github_workflows_are_lightweight_manual_or_release_scoped() -> None:
    pr_smoke = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    full_ci = (REPO_ROOT / ".github" / "workflows" / "full-ci.yml").read_text(encoding="utf-8")
    release = (REPO_ROOT / ".github" / "workflows" / "release-validation.yml").read_text(
        encoding="utf-8"
    )

    assert "pull_request:" in pr_smoke
    assert "python interfaces/cli/ci_gate.py" not in pr_smoke
    assert "workflow_dispatch:" in full_ci
    assert "pull_request:" not in full_ci
    assert "python interfaces/cli/ci_gate.py" in full_ci
    assert "workflow_dispatch:" in release
    assert "tags:" in release
    assert "Release validation is evidence only." in release
