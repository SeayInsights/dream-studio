import re
from pathlib import Path

TEMPLATE = Path("docs/contracts/security-review-tier0-work-order-template.md")
SAMPLE = Path("docs/contracts/security-review-tier0-work-order.sample.yaml")
STRUCTURED_CATALOG = Path("docs/contracts/security-review-scan-catalog.yaml")


def _template() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def _sample() -> str:
    return SAMPLE.read_text(encoding="utf-8")


def _structured_catalog() -> str:
    return STRUCTURED_CATALOG.read_text(encoding="utf-8")


def _structured_scan_blocks() -> list[str]:
    return [
        "  - scan_id: " + block
        for block in re.split(r"\n  - scan_id: ", "\n" + _structured_catalog())[1:]
    ]


def _tier_scan_ids(tier: str) -> set[str]:
    scan_ids: set[str] = set()

    for block in _structured_scan_blocks():
        scan_id = re.search(r'scan_id: "([^"]+)"', block).group(1)
        tier_match = re.search(r'\n    tier: "([^"]+)"', block)
        if tier_match and tier_match.group(1) == tier:
            scan_ids.add(scan_id)

    return scan_ids


def _sample_selected_scan_ids() -> set[str]:
    return set(re.findall(r'    - "(sec\.[^"]+)"', _sample()))


def test_security_review_tier0_template_exists_and_sets_non_execution_boundary() -> None:
    text = _template()
    required_terms = [
        "Observe-only Tier 0 Security Review Work Order Template",
        "documentation/template data only",
        "not a completed security review",
        "does not inspect target repos",
        "run scans",
        "execute commands",
        "mutate repositories",
        "implement dashboards",
        "claiming the template has reviewed a real target",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_tier0_template_documents_target_intake_fields() -> None:
    text = _template()
    required_fields = [
        "`target_id`",
        "`display_name`",
        "`repo_path`",
        "`repo_kind`",
        "`default_branch`",
        "`active_branch_policy`",
        "`remote_name`",
        "`allowed_read_scope`",
        "`target_output_restrictions`",
        "`generated_artifact_policy`",
        "`dependency_change_policy`",
        "`schema_migration_policy`",
        "`known_dirty_policy`",
        "`privacy_export_classification`",
        "Target intake is scope evidence only",
    ]

    missing = [term for term in required_fields if term not in text]

    assert missing == []


def test_security_review_tier0_template_defines_catalog_selection_rules() -> None:
    text = _template()
    required_terms = [
        "Tier 0 scan selection must be derived from `docs/contracts/security-review-scan-catalog.yaml`",
        "include scan definitions where `tier` is `T0`",
        'require `execution_status: "non_executing_definition"`',
        "require `command_template: null`",
        "require at least one `source_item_refs` entry",
        "do not execute command-based scans",
        "Current Tier 0 scan IDs",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_tier0_sample_selects_exact_t0_catalog_scan_ids() -> None:
    catalog_t0_ids = _tier_scan_ids("T0")
    sample_ids = _sample_selected_scan_ids()

    assert len(catalog_t0_ids) == 18
    assert len(sample_ids) == 18
    assert sample_ids == catalog_t0_ids


def test_security_review_tier0_template_documents_outputs_release_gate_and_dashboard_fields() -> (
    None
):
    text = _template()
    required_terms = [
        "## Output Artifact Expectations",
        "`SecurityReviewReport`",
        "`SecurityEvidenceRecord`",
        "`SecurityFindingRecord`",
        "`AcceptedRiskRecord`",
        "`ReleaseGateSummary`",
        "## Release-gate Decision Handling",
        "SECURITY_CLEAR",
        "SECURITY_CLEAR_WITH_RISKS",
        "ACCEPT_RISK_WITH_APPROVAL",
        "REMEDIATE_BEFORE_RELEASE",
        "RUN_ADDITIONAL_SECURITY_REVIEW",
        "HOLD",
        "FAIL",
        "## Dashboard Projection Readiness Fields",
        "`scan_status_counts`",
        "`findings_by_severity`",
        "`findings_by_release_impact`",
        "`next_work_order_recommendation`",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_tier0_sample_contains_required_template_shape() -> None:
    text = _sample()
    required_terms = [
        'artifact_kind: "SecurityReviewTier0WorkOrderTemplate"',
        'template_id: "security_review_tier0_observe_only"',
        'tier: "T0"',
        'approval_mode: "observe_only"',
        'execution_status: "non_executing_template"',
        "not_a_target_review: true",
        "target_intake_required:",
        "tier0_scan_selection:",
        "total_selected: 18",
        "observe_only_boundary:",
        "evidence_requirements:",
        "output_artifacts:",
        "release_gate_decision_policy:",
        "dashboard_projection_readiness:",
        "next_work_order_recommendation:",
        "command_result: not_run",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_tier0_template_and_sample_do_not_grant_forbidden_authority() -> None:
    combined = f"{_template()}\n{_sample()}"
    required_prohibitions = [
        "target repo mutation",
        "scan execution",
        "target validation",
        "dependency installation",
        "lockfile changes",
        "generated artifacts inside target repos",
        "runtime implementation",
        "CLI command implementation",
        "dashboard UI/API/runtime projection builder implementation",
        "profile registry implementation",
        "DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise expansion",
        "automatic scan execution",
        "dashboard authority",
    ]
    forbidden_phrases = [
        "this template authorizes",
        "this sample authorizes",
        "execute this scan",
        "run this scan",
        "git push",
        "npm install",
        "wrangler deploy",
        "C:\\Users\\Example\\",
        "DreamySuite",
        "Bill Stack",
        "TORII repo",
    ]

    missing = [term for term in required_prohibitions if term not in combined]
    forbidden = [term for term in forbidden_phrases if term in combined]

    assert missing == []
    assert forbidden == []
