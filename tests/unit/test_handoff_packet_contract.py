from __future__ import annotations

from pathlib import Path


def test_handoff_packet_contract_documents_required_context_and_safety() -> None:
    contract = Path("docs/contracts/handoff-packet-contract.md").read_text(encoding="utf-8")

    for required in (
        "A Handoff Packet is a ready-to-copy prompt artifact",
        "phase name",
        "handoff type",
        "phase type",
        "required decision taxonomy",
        "final decision",
        "decision rationale",
        "source Work Order ID",
        "next Work Order ID",
        "Dream Studio repo path",
        "target repo path",
        "approval artifact requirement",
        "before/after evidence requirements",
        "readiness rules",
        "expected verdict",
        "fresh-session rule",
        "Handoff Understanding Report",
        "Assume you have no prior conversation context. Use only this prompt and referenced artifacts.",
        "`PASS`",
        "`FAIL`",
        "`INCOMPLETE`",
    ):
        assert required in contract


def test_handoff_packet_contract_documents_deterministic_eval_types() -> None:
    contract = Path("docs/contracts/handoff-packet-contract.md").read_text(encoding="utf-8")

    for eval_type in (
        "handoff_prompt_completeness",
        "handoff_constraint_preservation",
        "handoff_execution_readiness",
        "handoff_fresh_session_sufficiency",
        "handoff_recovery_mode_completeness",
        "handoff_current_state_completeness",
        "handoff_recovery_option_clarity",
        "handoff_operator_decision_gate",
        "handoff_index_state_requirements",
        "handoff_hook_behavior_awareness",
        "handoff_push_execution_completeness",
        "handoff_push_target_constraints",
        "handoff_push_evidence_requirements",
        "security_handoff_finding_refs_present",
        "security_handoff_release_gate_preserved",
        "security_handoff_target_constraints_preserved",
        "security_handoff_remediation_scope_bounded",
        "security_handoff_forbidden_actions_preserved",
        "security_handoff_no_target_mutation_without_approval",
        "security_handoff_no_commit_without_commit_phase",
        "ready_to_copy_next_prompt_contract_compliance",
    ):
        assert eval_type in contract


def test_handoff_packet_contract_documents_security_remediation_handoffs() -> None:
    contract = Path("docs/contracts/handoff-packet-contract.md").read_text(encoding="utf-8")

    for required in (
        "Security Review remediation-planning handoffs",
        "`REMEDIATE_BEFORE_RELEASE`",
        "SecurityReviewReport path",
        "ReleaseGateSummary path",
        "finding and evidence artifact paths",
        "target branch/HEAD constraints",
        "known untracked-entry constraints",
        "no-scan/no-validation/no-target-mutation boundaries",
        "later approved mutation Work Order",
        "Abbreviated security next prompts must fail",
        "Approved security remediation mutation handoffs",
        "forbid staging, committing, and pushing",
        "commit planning occurs in a later separate Work Order",
    ):
        assert required in contract


def test_handoff_packet_contract_documents_recovery_decision_requirements() -> None:
    contract = Path("docs/contracts/handoff-packet-contract.md").read_text(encoding="utf-8")

    for required in (
        "recovery_decision",
        "source_failure",
        "current_state",
        "known_safe_actions",
        "forbidden_recovery_actions",
        "recovery_options",
        "recommended_option",
        "operator_decision_required: true",
        "do_not_execute_until_decision: true",
        "index_state_requirements",
        "hook_behavior_risks",
    ):
        assert required in contract


def test_handoff_packet_contract_documents_decision_taxonomies() -> None:
    contract = Path("docs/contracts/handoff-packet-contract.md").read_text(encoding="utf-8")

    for required in (
        "push_planning",
        "PUSH_READY_WITH_APPROVAL",
        "RUN_BROADER_VALIDATION_FIRST",
        "commit_planning",
        "READY_FOR_COMMIT_PLANNING",
        "recovery_decision",
        "LINT_REMEDIATION",
        "NO_VERIFY_CONTINUATION",
        "UNSTAGE_AND_HOLD",
        "ROLLBACK",
        "product_closeout",
        "READY_FOR_HUMAN_REVIEW",
        "Product closeout and post-push retrospective handoffs must include",
        "approved_mutation",
        "MUTATION_COMPLETE",
    ):
        assert required in contract


def test_handoff_packet_contract_documents_push_execution_requirements() -> None:
    contract = Path("docs/contracts/handoff-packet-contract.md").read_text(encoding="utf-8")

    for required in (
        "Approved Push Target",
        "Forbidden Push Targets",
        "Before-Push Evidence Requirements",
        "Push Command",
        "After-Push Evidence Requirements",
        "no force push",
        "tags",
        "pushing any other branch",
        "fetch origin",
        "ahead/behind",
        "expected HEAD",
        "empty index proof",
    ):
        assert required in contract
