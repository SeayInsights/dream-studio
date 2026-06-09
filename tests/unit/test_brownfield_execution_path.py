"""Tests for the brownfield execution path — Phase 4 safety-critical seam.

The test that matters: prove the execution path cannot be made to
mutate/push/deploy the target, and cannot scan excluded private artifacts,
even when asked. Safety properties that only hold at planning time but not
at execution time are holes — these tests re-assert them at the execution boundary.
"""

from __future__ import annotations

import pytest

from core.projects.external_validation import (
    PRIVATE_TARGET_ARTIFACT_PATTERNS,
    approve_read_only_execution,
    assert_step_is_permitted,
    build_external_project_validation_pipeline,
    validate_approved_read_only_execution,
    validate_external_project_validation_pipeline,
)

# ── Test fixtures ─────────────────────────────────────────────────────────────


def _sample_target() -> dict:
    return {
        "target_id": "test-brownfield-repo",
        "status": "paused",
        "source_boundary": "external_project",
        "validation_profile": "external_project_read_only_intake",
        "read_access_requires_current_selection": True,
        "mutation_requires_scoped_approval": True,
        "commit_requires_validation_and_commit_policy": True,
        "push_deploy_requires_separate_approval": True,
        "private_artifact_policy": "exclude_from_target_git_tracking",
        "operator_approval_refs": ["approval-ref-001"],
        "current_target_selection_ref": "operator-selected-2026-05-30",
        "dirty_state": "clean",
    }


def _valid_plan() -> dict:
    return build_external_project_validation_pipeline(
        _sample_target(),
        evidence_refs=["evidence-001"],
    )


# ── Planning layer invariants (should still hold) ─────────────────────────────


def test_planning_layer_always_sets_execution_allowed_false():
    """The planning layer must NEVER produce execution_allowed=True."""
    plan = _valid_plan()
    assert plan["execution_allowed"] is False


def test_planning_validator_rejects_execution_allowed_true():
    """The planning validator enforces execution_allowed=False."""
    bad_plan = {**_valid_plan(), "execution_allowed": True}
    issues = validate_external_project_validation_pipeline(bad_plan)
    assert "pipeline_must_not_execute_by_default" in issues


def test_planning_validator_rejects_repo_inspection():
    """The planning validator enforces external_repo_inspected=False."""
    bad_plan = {**_valid_plan(), "external_repo_inspected": True}
    issues = validate_external_project_validation_pipeline(bad_plan)
    assert "external_repo_inspection_not_part_of_plan_generation" in issues


# ── Execution path: approval required ────────────────────────────────────────


def test_approve_requires_operator_approval_ref():
    """approve_read_only_execution raises if approval ref is empty."""
    plan = _valid_plan()
    with pytest.raises(ValueError, match="operator_approval_ref is required"):
        approve_read_only_execution(plan, operator_approval_ref="")


def test_approve_requires_non_whitespace_approval_ref():
    """approve_read_only_execution raises if approval ref is whitespace-only."""
    plan = _valid_plan()
    with pytest.raises(ValueError, match="operator_approval_ref is required"):
        approve_read_only_execution(plan, operator_approval_ref="   ")


def test_approve_rejects_unsafe_source_plan():
    """approve_read_only_execution rejects a plan that has safety violations."""
    bad_plan = {**_valid_plan(), "external_repo_mutated": True}
    with pytest.raises(ValueError, match="safety violations"):
        approve_read_only_execution(bad_plan, operator_approval_ref="ref-001")


# ── Execution context: safety re-assertions ───────────────────────────────────


def test_approved_execution_context_has_execution_allowed_true():
    """The approved execution context sets execution_allowed=True."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    assert ctx["execution_allowed"] is True


def test_approved_execution_context_read_only_scope():
    """Execution context scope is read_only_validation_only."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    assert ctx["execution_scope"] == "read_only_validation_only"


def test_approved_execution_context_push_never_allowed():
    """push_allowed is False in the execution context — not inherited from plan."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    assert ctx["safety_assertions"]["push_allowed"] is False


def test_approved_execution_context_commit_never_allowed():
    """commit_allowed is False in the execution context."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    assert ctx["safety_assertions"]["commit_allowed"] is False


def test_approved_execution_context_mutation_never_allowed():
    """mutation_allowed is False in the execution context."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    assert ctx["safety_assertions"]["mutation_allowed"] is False


def test_approved_execution_context_deploy_never_allowed():
    """deploy_allowed is False in the execution context."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    assert ctx["safety_assertions"]["deploy_allowed"] is False


def test_approved_execution_context_only_allows_read_only_modes():
    """Allowed execution modes are only read_only and dry_run — not mutation, cleanup, etc."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    allowed = set(ctx["safety_assertions"]["allowed_execution_modes"])
    assert allowed == {"read_only", "dry_run"}
    # Explicitly verify none of the dangerous modes are allowed
    for dangerous in ("mutation", "cleanup", "push", "deploy", "commit", "stage"):
        assert (
            dangerous not in allowed
        ), f"dangerous mode '{dangerous}' allowed in execution context"


def test_approved_execution_context_has_private_artifact_exclusions():
    """Private artifact exclusion patterns are present in the execution context."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    exclusions = ctx["safety_assertions"]["private_artifact_exclusions"]
    assert exclusions, "private_artifact_exclusions must be non-empty"
    # Verify critical patterns are present
    assert any(".env" in p for p in exclusions), ".env pattern must be excluded"
    assert any(".db" in p or "sqlite" in p for p in exclusions), "DB files must be excluded"
    assert any(".planning" in p for p in exclusions), ".planning/ must be excluded"


def test_approved_execution_context_passes_validator():
    """The approved execution context passes its own validator with zero issues."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    issues = validate_approved_read_only_execution(ctx)
    assert issues == [], f"Unexpected safety issues: {issues}"


# ── Execution validator rejects tampered contexts ─────────────────────────────


def test_execution_validator_rejects_if_push_tampered_to_true():
    """The execution validator catches if push_allowed is tampered to True."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    # Attempt to tamper — someone sets push_allowed to True after approval
    tampered = {
        **ctx,
        "safety_assertions": {**ctx["safety_assertions"], "push_allowed": True},
    }
    issues = validate_approved_read_only_execution(tampered)
    assert "push_must_not_be_allowed_in_execution_context" in issues


def test_execution_validator_rejects_if_mutation_tampered_to_true():
    """The execution validator catches mutation tampering."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    tampered = {
        **ctx,
        "safety_assertions": {**ctx["safety_assertions"], "mutation_allowed": True},
    }
    issues = validate_approved_read_only_execution(tampered)
    assert "mutation_must_not_be_allowed_in_execution_context" in issues


def test_execution_validator_rejects_if_scope_tampered():
    """The execution validator catches scope tampering."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    tampered = {**ctx, "execution_scope": "full_execution"}
    issues = validate_approved_read_only_execution(tampered)
    assert "execution_scope_must_be_read_only_validation_only" in issues


def test_execution_validator_rejects_if_private_exclusions_removed():
    """The execution validator catches removal of private artifact exclusions."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    tampered = {
        **ctx,
        "safety_assertions": {**ctx["safety_assertions"], "private_artifact_exclusions": []},
    }
    issues = validate_approved_read_only_execution(tampered)
    assert "private_artifact_exclusions_required_in_execution_context" in issues


def test_execution_validator_rejects_if_approval_ref_removed():
    """The execution validator catches removal of the operator approval ref."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    tampered = {**ctx, "operator_approval_ref": ""}
    issues = validate_approved_read_only_execution(tampered)
    assert "operator_approval_ref_required_in_execution_context" in issues


# ── Step permission enforcement ───────────────────────────────────────────────


def test_permitted_step_passes():
    """assert_step_is_permitted passes for run_read_only_validation."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    # Should not raise
    assert_step_is_permitted("run_read_only_validation", ctx)


def test_unpermitted_step_raises():
    """assert_step_is_permitted raises for any step not in the approved list."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    with pytest.raises(ValueError, match="not in the approved execution steps"):
        assert_step_is_permitted("push_to_remote", ctx)


def test_mutation_step_raises():
    """Even named mutation steps are rejected if not in the approved list."""
    plan = _valid_plan()
    ctx = approve_read_only_execution(plan, operator_approval_ref="ref-001")
    for dangerous_step in ("commit_changes", "push_to_remote", "deploy", "cleanup", "mutate"):
        with pytest.raises(ValueError, match="not in the approved execution steps"):
            assert_step_is_permitted(dangerous_step, ctx)


# ── Private artifact exclusion scope ─────────────────────────────────────────


def test_private_artifact_patterns_cover_critical_exclusions():
    """PRIVATE_TARGET_ARTIFACT_PATTERNS covers all critical exclusion types."""
    patterns = PRIVATE_TARGET_ARTIFACT_PATTERNS
    pattern_str = " ".join(patterns)
    assert ".env" in pattern_str, ".env files must be in exclusion patterns"
    assert ".db" in pattern_str or "sqlite" in pattern_str, "DB files must be excluded"
    assert ".planning" in pattern_str, ".planning/ must be excluded"
    assert "dream-studio" in pattern_str.lower(), ".dream-studio/ must be excluded"
