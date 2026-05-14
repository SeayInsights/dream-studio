from __future__ import annotations

from core.upgrade.retention_policy import (
    build_db_retention_policy,
    validate_db_retention_policy,
)


def test_retention_policy_is_design_only_and_forbids_db_cleanup() -> None:
    policy = build_db_retention_policy()

    assert validate_db_retention_policy(policy) == []
    assert policy["design_only"] is True
    assert policy["db_cleanup_execution_allowed"] is False
    assert policy["record_deletion_allowed"] is False
    assert policy["table_drop_allowed"] is False
    assert policy["compaction_execution_allowed"] is False
    assert policy["migration_required"] is False
    assert policy["requires_future_operator_approval"] is True
    assert policy["default_decision"] == "retain_when_uncertain"


def test_retention_policy_classifies_core_table_groups() -> None:
    policy = build_db_retention_policy()
    groups = {group["group"]: group for group in policy["groups"]}

    assert "canonical_authority" in groups
    assert "telemetry_spine" in groups
    assert "security_validation" in groups
    assert "token_cost" in groups
    assert "derived_dashboard_projections" in groups
    assert groups["canonical_authority"]["retention_class"] == "retain_indefinitely"
    assert groups["derived_dashboard_projections"]["retention_class"] == "rebuildable_projection"
    assert "execution_events" in groups["telemetry_spine"]["tables"]
    assert "token_usage_records" in groups["token_cost"]["tables"]


def test_each_retention_group_retains_now_and_requires_review() -> None:
    policy = build_db_retention_policy()

    for group in policy["groups"]:
        assert group["action_now"] == "retain"
        assert group["human_review_required"] is True
        assert group["cleanup_execution_allowed"] is False
        assert group["future_policy_required"] is True
        assert group["rollup_or_restore_proof_required"] is True


def test_validation_rejects_execution_authority() -> None:
    policy = build_db_retention_policy()
    unsafe = {**policy, "record_deletion_allowed": True}

    errors = validate_db_retention_policy(unsafe)

    assert "record_deletion_allowed must be false" in errors
