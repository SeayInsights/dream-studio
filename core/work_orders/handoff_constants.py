"""WO-SPLIT-HANDOFF: handoff constants + milestone re-exports."""

from __future__ import annotations
import re

FRESH_SESSION_RULE = (
    "Assume you have no prior conversation context. Use only this prompt and referenced artifacts."
)

READY = "READY"

READY_WITH_CONSTRAINTS = "READY_WITH_CONSTRAINTS"

HOLD = "HOLD"

FAIL = "FAIL"

HANDOFF_PROMPT_COMPLETENESS = "handoff_prompt_completeness"

HANDOFF_CONSTRAINT_PRESERVATION = "handoff_constraint_preservation"

HANDOFF_EXECUTION_READINESS = "handoff_execution_readiness"

HANDOFF_FRESH_SESSION_SUFFICIENCY = "handoff_fresh_session_sufficiency"

HANDOFF_PATH_INTEGRITY = "handoff_path_integrity"

HANDOFF_SELF_VALIDATION = "handoff_self_validation"

HANDOFF_RECOVERY_MODE_COMPLETENESS = "handoff_recovery_mode_completeness"

HANDOFF_CURRENT_STATE_COMPLETENESS = "handoff_current_state_completeness"

HANDOFF_RECOVERY_OPTION_CLARITY = "handoff_recovery_option_clarity"

HANDOFF_OPERATOR_DECISION_GATE = "handoff_operator_decision_gate"

HANDOFF_INDEX_STATE_REQUIREMENTS = "handoff_index_state_requirements"

HANDOFF_HOOK_BEHAVIOR_AWARENESS = "handoff_hook_behavior_awareness"

HANDOFF_PUSH_EXECUTION_COMPLETENESS = "handoff_push_execution_completeness"

HANDOFF_PUSH_TARGET_CONSTRAINTS = "handoff_push_target_constraints"

HANDOFF_PUSH_EVIDENCE_REQUIREMENTS = "handoff_push_evidence_requirements"

SECURITY_HANDOFF_FINDING_REFS_PRESENT = "security_handoff_finding_refs_present"

SECURITY_HANDOFF_RELEASE_GATE_PRESERVED = "security_handoff_release_gate_preserved"

SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED = "security_handoff_target_constraints_preserved"

SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED = "security_handoff_remediation_scope_bounded"

SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED = "security_handoff_forbidden_actions_preserved"

SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL = (
    "security_handoff_no_target_mutation_without_approval"
)

SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE = "security_handoff_no_commit_without_commit_phase"

READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE = "ready_to_copy_next_prompt_contract_compliance"

HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER = "normal_next_work_order"

HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION = "approved_mutation_execution"

HANDOFF_TYPE_COMMIT_EXECUTION = "commit_execution"

HANDOFF_TYPE_RECOVERY_DECISION = "recovery_decision"

HANDOFF_TYPE_RECOVERY_EXECUTION = "recovery_execution"

HANDOFF_TYPE_HOLD_REVIEW = "hold_review"

HANDOFF_TYPES = frozenset(
    {
        HANDOFF_TYPE_NORMAL_NEXT_WORK_ORDER,
        HANDOFF_TYPE_APPROVED_MUTATION_EXECUTION,
        HANDOFF_TYPE_COMMIT_EXECUTION,
        HANDOFF_TYPE_RECOVERY_DECISION,
        HANDOFF_TYPE_RECOVERY_EXECUTION,
        HANDOFF_TYPE_HOLD_REVIEW,
    }
)

PHASE_TYPE_PUSH_PLANNING = "push_planning"

PHASE_TYPE_COMMIT_PLANNING = "commit_planning"

PHASE_TYPE_RECOVERY_DECISION = "recovery_decision"

PHASE_TYPE_PRODUCT_CLOSEOUT = "product_closeout"

PHASE_TYPE_APPROVED_MUTATION = "approved_mutation"

PHASE_TYPE_NORMAL_NEXT_WORK_ORDER = "normal_next_work_order"

DECISION_TAXONOMIES: dict[str, tuple[str, ...]] = {
    PHASE_TYPE_PUSH_PLANNING: (
        "PUSH_READY_WITH_APPROVAL",
        "RUN_BROADER_VALIDATION_FIRST",
        "HOLD",
        "FAIL",
    ),
    PHASE_TYPE_COMMIT_PLANNING: (
        "READY_FOR_COMMIT_PLANNING",
        "NEEDS_ONE_MORE_FIX",
        "HOLD",
        "FAIL",
    ),
    PHASE_TYPE_RECOVERY_DECISION: (
        "LINT_REMEDIATION",
        "NO_VERIFY_CONTINUATION",
        "UNSTAGE_AND_HOLD",
        "ROLLBACK",
        "HOLD",
        "FAIL",
    ),
    PHASE_TYPE_PRODUCT_CLOSEOUT: (
        "READY_FOR_HUMAN_REVIEW",
        "READY_FOR_COMMIT_PLANNING",
        "NEEDS_ONE_MORE_FIX",
        "HOLD",
        "FAIL",
    ),
    PHASE_TYPE_APPROVED_MUTATION: (
        "MUTATION_COMPLETE",
        "NEEDS_REMEDIATION",
        "HOLD",
        "FAIL",
    ),
    PHASE_TYPE_NORMAL_NEXT_WORK_ORDER: (
        "CONTINUE_TO_NEXT_WORK_ORDER",
        "REQUEST_HUMAN_APPROVAL",
        "HOLD",
        "FAIL",
    ),
}

