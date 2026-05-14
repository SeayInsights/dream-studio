from pathlib import Path

CONTRACT = Path("docs/contracts/security-review-report-artifact-contract.md")
SAMPLE = Path("docs/contracts/security-review-report.sample.yaml")
PROFILE_PACK = Path("docs/contracts/security-review-profile-pack-contract.md")


def _contract() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def _sample() -> str:
    return SAMPLE.read_text(encoding="utf-8")


def _profile_pack() -> str:
    return PROFILE_PACK.read_text(encoding="utf-8")


def test_security_review_report_artifact_contract_documents_required_shapes() -> None:
    text = _contract()
    required_sections = [
        "## SecurityReviewReport",
        "## SecurityFindingRecord",
        "## SecurityEvidenceRecord",
        "## AcceptedRiskRecord",
        "## ReleaseGateSummary",
        "## SecurityNextWorkOrderRecommendation",
        "## Dashboard Boundary",
        "## Non-Execution Rules",
    ]
    required_fields = [
        "`report_id`",
        "`source_work_order_id`",
        "`target_id`",
        "`security_pack_id`",
        "`catalog_ref`",
        "`review_scope`",
        "`approval_mode`",
        "`verdict`",
        "`release_gate_decision`",
        "`taxonomy_coverage`",
        "`scan_summary`",
        "`findings_summary`",
        "`evidence_inventory`",
        "`accepted_risks`",
        "`no_forbidden_action_proof`",
        "`next_work_order_recommendation`",
        "`ready_to_copy_handoff_packet`",
    ]

    missing = [term for term in [*required_sections, *required_fields] if term not in text]

    assert missing == []


def test_security_review_finding_evidence_and_risk_shapes_are_complete() -> None:
    text = _contract()
    required_fields = [
        "`finding_id`",
        "`scan_id`",
        "`source_item_refs`",
        "`category_id`",
        "`title`",
        "`summary`",
        "`affected_assets`",
        "`severity`",
        "`confidence`",
        "`exploitability`",
        "`scope`",
        "`release_impact`",
        "`privacy_impact`",
        "`remediation_urgency`",
        "`evidence_refs`",
        "`recommended_action`",
        "`remediation_scope_hint`",
        "`status`",
        "`evidence_id`",
        "`evidence_kind`",
        "`before_status`",
        "`after_status`",
        "`command_result`",
        "`external_report_ref`",
        "`no_target_mutation_proof`",
        "`no_generated_artifact_proof`",
        "`evidence_limitations`",
        "`risk_id`",
        "`operator_decision_artifact`",
        "`accepted_by`",
        "`reason`",
        "`constraints`",
        "`expiry_or_review_date`",
        "`residual_risk_summary`",
    ]

    missing = [term for term in required_fields if term not in text]

    assert missing == []


def test_security_review_release_gate_decision_shape_is_explicit() -> None:
    text = _contract()
    required_terms = [
        "`decision`",
        "`rationale`",
        "`blocking_findings`",
        "`accepted_risks`",
        "`deferred_scans`",
        "`required_next_actions`",
        "SECURITY_CLEAR",
        "SECURITY_CLEAR_WITH_RISKS",
        "ACCEPT_RISK_WITH_APPROVAL",
        "REMEDIATE_BEFORE_RELEASE",
        "RUN_ADDITIONAL_SECURITY_REVIEW",
        "HOLD",
        "FAIL",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_report_contract_keeps_dashboard_non_authoritative() -> None:
    text = _contract()
    required_terms = [
        "Future dashboards may project these artifacts but must not become authority",
        "Dashboards may show security posture",
        "Dashboards must not run scans",
        "approve risk",
        "mutate repositories",
        "replace Work Order reports",
        "replace Handoff Packets",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_report_contract_requires_complete_remediation_handoffs() -> None:
    text = _contract()
    required_terms = [
        "Security Review reports that recommend remediation planning must not rely on abbreviated ready-to-copy prompts",
        "release_gate_decision: REMEDIATE_BEFORE_RELEASE",
        "release-gate decision and release-gate decision rules",
        "all finding IDs or short finding references",
        "target path, target branch, target HEAD, and known dirty/untracked constraints",
        "no-scan, no-target-validation, no-target-mutation, no-secret",
        "actual remediation mutation occurs only in a later approved mutation Work Order",
        "fail deterministic evals when these fields are missing",
        "approved_mutation_execution",
        "phase_type: approved_mutation",
        "forbid staging, committing, and pushing",
        "defer commit planning to a later separate Work Order",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_report_contract_does_not_grant_forbidden_authority() -> None:
    text = _contract()
    required_prohibitions = [
        "does not run scans",
        "inspect target repositories",
        "mutate target repositories",
        "add runtime execution code",
        "add CLI commands",
        "create a profile registry",
        "write database/event ledgers",
        "add schema migrations",
        "expand Docker",
        "implement dashboards",
        "add TORII/cloud/org/global/enterprise integration",
        "modify dependencies",
        "change lockfiles",
    ]
    forbidden_authority_phrases = [
        "run this scan",
        "execute this scan",
        "this contract authorizes",
        "this report authorizes",
        "git push",
        "npm install",
        "wrangler deploy",
    ]

    missing = [term for term in required_prohibitions if term not in text]
    forbidden = [term for term in forbidden_authority_phrases if term in text.lower()]

    assert missing == []
    assert forbidden == []


def test_security_review_report_sample_contains_required_top_level_shape() -> None:
    text = _sample()
    required_terms = [
        'artifact_kind: "SecurityReviewReport"',
        'artifact_schema_version: "security_review_report_artifact.v0"',
        'execution_status: "non_executing_report_artifact"',
        'report_id: "sec.report.sample"',
        'source_work_order_id: "wo-dream-studio-sample-security-review"',
        'target_id: "not_applicable"',
        'security_pack_id: "security_review_profile_pack"',
        'catalog_ref: "docs/contracts/security-review-scan-catalog.yaml"',
        "release_gate_decision:",
        "taxonomy_coverage:",
        "scan_summary:",
        "findings_summary:",
        "findings:",
        "evidence_inventory:",
        "accepted_risks:",
        "no_forbidden_action_proof:",
        "next_work_order_recommendation:",
        "ready_to_copy_handoff_packet: null",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_report_sample_remains_non_executing_and_not_target_specific() -> None:
    text = _sample()
    required_terms = [
        'target_repo_access: "not_authorized"',
        'scan_execution: "not_authorized"',
        'command_result: "not_run"',
        "No target repository is in scope for this sample.",
        "No scan, target access, mutation, push, stage, commit, runtime, CLI, DB/event, Docker, dashboard, TORII, cloud, org, global, enterprise, dependency, or lockfile action is represented.",
        "no_scans_run: true",
        "no_runtime_code_added: true",
        "no_dashboard_authority_added: true",
        "no_dependency_or_lockfile_changed: true",
    ]
    forbidden_terms = [
        "C:\\Users\\",
        "DreamySuite",
        "Bill Stack",
        "TORII repo",
        "git push",
        "npm install",
        "wrangler deploy",
        "execute this scan",
        "run this scan",
    ]

    missing = [term for term in required_terms if term not in text]
    forbidden = [term for term in forbidden_terms if term in text]

    assert missing == []
    assert forbidden == []


def test_security_review_profile_pack_references_report_artifacts() -> None:
    text = _profile_pack()
    required_terms = [
        "docs/contracts/security-review-report-artifact-contract.md",
        "docs/contracts/security-review-report.sample.yaml",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []
