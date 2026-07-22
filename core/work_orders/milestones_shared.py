"""Shared constants and primitives for PRD-driven milestone classification.

WO-GF-WO-LIFECYCLE: split from ``core/work_orders/milestones.py``. Holds the
next-action / handoff-reason / risk-tier constant tables, the
``NextActionDecision`` reason-coded dataclass, and the small mapping/sequence/
text/truthy coercion helpers shared by the completion and classify siblings.
No logic changes — extracted verbatim from the original module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

NEXT_ACTION_CONTINUE_INTERNAL = "continue_internal"
NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL = "require_operator_approval"
NEXT_ACTION_REQUIRE_OPERATOR_DECISION = "require_operator_decision"
NEXT_ACTION_HARD_STOP = "hard_stop"
NEXT_ACTION_GENERATE_HANDOFF = "generate_handoff"
NEXT_ACTION_COMPLETE_MILESTONE = "complete_milestone"
NEXT_ACTION_START_NEXT_MILESTONE = "start_next_milestone"
NEXT_ACTION_SESSION_TRANSFER = "session_transfer"
NEXT_ACTION_USER_REQUESTED_EXPORT = "user_requested_export"

NEXT_ACTIONS = frozenset(
    {
        NEXT_ACTION_CONTINUE_INTERNAL,
        NEXT_ACTION_REQUIRE_OPERATOR_APPROVAL,
        NEXT_ACTION_REQUIRE_OPERATOR_DECISION,
        NEXT_ACTION_HARD_STOP,
        NEXT_ACTION_GENERATE_HANDOFF,
        NEXT_ACTION_COMPLETE_MILESTONE,
        NEXT_ACTION_START_NEXT_MILESTONE,
        NEXT_ACTION_SESSION_TRANSFER,
        NEXT_ACTION_USER_REQUESTED_EXPORT,
    }
)

HANDOFF_REASON_NONE = "none"
HANDOFF_REASON_OPERATOR_APPROVAL = "operator_approval_required"
HANDOFF_REASON_OPERATOR_DECISION = "operator_decision_required"
HANDOFF_REASON_HARD_BLOCKER = "hard_blocker"
HANDOFF_REASON_MILESTONE_COMPLETION = "milestone_completion_policy_requires_handoff"
HANDOFF_REASON_MATERIAL_RISK_BOUNDARY = "hard_blocker"
HANDOFF_REASON_FAILED_VALIDATION = "failed_validation"
HANDOFF_REASON_ROLLBACK_UNCERTAINTY = "rollback_uncertainty"
HANDOFF_REASON_PAUSE_RESUME = "pause_resume"
HANDOFF_REASON_SESSION_TRANSFER = "session_transfer_required"
HANDOFF_REASON_CONTEXT_TRANSFER = "context_threshold_transfer"
HANDOFF_REASON_USER_EXPORT = "user_requested_export_or_continuation"
HANDOFF_REASON_COMMIT_REQUIRED = "commit_required"
HANDOFF_REASON_PUSH_DEPLOY_REQUIRED = "push_or_deploy_required"
HANDOFF_REASON_DATABASE_MUTATION_REQUIRED = "database_mutation_required"
HANDOFF_REASON_MIGRATION_REQUIRED = "migration_required"
HANDOFF_REASON_DDL_DML_REQUIRED = "ddl_or_dml_required"
HANDOFF_REASON_PACKAGE_REQUIRED = "package_or_dependency_operation_required"
HANDOFF_REASON_RUNTIME_VALIDATION_REQUIRED = "runtime_or_browser_validation_required"
HANDOFF_REASON_SECRET_REQUIRED = "secret_or_sensitive_access_required"
HANDOFF_REASON_ARTIFACT_LIFECYCLE_REQUIRED = "artifact_compaction_deletion_archive_required"
HANDOFF_REASON_EXTERNAL_RESUME_REQUIRED = "external_project_resume_required"

ALLOWED_HANDOFF_REASONS = frozenset(
    {
        HANDOFF_REASON_OPERATOR_APPROVAL,
        HANDOFF_REASON_OPERATOR_DECISION,
        HANDOFF_REASON_HARD_BLOCKER,
        HANDOFF_REASON_FAILED_VALIDATION,
        HANDOFF_REASON_ROLLBACK_UNCERTAINTY,
        HANDOFF_REASON_PAUSE_RESUME,
        HANDOFF_REASON_SESSION_TRANSFER,
        HANDOFF_REASON_CONTEXT_TRANSFER,
        HANDOFF_REASON_USER_EXPORT,
        HANDOFF_REASON_COMMIT_REQUIRED,
        HANDOFF_REASON_PUSH_DEPLOY_REQUIRED,
        HANDOFF_REASON_DATABASE_MUTATION_REQUIRED,
        HANDOFF_REASON_MIGRATION_REQUIRED,
        HANDOFF_REASON_DDL_DML_REQUIRED,
        HANDOFF_REASON_PACKAGE_REQUIRED,
        HANDOFF_REASON_RUNTIME_VALIDATION_REQUIRED,
        HANDOFF_REASON_SECRET_REQUIRED,
        HANDOFF_REASON_ARTIFACT_LIFECYCLE_REQUIRED,
        HANDOFF_REASON_EXTERNAL_RESUME_REQUIRED,
        HANDOFF_REASON_MILESTONE_COMPLETION,
    }
)

INVALID_HANDOFF_REASONS = frozenset(
    {
        "planning_finished",
        "report_written",
        "evidence_created",
        "checklist_review_complete",
        "package_review_needed",
        "routine_validation_needed",
        "next_step_exists",
        "next_milestone_exists",
        "phase_number_incremented",
        "recommended_next_work_order_by_default",
        "legacy_next_work_order_routing",
        "no_reason_given",
        HANDOFF_REASON_NONE,
    }
)

LOW_RISK_STEP_TYPES = frozenset(
    {
        "artifact_read",
        "checklist_review",
        "package_review",
        "evidence_indexing",
        "evidence_creation",
        "report_writing",
        "report_generation",
        "summary",
        "progress_update",
        "non_mutating_validation",
        "backup",
        "checksum",
        "restore_rehearsal",
        "schema_fingerprint",
        "review",
    }
)

MATERIAL_RISK_STEP_TYPES = frozenset(
    {
        "architecture_direction_change",
        "stage_gate_order_change",
        "scope_expansion",
        "source_code_mutation",
        "database_mutation",
        "data_migration",
        "migration",
        "ddl",
        "dml",
        "ddl_or_dml",
        "commit",
        "push",
        "deploy",
        "package_manager",
        "dependency_operation",
        "runtime_browser_validation",
        "artifact_compaction",
        "artifact_deletion",
        "artifact_archive",
        "secret_access",
        "sensitive_data_access",
        "target_repo_work",
        "external_project_resume",
        "executable_design_artifact_execution",
    }
)

HANDOFF_REASON_BY_STEP_TYPE = {
    "database_mutation": HANDOFF_REASON_DATABASE_MUTATION_REQUIRED,
    "data_migration": HANDOFF_REASON_MIGRATION_REQUIRED,
    "migration": HANDOFF_REASON_MIGRATION_REQUIRED,
    "ddl": HANDOFF_REASON_DDL_DML_REQUIRED,
    "dml": HANDOFF_REASON_DDL_DML_REQUIRED,
    "ddl_or_dml": HANDOFF_REASON_DDL_DML_REQUIRED,
    "commit": HANDOFF_REASON_COMMIT_REQUIRED,
    "push": HANDOFF_REASON_PUSH_DEPLOY_REQUIRED,
    "deploy": HANDOFF_REASON_PUSH_DEPLOY_REQUIRED,
    "package_manager": HANDOFF_REASON_PACKAGE_REQUIRED,
    "dependency_operation": HANDOFF_REASON_PACKAGE_REQUIRED,
    "runtime_browser_validation": HANDOFF_REASON_RUNTIME_VALIDATION_REQUIRED,
    "secret_access": HANDOFF_REASON_SECRET_REQUIRED,
    "sensitive_data_access": HANDOFF_REASON_SECRET_REQUIRED,
    "artifact_compaction": HANDOFF_REASON_ARTIFACT_LIFECYCLE_REQUIRED,
    "artifact_deletion": HANDOFF_REASON_ARTIFACT_LIFECYCLE_REQUIRED,
    "artifact_archive": HANDOFF_REASON_ARTIFACT_LIFECYCLE_REQUIRED,
    "target_repo_work": HANDOFF_REASON_EXTERNAL_RESUME_REQUIRED,
    "external_project_resume": HANDOFF_REASON_EXTERNAL_RESUME_REQUIRED,
}

DEFAULT_PAUSED_EXTERNAL_PROJECTS: frozenset[str] = frozenset()


@dataclass(frozen=True)
class NextActionDecision:
    """Reason-coded planner decision for the next milestone action."""

    next_action: str
    handoff_required: bool
    handoff_reason: str = HANDOFF_REASON_NONE
    reasons: tuple[str, ...] = ()
    current_internal_step: str | None = None
    next_milestone: str | None = None
    stop_gate: str | None = None
    why_internal_continuation_is_not_allowed: str | None = None
    required_operator_action: str | None = None
    next_internal_action: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "route_decision": self.next_action,
            "next_action": self.next_action,
            "handoff_required": self.handoff_required,
            "handoff_reason": self.handoff_reason,
            "reasons": list(self.reasons),
            "current_internal_step": self.current_internal_step,
            "next_milestone": self.next_milestone,
            "stop_gate": self.stop_gate,
            "why_internal_continuation_is_not_allowed": self.why_internal_continuation_is_not_allowed,
            "required_operator_action": self.required_operator_action,
            "next_internal_action": self.next_internal_action,
        }


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "present", "approved"}
    return bool(value)
