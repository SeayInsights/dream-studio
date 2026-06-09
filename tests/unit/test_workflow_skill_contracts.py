from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from core.shared_intelligence.workflow_skill_contracts import (
    APPROVED_LIFECYCLE_STATE_SET,
    APPROVED_MUTATION_RISK_SET,
    ContractValidationResult,
    SkillContract,
    WorkflowContract,
    example_active_skill_contract,
    example_mutation_capable_workflow_contract,
    example_read_only_workflow_contract,
    example_removal_candidate_skill_contract,
    validate_contract,
    validate_skill_contract,
    validate_workflow_contract,
)


def test_valid_read_only_workflow_contract() -> None:
    contract = example_read_only_workflow_contract()
    result = validate_workflow_contract(contract)

    assert isinstance(contract, WorkflowContract)
    assert result.valid is True
    assert result.errors == []
    assert result.required_operator_decision is False
    assert contract.mutation_risk == "read_only"


def test_valid_mutation_capable_workflow_contract_with_gates_and_approval() -> None:
    contract = example_mutation_capable_workflow_contract()
    result = validate_workflow_contract(contract)

    assert result.valid is True
    assert result.errors == []
    assert result.required_operator_decision is True
    assert "runtime mutation needed" in contract.stop_gates
    assert "current operator source_additive approval" in contract.approval_requirements


def test_invalid_workflow_missing_evidence_requirements() -> None:
    contract = replace(example_read_only_workflow_contract(), evidence_requirements=())

    result = validate_workflow_contract(contract)

    assert result.valid is False
    assert "missing evidence_requirements" in result.errors


def test_invalid_workflow_with_mutation_risk_but_no_stop_gates() -> None:
    contract = replace(example_mutation_capable_workflow_contract(), stop_gates=())

    result = validate_workflow_contract(contract)

    assert result.valid is False
    assert "missing stop_gates" in result.errors
    assert result.required_operator_decision is True


def test_invalid_workflow_with_mutation_risk_but_no_approval_requirements() -> None:
    contract = replace(example_mutation_capable_workflow_contract(), approval_requirements=())

    result = validate_workflow_contract(contract)

    assert result.valid is False
    assert "missing approval_requirements" in result.errors
    assert result.required_operator_decision is True


def test_runtime_sqlite_or_migration_risk_requires_explicit_stop_gate() -> None:
    contract = replace(
        example_mutation_capable_workflow_contract(),
        mutation_risk="sqlite_mutating",
        stop_gates=("file outside approved scope",),
    )

    result = validate_workflow_contract(contract)

    assert result.valid is False
    assert "runtime/SQLite/migration workflow requires explicit runtime or DB stop gate" in (
        result.errors
    )


def test_external_project_mutation_requires_explicit_approval_requirement() -> None:
    contract = replace(
        example_mutation_capable_workflow_contract(),
        mutation_risk="external_project_mutating",
        approval_requirements=("source additive approval",),
    )

    result = validate_workflow_contract(contract)

    assert result.valid is False
    assert "external_project_mutating workflow requires explicit external project approval" in (
        result.errors
    )


def test_valid_active_skill_contract() -> None:
    contract = example_active_skill_contract()
    result = validate_skill_contract(contract)

    assert isinstance(contract, SkillContract)
    assert result.valid is True
    assert result.errors == []
    assert contract.lifecycle_state == "active"
    assert "work_order_planning" in contract.capabilities


def test_invalid_skill_lifecycle_state() -> None:
    contract = replace(example_active_skill_contract(), lifecycle_state="live_consumption_magic")

    result = validate_skill_contract(contract)

    assert result.valid is False
    assert "invalid lifecycle_state: live_consumption_magic" in result.errors


def test_removal_candidate_skill_requires_removal_policy() -> None:
    contract = replace(example_removal_candidate_skill_contract(), removal_policy="")

    result = validate_skill_contract(contract)

    assert result.valid is False
    assert "skill removal_candidate or removed state requires removal_policy" in result.errors


def test_valid_removal_candidate_skill_contract() -> None:
    contract = example_removal_candidate_skill_contract()

    result = validate_skill_contract(contract)

    assert result.valid is True
    assert result.errors == []
    assert "explicit operator approval" in contract.removal_policy


def test_skill_with_secret_access_requires_explicit_approval_boundary() -> None:
    contract = replace(
        example_active_skill_contract(),
        allowed_actions=("read_secrets",),
        forbidden_actions=(),
        privacy_boundary="Can inspect sensitive provider credentials.",
        notes="",
    )

    result = validate_skill_contract(contract)

    assert result.valid is False
    assert result.required_operator_decision is True
    assert (
        "skill allowing secrets/sensitive access requires explicit forbidden action boundary"
        in (result.errors)
    )
    assert "skill allowing secrets/sensitive access requires explicit approval boundary" in (
        result.errors
    )


def test_structured_validation_output_shape() -> None:
    result = validate_contract({"id": "", "version": "", "lifecycle_state": "unknown"})

    assert isinstance(result, ContractValidationResult)
    payload = result.to_dict()
    assert set(payload) == {"valid", "errors", "warnings", "required_operator_decision"}
    assert payload["valid"] is False
    assert isinstance(payload["errors"], list)
    assert isinstance(payload["warnings"], list)
    assert isinstance(payload["required_operator_decision"], bool)


def test_approved_state_and_risk_catalogs_are_stable() -> None:
    assert {
        "proposed",
        "researched",
        "draft_generated",
        "active",
        "deprecated",
        "removal_candidate",
        "removed",
        "retained_reference_only",
    } == set(APPROVED_LIFECYCLE_STATE_SET)
    assert {
        "none",
        "read_only",
        "source_additive",
        "source_mutating",
        "runtime_state_mutating",
        "sqlite_mutating",
        "migration",
        "dependency_mutating",
        "artifact_lifecycle_mutating",
        "external_project_mutating",
        "commit_push_deploy",
        "security_sensitive",
    } == set(APPROVED_MUTATION_RISK_SET)


def test_contract_module_has_no_runtime_sqlite_dependency() -> None:
    module_path = (
        Path(__file__).resolve().parents[2]
        / "core"
        / "shared_intelligence"
        / "workflow_skill_contracts.py"
    )
    source = module_path.read_text(encoding="utf-8")

    assert "sqlite3" not in source
    assert "core.event_store" not in source
    assert "Path.home()" not in source
