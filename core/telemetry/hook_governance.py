"""Hook lifecycle governance policy."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

HOOK_LIFECYCLE_STATUSES = (
    "declared",
    "dispatched",
    "emitted",
    "completed",
    "completed_with_failures",
    "failed",
    "suppressed",
)

HOOK_REQUIRED_ATTRIBUTION = (
    "hook_id",
    "hook_name",
    "hook_event_name",
    "source_refs",
)


def hook_lifecycle_policy() -> dict[str, Any]:
    """Return non-executing hook lifecycle governance policy."""
    return {
        "artifact_type": "hook_lifecycle_governance_policy",
        "changes_hook_execution": False,
        "writes_db": False,
        "schema_migration_required": False,
        "dashboard_authority": False,
        "statuses": list(HOOK_LIFECYCLE_STATUSES),
        "required_attribution": list(HOOK_REQUIRED_ATTRIBUTION),
        "failure_handling": {
            "best_effort_emitters_do_not_raise": True,
            "failed_hooks_emit_status": True,
            "error_message_is_summary_only": True,
            "operator_attention_required_for_repeated_failures": True,
        },
        "safety_boundaries": {
            "hooks_must_not_mutate_authority_without_approved_runtime_path": True,
            "hooks_must_not_import_provider_sdks_directly": True,
            "hooks_must_not_write_live_db_in_tests": True,
            "risky_action_prevention_is_telemetry_not_release_authority": True,
        },
        "telemetry_requirements": {
            "execution_events": True,
            "hook_invocations": True,
            "tool_invocations_when_tool_related": True,
            "source_refs": True,
            "component_attribution": True,
        },
    }


def classify_hook_status(status: str | None, *, error_message: str | None = None) -> str:
    """Normalize hook lifecycle status for dashboard and telemetry policy checks."""
    text = (status or "").strip().lower()
    if error_message:
        return "failed"
    if text in {"ok", "success", "succeeded", "complete", "completed"}:
        return "completed"
    if text in {"warning", "completed_with_failures"}:
        return "completed_with_failures"
    if text in {"fail", "failed", "error"}:
        return "failed"
    if text in {"skip", "skipped", "suppressed"}:
        return "suppressed"
    if text in HOOK_LIFECYCLE_STATUSES:
        return text
    return "declared"


def validate_hook_invocation_metadata(metadata: Mapping[str, Any]) -> list[str]:
    """Validate hook invocation metadata has lifecycle and attribution fields."""
    errors: list[str] = []
    status = classify_hook_status(
        str(metadata.get("status", "")),
        error_message=metadata.get("error_message"),
    )
    if status not in HOOK_LIFECYCLE_STATUSES:
        errors.append(f"invalid hook status: {status}")
    for field in HOOK_REQUIRED_ATTRIBUTION:
        if not metadata.get(field):
            errors.append(f"missing hook attribution: {field}")
    if metadata.get("dashboard_authority") is True:
        errors.append("hook dashboard output must not be authority")
    if metadata.get("writes_live_db_in_test") is True:
        errors.append("hook tests must not write live DB")
    return errors


def validate_hook_lifecycle_policy(policy: Mapping[str, Any]) -> list[str]:
    """Validate hook governance policy remains non-executing."""
    errors: list[str] = []
    for key in (
        "changes_hook_execution",
        "writes_db",
        "schema_migration_required",
        "dashboard_authority",
    ):
        if policy.get(key) is not False:
            errors.append(f"{key} must be false")
    for status in HOOK_LIFECYCLE_STATUSES:
        if status not in policy.get("statuses", []):
            errors.append(f"missing lifecycle status: {status}")
    return errors