HANDOFF_EVAL_TYPES = frozenset(
    {
        HANDOFF_PROMPT_COMPLETENESS,
        HANDOFF_CONSTRAINT_PRESERVATION,
        HANDOFF_EXECUTION_READINESS,
        HANDOFF_FRESH_SESSION_SUFFICIENCY,
        HANDOFF_PATH_INTEGRITY,
        HANDOFF_RECOVERY_MODE_COMPLETENESS,
        HANDOFF_CURRENT_STATE_COMPLETENESS,
        HANDOFF_RECOVERY_OPTION_CLARITY,
        HANDOFF_OPERATOR_DECISION_GATE,
        HANDOFF_INDEX_STATE_REQUIREMENTS,
        HANDOFF_HOOK_BEHAVIOR_AWARENESS,
        HANDOFF_PUSH_EXECUTION_COMPLETENESS,
        HANDOFF_PUSH_TARGET_CONSTRAINTS,
        HANDOFF_PUSH_EVIDENCE_REQUIREMENTS,
    }
)

SECURITY_HANDOFF_EVAL_TYPES = frozenset(
    {
        SECURITY_HANDOFF_FINDING_REFS_PRESENT,
        SECURITY_HANDOFF_RELEASE_GATE_PRESERVED,
        SECURITY_HANDOFF_TARGET_CONSTRAINTS_PRESERVED,
        SECURITY_HANDOFF_REMEDIATION_SCOPE_BOUNDED,
        SECURITY_HANDOFF_FORBIDDEN_ACTIONS_PRESERVED,
        SECURITY_HANDOFF_NO_TARGET_MUTATION_WITHOUT_APPROVAL,
        SECURITY_HANDOFF_NO_COMMIT_WITHOUT_COMMIT_PHASE,
        READY_TO_COPY_NEXT_PROMPT_CONTRACT_COMPLIANCE,
    }
)

BLOCKING_FAILED_EVALS = frozenset(
    {
        "approved_mutation_compliance",
        "observe_only_compliance",
        "target_repo_mutation",
        "forbidden_action_compliance",
        "skill_identifier_safety",
        "work_order_render_completeness",
        "next_work_order_recommendation",
        "operator_decision_required_before_execution",
        "operator_decision_validity",
        "operator_decision_reason_completeness",
    }
)

REQUIRED_HANDOFF_SECTIONS = (
    "phase_name",
    "handoff_type",
    "phase_type",
    "required_decision_taxonomy",
    "final_decision",
    "decision_rationale",
    "transition_rationale",
    "fresh_session_rule",
    "source_work_order_id",
    "next_work_order_id",
    "dream_studio_repo_path",
    "target_repo_path",
    "baseline_dream_studio_branch_head",
    "baseline_target_repo_branch_head",
    "objective",
    "capability_boundary",
    "approval_mode",
    "risk_level",
    "scope_include",
    "scope_exclude",
    "approved_files_if_mutation_gated",
    "forbidden_files",
    "allowed_actions",
    "forbidden_actions",
    "approval_artifact_requirement",
    "before_after_evidence_requirements",
    "validation_commands",
    "eval_requirements",
    "report_path",
    "output_artifacts",
    "readiness_rules",
    "expected_verdict",
    "stop_conditions",
    "final_response_must_include",
    "next_handoff_requirements",
    "phase_specific_safety_constraints",
    "handoff_understanding_report_requirement",
    "first_safe_action",
)

RECOVERY_DECISION_REQUIRED_SECTIONS = (
    "source_failure",
    "current_state",
    "known_safe_actions",
    "forbidden_recovery_actions",
    "recovery_options",
    "recommended_option",
    "operator_decision_required",
    "do_not_execute_until_decision",
    "index_state_requirements",
    "hook_behavior_risks",
)

PUSH_EXECUTION_REQUIRED_SECTIONS = (
    "approved_push_target",
    "forbidden_push_targets",
    "before_push_evidence_requirements",
    "push_command",
    "after_push_evidence_requirements",
    "sequential_readiness_rules",
    "expected_verdict",
    "next_prompt_report_requirement",
)

SECURITY_REMEDIATION_REQUIRED_SECTIONS = (
    *REQUIRED_HANDOFF_SECTIONS,
    "target_baseline_constraints",
    "release_gate_decision_rules",
)

UNDERSTANDING_REQUIRED_TERMS = (
    "objective",
    "repositories involved",
    "source Work Order ID",
    "next Work Order ID",
    "approval mode",
    "risk level",
    "approved files",
    "forbidden files",
    "allowed commands/actions",
    "forbidden commands/actions",
    "evidence required",
    "validation required",
    "eval requirements",
    "stop conditions",
    "first safe action",
    "missing context",
)

CONSTRAINT_TERMS = (
    "Do not add DB/event ledger integration",
    "Do not add schema migrations",
    "Do not expand Docker",
    "Do not add dashboard projection integration",
    "Do not add TORII integration",
    "Do not add cloud/org/global sync",
    "Do not add enterprise integration",
    "Do not mutate target repos without explicit approval",
    "Do not change skill identifiers",
    "Do not recreate hooks/lib",
)

_MALFORMED_DREAM_STUDIO_META_ROOT_RE = re.compile(
    r"[A-Za-z]:\\Users\\[^\\\r\n]+\.dream-studio(?=\\|/|\s|$)"
)

_WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"[A-Za-z]:[\\/][^\s`<>\"|]+")
