"""File-backed Work Order primitives.

Phase 16B keeps Work Orders in local files only. Importing this package must
not initialize Dream Studio runtime state or open the native runtime DB.
"""

from .models import (
    APPROVAL_MODES,
    PRIVACY_EXPORT_CLASSES,
    RISK_LEVELS,
    STATUSES,
    STORAGE_CLASS,
    WORK_ORDER_ROOT_ENV,
    WorkOrderError,
    load_work_order_file,
    normalize_work_order,
)
from .storage import (
    default_storage_root,
    load_work_order,
    save_work_order,
    status_summary,
    write_existing_work_order,
    work_order_dir,
)
from .validation import ValidationIssue, ValidationResult, validate_work_order
from .decisions import (
    allowed_decisions_for_phase,
    create_decision_request,
    decision_status,
    load_decision_request,
    load_operator_decision,
    record_operator_decision,
)
from .milestones import (
    classify_next_action,
    handoff_required_for_decision,
    validate_authority_pack,
    validate_milestone_completion_criteria,
)
from .handoff import (
    build_security_post_remediation_review_handoff_prompt,
    build_security_remediation_mutation_handoff_prompt,
    build_security_review_remediation_handoff_prompt,
    evaluate_security_post_remediation_review_handoff_prompt,
    evaluate_security_remediation_mutation_handoff_prompt,
    evaluate_security_review_next_handoff_prompt,
    regenerate_handoff_prompt,
    self_validate_generated_handoff,
)
from .renderers import SUPPORTED_RENDER_TARGETS, render_packet_text, render_work_order
from .reporting import generate_report
from .results import record_result
from .sequencing import build_work_order_sequence
from .audit_export import build_audit_export_packet, validate_audit_export_packet

__all__ = [
    "APPROVAL_MODES",
    "PRIVACY_EXPORT_CLASSES",
    "RISK_LEVELS",
    "STATUSES",
    "STORAGE_CLASS",
    "WORK_ORDER_ROOT_ENV",
    "SUPPORTED_RENDER_TARGETS",
    "ValidationIssue",
    "ValidationResult",
    "WorkOrderError",
    "allowed_decisions_for_phase",
    "build_security_post_remediation_review_handoff_prompt",
    "build_security_remediation_mutation_handoff_prompt",
    "build_security_review_remediation_handoff_prompt",
    "build_audit_export_packet",
    "build_work_order_sequence",
    "classify_next_action",
    "create_decision_request",
    "decision_status",
    "default_storage_root",
    "evaluate_security_post_remediation_review_handoff_prompt",
    "evaluate_security_remediation_mutation_handoff_prompt",
    "evaluate_security_review_next_handoff_prompt",
    "generate_report",
    "handoff_required_for_decision",
    "load_decision_request",
    "load_operator_decision",
    "load_work_order",
    "load_work_order_file",
    "normalize_work_order",
    "record_operator_decision",
    "record_result",
    "regenerate_handoff_prompt",
    "render_packet_text",
    "render_work_order",
    "save_work_order",
    "self_validate_generated_handoff",
    "status_summary",
    "validate_authority_pack",
    "validate_audit_export_packet",
    "validate_milestone_completion_criteria",
    "validate_work_order",
    "write_existing_work_order",
    "work_order_dir",
]
