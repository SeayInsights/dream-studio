from pathlib import Path

CONTRACT = Path("docs/contracts/security-review-profile-pack-contract.md")


def _contract() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def test_security_review_profile_pack_contract_exists_and_sets_boundary() -> None:
    text = _contract()

    expected_terms = [
        "Security Review Profile Pack",
        "not generic Work Order core",
        "not a scan runner",
        "does not execute scans",
        "target repo access requires explicit Work Order scope",
        "accepted risk requires a file-backed operator decision",
        "The future 47-scan catalog must be reviewed as data",
    ]

    missing = [term for term in expected_terms if term not in text]

    assert missing == []


def test_security_review_profile_pack_documents_required_data_shapes() -> None:
    text = _contract()

    required_sections = [
        "## Security Taxonomy",
        "## ScanDefinition",
        "## Evidence Model",
        "## Severity Model",
        "## FindingRecord",
        "## Remediation Handoff Placement",
        "## Security Review Report Contract",
        "## Release-Gate Decision Taxonomy",
        "## Profile Pack Attachment",
        "## Non-Goals",
        "## Safety Rules",
    ]
    required_fields = [
        "`scan_id`",
        "`category_id`",
        "`scan_kind`",
        "`approval_mode_required`",
        "`target_profile_inputs`",
        "`validation_profile_inputs`",
        "`evidence_profile_inputs`",
        "`mutation_risk`",
        "`network_risk`",
        "`evidence_id`",
        "`source_work_order_id`",
        "`no_target_mutation_proof`",
        "`approval_artifact`",
        "`operator_decision_artifact`",
        "`severity`",
        "`confidence`",
        "`release_impact`",
        "`finding_id`",
    ]

    missing = [term for term in [*required_sections, *required_fields] if term not in text]

    assert missing == []


def test_security_release_gate_taxonomy_and_handoff_boundaries_are_explicit() -> None:
    text = _contract()

    required_terms = [
        "SECURITY_CLEAR",
        "SECURITY_CLEAR_WITH_RISKS",
        "ACCEPT_RISK_WITH_APPROVAL",
        "REMEDIATE_BEFORE_RELEASE",
        "RUN_ADDITIONAL_SECURITY_REVIEW",
        "HOLD",
        "FAIL",
        "`hold_review`",
        "`recovery_decision`",
        "`approved_mutation_execution`",
        "must not create a new mutation channel",
        "this contract does not modify core decision taxonomies",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_contract_does_not_grant_forbidden_authority() -> None:
    text = _contract()

    required_prohibitions = [
        "scan command execution",
        "target repo inspection or mutation",
        "runtime execution code",
        "profile registry implementation",
        "database storage or event ledger writes",
        "schema migrations",
        "Docker expansion",
        "dashboard projection integration",
        "TORII, cloud, org, global, or enterprise integration",
        "dependency changes",
        "security remediation",
    ]

    missing = [term for term in required_prohibitions if term not in text]

    assert missing == []
