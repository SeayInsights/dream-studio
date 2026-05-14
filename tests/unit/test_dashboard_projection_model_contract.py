from pathlib import Path

CONTRACT = Path("docs/contracts/dashboard-projection-model-contract.md")
SAMPLE = Path("docs/contracts/dashboard-projection.sample.yaml")
SECURITY_REPORT_CONTRACT = Path("docs/contracts/security-review-report-artifact-contract.md")


def _contract() -> str:
    return CONTRACT.read_text(encoding="utf-8")


def _sample() -> str:
    return SAMPLE.read_text(encoding="utf-8")


def _security_report_contract() -> str:
    return SECURITY_REPORT_CONTRACT.read_text(encoding="utf-8")


def test_dashboard_projection_contract_documents_required_shapes() -> None:
    text = _contract()
    required_sections = [
        "## DashboardProjectionSnapshot",
        "## WorkOrderOverviewProjection",
        "## EvalProjection",
        "## ApprovalOperatorDecisionProjection",
        "## SecurityReviewProjection",
        "## Stale And Missing Evidence Behavior",
        "## Dashboard Boundary",
        "## Security Projection Source Rules",
    ]
    required_fields = [
        "`projection_id`",
        "`generated_at`",
        "`source_artifact_refs`",
        "`work_orders`",
        "`evals`",
        "`approvals_and_operator_decisions`",
        "`security_reviews`",
        "`stale_or_missing_evidence`",
        "`non_authority_notice`",
    ]

    missing = [term for term in [*required_sections, *required_fields] if term not in text]

    assert missing == []


def test_dashboard_work_order_eval_and_decision_projection_fields_are_complete() -> None:
    text = _contract()
    required_fields = [
        "`work_order_id`",
        "`phase_name`",
        "`approval_mode`",
        "`risk_level`",
        "`readiness`",
        "`verdict`",
        "`final_decision`",
        "`next_action`",
        "`report_ref`",
        "`handoff_ref`",
        "`blocking_risks`",
        "`eval_artifact_ref`",
        "`eval_type`",
        "`pass_fail`",
        "`score`",
        "`evidence_refs`",
        "`blocking`",
        "`limitations`",
        "`approval_artifact_ref`",
        "`approval_status`",
        "`operator_decision_ref`",
        "`selected_decision`",
        "`reason_required`",
        "`reason_present`",
        "`execution_allowed`",
    ]

    missing = [term for term in required_fields if term not in text]

    assert missing == []


def test_dashboard_security_projection_fields_are_complete() -> None:
    text = _contract()
    required_fields = [
        "`security_review_report_ref`",
        "`target_id`",
        "`security_pack_id`",
        "`verdict`",
        "`release_gate_decision`",
        "`taxonomy_coverage`",
        "`scan_status_counts`",
        "`findings_by_severity`",
        "`findings_by_release_impact`",
        "`blocking_findings`",
        "`accepted_risks`",
        "`deferred_scans`",
        "`evidence_inventory_refs`",
        "`next_work_order_recommendation`",
    ]

    missing = [term for term in required_fields if term not in text]

    assert missing == []


def test_dashboard_projection_contract_preserves_non_authority_boundary() -> None:
    text = _contract()
    required_terms = [
        "Dashboard projections are read-only views over file-backed artifacts",
        "They are not authority",
        "Work Orders, reports, approvals, operator decisions, eval artifacts, Handoff Packets, and Security Review artifacts remain the source of truth",
        "Projections must not run scans",
        "Projections must not approve risk",
        "Projections must not mutate repos",
        "Projections must not replace Work Order reports",
        "Projections must not replace operator decisions",
        "Projections must not replace Security Review reports",
        "Projections must not replace Handoff Packets",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_dashboard_projection_contract_documents_stale_and_missing_evidence_behavior() -> None:
    text = _contract()
    required_terms = [
        "Missing report refs must be displayed as missing, not inferred",
        "Missing approval artifacts must display execution as not allowed",
        "Missing operator decisions must display risk acceptance as incomplete",
        "Missing eval artifacts must display eval status as `unknown` or `incomplete`",
        "Missing Security Review reports must display release-gate state as `HOLD` or `unknown`, not clear",
        "Stale source artifacts must display staleness and last-known values separately",
        "Conflicting source artifacts must display conflict notes and must not be resolved silently",
        "Projection snapshots must preserve source artifact refs for manual review",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_dashboard_projection_contract_does_not_grant_forbidden_authority() -> None:
    text = _contract()
    required_prohibitions = [
        "does not implement a dashboard UI",
        "dashboard API",
        "runtime projection builder",
        "database table",
        "event ledger",
        "schema migration",
        "scan runner",
        "profile registry",
        "target repo access",
        "Docker expansion",
        "TORII/cloud/org/global/enterprise integration",
    ]
    forbidden_phrases = [
        "this dashboard authorizes",
        "this projection authorizes",
        "run this scan",
        "execute this scan",
        "git push",
        "npm install",
        "wrangler deploy",
    ]

    missing = [term for term in required_prohibitions if term not in text]
    forbidden = [phrase for phrase in forbidden_phrases if phrase in text.lower()]

    assert missing == []
    assert forbidden == []


def test_dashboard_projection_sample_contains_required_shape() -> None:
    text = _sample()
    required_terms = [
        'artifact_kind: "DashboardProjectionSnapshot"',
        'artifact_schema_version: "dashboard_projection_model.v0"',
        'projection_id: "dashboard.projection.sample"',
        "source_artifact_refs:",
        "non_authority_notice:",
        "stale_or_missing_evidence:",
        "work_orders:",
        "evals:",
        "approvals_and_operator_decisions:",
        "security_reviews:",
        'release_gate_decision: "SECURITY_CLEAR_WITH_RISKS"',
        "scan_status_counts:",
        "findings_by_severity:",
        "findings_by_release_impact:",
        "accepted_risks:",
        "deferred_scans:",
        "evidence_inventory_refs:",
        "next_work_order_recommendation:",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_dashboard_projection_sample_remains_non_executing_and_not_target_specific() -> None:
    text = _sample()
    required_terms = [
        "Dashboard projections are read-only views",
        "must not run scans",
        "approve risk",
        "mutate repos",
        "not_authorized",
        "execution_allowed: false",
        'target_id: "not_applicable"',
        "target repo access",
        "scan execution",
        "dashboard UI implementation",
        "dashboard API implementation",
        "runtime projection builder implementation",
        "DB/event/schema migration",
        "dependency or lockfile changes",
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


def test_security_report_contract_references_dashboard_projection_model() -> None:
    text = _security_report_contract()
    required_terms = [
        "docs/contracts/dashboard-projection-model-contract.md",
        "The projection contract may read and display Security Review artifacts, but it must not replace this contract or become authority",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []
