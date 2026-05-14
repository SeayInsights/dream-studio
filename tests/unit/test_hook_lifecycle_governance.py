from __future__ import annotations

from core.telemetry.hook_governance import (
    classify_hook_status,
    hook_lifecycle_policy,
    validate_hook_invocation_metadata,
    validate_hook_lifecycle_policy,
)


def test_hook_lifecycle_policy_is_non_executing() -> None:
    policy = hook_lifecycle_policy()

    assert validate_hook_lifecycle_policy(policy) == []
    assert policy["changes_hook_execution"] is False
    assert policy["writes_db"] is False
    assert policy["schema_migration_required"] is False
    assert policy["dashboard_authority"] is False
    assert policy["failure_handling"]["best_effort_emitters_do_not_raise"] is True
    assert policy["telemetry_requirements"]["hook_invocations"] is True


def test_hook_status_normalization_covers_failure_and_suppression() -> None:
    assert classify_hook_status("ok") == "completed"
    assert classify_hook_status("warning") == "completed_with_failures"
    assert classify_hook_status("skipped") == "suppressed"
    assert classify_hook_status("unknown") == "declared"
    assert classify_hook_status("completed", error_message="boom") == "failed"


def test_hook_invocation_metadata_requires_attribution() -> None:
    metadata = {
        "hook_id": "on-tool-activity",
        "hook_name": "on-tool-activity",
        "hook_event_name": "PostToolUse",
        "source_refs": ["runtime/hooks/meta/on-tool-activity.py"],
        "status": "completed",
        "dashboard_authority": False,
        "writes_live_db_in_test": False,
    }

    assert validate_hook_invocation_metadata(metadata) == []


def test_hook_invocation_metadata_rejects_dashboard_authority_and_live_test_writes() -> None:
    metadata = {
        "hook_id": "on-tool-activity",
        "hook_name": "on-tool-activity",
        "hook_event_name": "PostToolUse",
        "source_refs": ["runtime/hooks/meta/on-tool-activity.py"],
        "status": "completed",
        "dashboard_authority": True,
        "writes_live_db_in_test": True,
    }

    errors = validate_hook_invocation_metadata(metadata)

    assert "hook dashboard output must not be authority" in errors
    assert "hook tests must not write live DB" in errors


def test_hook_invocation_metadata_rejects_missing_attribution() -> None:
    errors = validate_hook_invocation_metadata({"status": "completed"})

    assert "missing hook attribution: hook_id" in errors
    assert "missing hook attribution: source_refs" in errors
