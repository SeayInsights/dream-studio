from __future__ import annotations

from pathlib import Path


def test_operator_decision_contract_documents_required_artifacts() -> None:
    contract = Path("docs/contracts/operator-decision-contract.md").read_text(encoding="utf-8")

    for required in (
        "Decision Request",
        "Operator Decision",
        "decision_request_id",
        "work_order_id",
        "phase_type",
        "required_decision_taxonomy",
        "pending_operator_decision",
        "allowed_decisions",
        "recommended_decision",
        "requires_reason",
        "decided_by",
        "decided_at",
        "approved_next_handoff_type",
        "privacy_export_classification",
        "operator decision must not mutate a target repo",
        "operator decision does not execute work by itself",
    ):
        assert required in contract


def test_handoff_contract_mentions_operator_decision_gate() -> None:
    contract = Path("docs/contracts/handoff-packet-contract.md").read_text(encoding="utf-8")

    for required in (
        "Operator Decision Gate",
        "decisions/request.json",
        "decisions/operator_decision.json",
        "operator_decision_request_completeness",
        "operator_decision_validity",
        "operator_decision_required_before_execution",
        "operator_decision_reason_completeness",
    ):
        assert required in contract
