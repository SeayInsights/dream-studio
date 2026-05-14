"""Design-only database retention policy.

The policy produced here is not an executor. It classifies table groups and
records future approval gates for cleanup, archive, compaction, and retention.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

DEFAULT_TABLE_GROUPS: tuple[dict[str, Any], ...] = (
    {
        "group": "canonical_authority",
        "tables": ["canonical_events", "decision_records", "outcome_records"],
        "retention_class": "retain_indefinitely",
        "reason": "source authority and outcome lineage must remain available for audit.",
    },
    {
        "group": "telemetry_spine",
        "tables": [
            "execution_events",
            "route_decision_records",
            "hook_invocations",
            "tool_invocations",
            "skill_invocations",
            "workflow_invocations",
        ],
        "retention_class": "retain_then_review_rollups",
        "reason": "raw telemetry powers traceability and should only be reduced after rollup proof.",
    },
    {
        "group": "security_validation",
        "tables": ["security_findings", "validation_results"],
        "retention_class": "retain_until_remediated_and_reviewed",
        "reason": "security and validation records need status-aware review before any retention action.",
    },
    {
        "group": "token_cost",
        "tables": ["token_usage_records"],
        "retention_class": "aggregate_then_archive_candidate",
        "reason": "token detail can later roll up to cost analytics if raw linkage is preserved.",
    },
    {
        "group": "derived_dashboard_projections",
        "tables": ["proj_sessions", "proj_skill_stats", "proj_workflow_runs"],
        "retention_class": "rebuildable_projection",
        "reason": "derived projections are not primary authority and can be rebuilt after source proof.",
    },
    {
        "group": "backups_recovery_artifacts",
        "tables": ["sqlite_backup_files"],
        "retention_class": "manual_review_required",
        "reason": "backup retention touches recovery guarantees and private local state.",
    },
)


def build_db_retention_policy(
    table_groups: Iterable[Mapping[str, Any]] = DEFAULT_TABLE_GROUPS,
) -> dict[str, Any]:
    """Build a design-only retention policy with cleanup execution disabled."""
    groups = [_group(group) for group in table_groups]
    return {
        "artifact_type": "db_retention_policy_design",
        "design_only": True,
        "db_cleanup_execution_allowed": False,
        "record_deletion_allowed": False,
        "table_drop_allowed": False,
        "compaction_execution_allowed": False,
        "migration_required": False,
        "requires_future_operator_approval": True,
        "requires_future_retention_migration": True,
        "groups": groups,
        "approval_gates": [
            "approve_retention_policy",
            "approve_rollup_equivalence_proof",
            "approve_restore_rehearsal",
            "approve_db_cleanup_execution",
        ],
        "default_decision": "retain_when_uncertain",
        "prohibited_without_future_approval": [
            "record deletion",
            "table drop",
            "database compaction",
            "retention migration",
            "cleanup execution",
        ],
    }


def validate_db_retention_policy(policy: Mapping[str, Any]) -> list[str]:
    """Validate that the policy is design-only and has conservative defaults."""
    errors: list[str] = []
    if policy.get("design_only") is not True:
        errors.append("retention policy must be design-only")
    for key in (
        "db_cleanup_execution_allowed",
        "record_deletion_allowed",
        "table_drop_allowed",
        "compaction_execution_allowed",
        "migration_required",
    ):
        if policy.get(key) is not False:
            errors.append(f"{key} must be false")
    if policy.get("default_decision") != "retain_when_uncertain":
        errors.append("uncertain records must default to retain")
    if policy.get("requires_future_operator_approval") is not True:
        errors.append("future operator approval is required")
    for group in policy.get("groups", []):
        if not group.get("tables"):
            errors.append(f"retention group has no tables: {group.get('group')}")
        if group.get("action_now") != "retain":
            errors.append(f"retention group action_now must be retain: {group.get('group')}")
        if group.get("human_review_required") is not True:
            errors.append(f"retention group requires human review: {group.get('group')}")
    return errors


def _group(group: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "group": group.get("group"),
        "tables": list(group.get("tables", [])),
        "retention_class": group.get("retention_class", "manual_review_required"),
        "reason": group.get("reason", "No reason supplied."),
        "action_now": "retain",
        "human_review_required": True,
        "cleanup_execution_allowed": False,
        "future_policy_required": True,
        "rollup_or_restore_proof_required": True,
    }
