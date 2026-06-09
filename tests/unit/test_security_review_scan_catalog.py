import re
from pathlib import Path

CATALOG = Path("docs/contracts/security-review-scan-catalog.md")
SOURCE_LIST = Path("docs/contracts/security-review-source-47-enterprise-scans.md")
CROSSWALK = Path("docs/contracts/security-review-47-scan-crosswalk.md")
SCHEMA = Path("docs/contracts/security-review-scan-definition-schema.md")
SAMPLE = Path("docs/contracts/security-review-scan-catalog.sample.yaml")
STRUCTURED_CATALOG = Path("docs/contracts/security-review-scan-catalog.yaml")
GOVERNANCE = Path("docs/contracts/security-review-catalog-governance.md")

VALID_TIERS = {"T0", "T1", "T2", "T3"}
VALID_CATEGORIES = {
    "dependency_supply_chain",
    "secrets_exposure",
    "static_code_security",
    "configuration_posture",
    "auth_session_access",
    "api_surface",
    "data_handling_privacy",
    "build_release_integrity",
    "infrastructure_runtime",
    "observability_incident",
}
VALID_SCAN_KINDS = {
    "manual_review",
    "static_command",
    "external_report_review",
    "artifact_review",
    "config_review",
    "deferred",
}
VALID_MUTATION_RISKS = {
    "none",
    "writes_cache",
    "writes_artifacts",
    "updates_snapshots",
    "formatting",
    "network",
    "unknown",
}
VALID_NETWORK_RISKS = {
    "none",
    "local_only",
    "external_metadata",
    "external_service",
    "unknown",
}
VALID_COVERAGE_STATUSES = {
    "explicit",
    "grouped",
    "partial",
    "deferred_runtime",
    "deferred_infrastructure",
    "not_applicable_by_default",
    "missing",
}
VALID_RECOMMENDED_ACTIONS = {
    "keep",
    "add explicit scan",
    "split scan",
    "rename scan",
    "add source_item_refs",
    "defer",
    "no action",
}


def _catalog() -> str:
    return CATALOG.read_text(encoding="utf-8")


def _source_list() -> str:
    return SOURCE_LIST.read_text(encoding="utf-8")


def _crosswalk() -> str:
    return CROSSWALK.read_text(encoding="utf-8")


def _schema() -> str:
    return SCHEMA.read_text(encoding="utf-8")


def _sample() -> str:
    return SAMPLE.read_text(encoding="utf-8")


def _structured_catalog() -> str:
    return STRUCTURED_CATALOG.read_text(encoding="utf-8")


def _governance() -> str:
    return GOVERNANCE.read_text(encoding="utf-8")


def _cell_value(cell: str) -> str:
    return cell.strip().strip("`")


def _scan_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for line in _catalog().splitlines():
        if not line.startswith("| `sec."):
            continue

        cells = [_cell_value(cell) for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 9

        rows.append(
            {
                "scan_id": cells[0],
                "tier": cells[1],
                "category": cells[2],
                "scan_kind": cells[3],
                "intent": cells[4],
                "mutation_risk": cells[5],
                "network_risk": cells[6],
                "evidence_inputs": cells[7],
                "remediation_handoff": cells[8],
            }
        )

    return rows


def _source_items() -> list[tuple[int, str]]:
    items: list[tuple[int, str]] = []

    for line in _source_list().splitlines():
        match = re.match(r"^(\d+)\. (.+)$", line)
        if match:
            items.append((int(match.group(1)), match.group(2)))

    return items


def _crosswalk_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for line in _crosswalk().splitlines():
        if not re.match(r"^\| \d+ \|", line):
            continue

        cells = [_cell_value(cell) for cell in line.strip().strip("|").split("|")]
        assert len(cells) == 7

        rows.append(
            {
                "original_number": cells[0],
                "original_item_name": cells[1],
                "original_domain": cells[2],
                "coverage_status": cells[3],
                "catalog_scan_ids": cells[4],
                "rationale": cells[5],
                "recommended_action": cells[6],
            }
        )

    return rows


def _structured_scan_blocks() -> list[str]:
    text = _structured_catalog()
    blocks = re.split(r"\n  - scan_id: ", "\n" + text)[1:]

    return ["  - scan_id: " + block for block in blocks]


def test_security_review_scan_catalog_exists_and_is_non_executing() -> None:
    text = _catalog()

    required_terms = [
        "This catalog drafts enterprise security review scans",
        "The source list remains exactly 47 original enterprise items",
        "not execution authority",
        "does not run scans",
        "Target repo access requires a future scoped Work Order",
        "Command-based scans may be described as `static_command`, but command templates remain absent",
        "docs/contracts/security-review-scan-definition-schema.md",
        "docs/contracts/security-review-scan-catalog.sample.yaml",
        "docs/contracts/security-review-scan-catalog.yaml",
        "docs/contracts/security-review-catalog-governance.md",
    ]
    forbidden_authority_phrases = [
        "run this scan",
        "execute this scan",
        "execute the catalog",
        "this catalog authorizes",
        "auto-run",
        "automatically run",
        "git push",
        "npm install",
        "wrangler deploy",
    ]

    missing = [term for term in required_terms if term not in text]
    forbidden = [phrase for phrase in forbidden_authority_phrases if phrase in text.lower()]

    assert missing == []
    assert forbidden == []


def test_security_review_scan_catalog_contains_revised_unique_scan_ids() -> None:
    rows = _scan_rows()
    scan_ids = [row["scan_id"] for row in rows]

    assert len(rows) == 75
    assert len(set(scan_ids)) == 75
    assert all(scan_id.startswith("sec.") for scan_id in scan_ids)


def test_security_review_scan_catalog_adds_priority_coverage_rows() -> None:
    scan_ids = {row["scan_id"] for row in _scan_rows()}
    required_scan_ids = {
        "sec.static.xss_output_encoding",
        "sec.static.memory_safety_boundary_review",
        "sec.static.concurrency_race_review",
        "sec.static.ssrf_request_boundary_review",
        "sec.static.xxe_parser_review",
        "sec.dast.runtime_injection_testing",
        "sec.dast.tls_ssl_configuration_review",
        "sec.secrets.git_history_secret_review",
        "sec.secrets.certificate_key_management_review",
        "sec.secrets.cicd_secret_exposure_review",
        "sec.infra.container_registry_security_review",
        "sec.infra.kubernetes_pod_security_review",
        "sec.infra.cloud_misconfiguration_review",
        "sec.infra.iam_least_privilege_review",
        "sec.infra.network_segmentation_review",
        "sec.compliance.regulatory_mapping_review",
        "sec.obs.incident_response_error_handling_review",
    }

    assert required_scan_ids <= scan_ids


def test_security_review_scan_catalog_rows_use_contract_values() -> None:
    invalid_rows: list[dict[str, str]] = []

    for row in _scan_rows():
        if (
            row["tier"] not in VALID_TIERS
            or row["category"] not in VALID_CATEGORIES
            or row["scan_kind"] not in VALID_SCAN_KINDS
            or row["mutation_risk"] not in VALID_MUTATION_RISKS
            or row["network_risk"] not in VALID_NETWORK_RISKS
        ):
            invalid_rows.append(row)

    assert invalid_rows == []


def test_security_review_scan_catalog_rows_include_required_field_content() -> None:
    incomplete_rows = [
        row
        for row in _scan_rows()
        if not row["intent"] or not row["evidence_inputs"] or not row["remediation_handoff"]
    ]

    assert incomplete_rows == []


def test_security_review_scan_catalog_has_expected_tier_distribution() -> None:
    rows = _scan_rows()
    counts = {tier: len([row for row in rows if row["tier"] == tier]) for tier in VALID_TIERS}

    assert counts == {
        "T0": 18,
        "T1": 19,
        "T2": 28,
        "T3": 10,
    }


def test_security_review_source_list_preserves_operator_supplied_47_items() -> None:
    text = _source_list()
    items = _source_items()
    domains = [line for line in text.splitlines() if line.startswith("DOMAIN ")]

    assert len(domains) == 7
    assert len(items) == 47
    assert [number for number, _name in items] == list(range(1, 48))
    assert items[0] == (1, "SQL Injection Detection")
    assert items[-1] == (47, "Dependency & Build Reproducibility")
    assert "DOMAIN 1 \u2014 SOURCE CODE ANALYSIS (SAST)" in text
    assert "DOMAIN 7 \u2014 COMPLIANCE, GOVERNANCE & OPERATIONAL SECURITY" in text
    assert "operator-supplied inline content in Phase 18S.3A" in text


def test_security_review_crosswalk_maps_all_47_source_items_once() -> None:
    source_items = dict(_source_items())
    rows = _crosswalk_rows()
    row_numbers = [int(row["original_number"]) for row in rows]

    assert len(rows) == 47
    assert row_numbers == list(range(1, 48))

    mismatches = [
        row
        for row in rows
        if source_items[int(row["original_number"])] != row["original_item_name"]
    ]

    assert mismatches == []


def test_security_review_crosswalk_uses_valid_statuses_and_actions() -> None:
    invalid_rows = [
        row
        for row in _crosswalk_rows()
        if row["coverage_status"] not in VALID_COVERAGE_STATUSES
        or row["recommended_action"] not in VALID_RECOMMENDED_ACTIONS
        or not row["rationale"]
    ]

    assert invalid_rows == []


def test_security_review_crosswalk_has_no_missing_or_partial_coverage_after_revision() -> None:
    rows = _crosswalk_rows()
    counts = {
        status: len([row for row in rows if row["coverage_status"] == status])
        for status in VALID_COVERAGE_STATUSES
    }

    assert counts == {
        "explicit": 34,
        "grouped": 0,
        "partial": 0,
        "deferred_runtime": 8,
        "deferred_infrastructure": 5,
        "not_applicable_by_default": 0,
        "missing": 0,
    }


def test_security_review_crosswalk_remains_non_executing() -> None:
    text = _crosswalk()

    required_terms = [
        "does not implement scans",
        "run scans",
        "authorize target repo access",
        "coverage evidence only",
    ]
    forbidden_authority_phrases = [
        "run this scan",
        "execute this scan",
        "this crosswalk authorizes",
        "git push",
        "npm install",
        "wrangler deploy",
    ]

    missing = [term for term in required_terms if term not in text]
    forbidden = [phrase for phrase in forbidden_authority_phrases if phrase in text.lower()]

    assert missing == []
    assert forbidden == []


def test_security_review_scan_definition_schema_documents_required_shape() -> None:
    text = _schema()
    required_terms = [
        "## ScanDefinition Shape",
        "`scan_id`",
        "`title`",
        "`tier`",
        "`source_item_refs`",
        "`category_id`",
        "`scan_kind`",
        "`intent`",
        "`phase_allowed`",
        "`approval_mode_required`",
        "`target_profile_inputs`",
        "`validation_profile_inputs`",
        "`evidence_profile_inputs`",
        "`mutation_risk`",
        "`network_risk`",
        "`artifact_write_risk`",
        "`prerequisites`",
        "`expected_outputs`",
        "`timeout_policy`",
        "`safe_failure_mode`",
        "`false_positive_notes`",
        "`remediation_handoff_hint`",
        "`execution_status`",
        "non_executing_definition",
        "## SourceItemRef Shape",
        "`item_number`",
        "`item_name`",
        "`domain`",
        "`coverage_status`",
        "`coverage_rationale`",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_scan_definition_schema_keeps_non_execution_boundary() -> None:
    text = _schema()
    required_terms = [
        "does not implement scan execution",
        "Structured scan definitions are profile-pack data",
        "`command_template` is optional and must remain absent or `null`",
        "target repository access requires a future scoped Work Order",
        "Do not implement these in this schema draft",
    ]
    forbidden_terms = [
        "execute this scan",
        "run this scan",
        "this schema authorizes",
        "git push",
        "npm install",
        "wrangler deploy",
    ]

    missing = [term for term in required_terms if term not in text]
    forbidden = [term for term in forbidden_terms if term in text.lower()]

    assert missing == []
    assert forbidden == []


def test_security_review_scan_catalog_sample_demonstrates_required_mappings() -> None:
    text = _sample()
    required_terms = [
        "catalog_schema_version: security_review_scan_definition.v0",
        "execution_status: non_executing_definition",
        "source_item_refs:",
        "coverage_status: explicit",
        "coverage_status: deferred_runtime",
        "coverage_status: deferred_infrastructure",
        "scan_id: sec.static.injection_patterns",
        "scan_id: sec.dast.runtime_injection_testing",
        "scan_id: sec.infra.kubernetes_pod_security_review",
        "scan_id: sec.compliance.regulatory_mapping_review",
        "command_template: null",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []
    assert text.count("\n        item_number: 1\n") == 1
    assert text.count("\n        item_number: 3\n") == 1


def test_security_review_scan_catalog_sample_remains_non_executing() -> None:
    text = _sample()
    forbidden_terms = [
        "git push",
        "npm install",
        "wrangler deploy",
        "execute this scan",
        "run this scan",
        "this file authorizes",
    ]

    forbidden = [term for term in forbidden_terms if term in text.lower()]

    assert forbidden == []


def test_structured_security_review_catalog_has_required_top_level_fields() -> None:
    text = _structured_catalog()
    required_terms = [
        'catalog_id: "security_review_scan_catalog"',
        'version: "0.1.0"',
        'draft_status: "structured_draft"',
        'source_standard_ref: "docs/contracts/security-review-source-47-enterprise-scans.md"',
        'schema_ref: "docs/contracts/security-review-scan-definition-schema.md"',
        'crosswalk_ref: "docs/contracts/security-review-47-scan-crosswalk.md"',
        'markdown_catalog_ref: "docs/contracts/security-review-scan-catalog.md"',
        "non_execution_notice:",
        'execution_status: "non_executing_definition"',
        "scans:",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_structured_security_review_catalog_contains_75_unique_scan_definitions() -> None:
    blocks = _structured_scan_blocks()
    scan_ids = [re.search(r'scan_id: "([^"]+)"', block).group(1) for block in blocks]

    assert len(blocks) == 75
    assert len(set(scan_ids)) == 75
    assert set(scan_ids) == {row["scan_id"] for row in _scan_rows()}


def test_structured_security_review_catalog_scan_blocks_have_required_fields() -> None:
    required_fields = [
        "title",
        "tier",
        "source_item_refs",
        "category_id",
        "scan_kind",
        "intent",
        "phase_allowed",
        "approval_mode_required",
        "target_profile_inputs",
        "validation_profile_inputs",
        "evidence_profile_inputs",
        "mutation_risk",
        "network_risk",
        "artifact_write_risk",
        "prerequisites",
        "expected_outputs",
        "timeout_policy",
        "safe_failure_mode",
        "false_positive_notes",
        "remediation_handoff_hint",
        "execution_status",
        "command_template",
    ]
    incomplete: list[str] = []

    for block in _structured_scan_blocks():
        scan_id = re.search(r'scan_id: "([^"]+)"', block).group(1)
        missing = [field for field in required_fields if f"\n    {field}:" not in block]
        if missing or "\n      - source_list_ref:" not in block:
            incomplete.append(f"{scan_id}: {missing}")

    assert incomplete == []


def test_structured_security_review_catalog_preserves_source_item_traceability() -> None:
    text = _structured_catalog()
    item_numbers = {int(match) for match in re.findall(r"\n        item_number: (\d+)\n", text)}

    assert item_numbers == set(range(1, 48))
    assert text.count("source_item_refs:") == 75


def test_structured_security_review_catalog_remains_non_executing() -> None:
    text = _structured_catalog()

    assert text.count('execution_status: "non_executing_definition"') == 76
    assert text.count("command_template: null") == 75

    forbidden_terms = [
        "git push",
        "npm install",
        "wrangler deploy",
        "execute this scan",
        "run this scan",
        "this catalog authorizes",
    ]
    forbidden = [term for term in forbidden_terms if term in text.lower()]

    assert forbidden == []


def test_security_review_catalog_governance_documents_canonical_artifact_roles() -> None:
    text = _governance()
    required_terms = [
        "## Canonical Artifact Roles",
        "`docs/contracts/security-review-source-47-enterprise-scans.md` | Source standard",
        "`docs/contracts/security-review-47-scan-crosswalk.md` | Traceability authority",
        "`docs/contracts/security-review-scan-catalog.yaml` | Machine-readable catalog source",
        "`docs/contracts/security-review-scan-catalog.md` | Human-readable documentation",
        "`docs/contracts/security-review-scan-definition-schema.md` | Schema authority",
        "`docs/contracts/security-review-scan-catalog.sample.yaml` | Non-canonical illustrative excerpt",
        "`docs/contracts/security-review-profile-pack-contract.md` | Profile-pack boundary contract",
        "The original 47 source list is the source standard",
        "Changes to it require explicit operator approval",
        "The structured YAML catalog is the machine-readable catalog source",
        "The crosswalk is the traceability authority",
        "The markdown catalog is human-readable documentation",
        "The schema document defines allowed fields",
        "The sample YAML is not canonical",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_catalog_governance_documents_required_drift_checks() -> None:
    text = _governance()
    required_terms = [
        "## Drift Prevention Checks",
        "75 YAML scans match markdown scan IDs",
        "every YAML scan has source_item_refs",
        "every source item 1-47 appears in at least one YAML scan",
        "every crosswalk row maps to valid YAML scan IDs",
        "every scan is non-executing",
        "every command_template remains null",
        "no target repo, runtime, CLI, dashboard, DB/event, Docker, TORII, cloud, org, global, enterprise, dependency, or lockfile authority is introduced",
        "Catalog row additions require updates to the YAML catalog, markdown catalog, crosswalk, and static tests",
        "YAML catalog changes require static tests before acceptance",
        "Markdown catalog changes must not contradict the YAML catalog or crosswalk",
        "Source list changes require explicit operator approval",
        "Scan execution requires a later approved Work Order",
    ]

    missing = [term for term in required_terms if term not in text]

    assert missing == []


def test_security_review_crosswalk_scan_ids_are_valid_structured_catalog_ids() -> None:
    structured_ids = {
        re.search(r'scan_id: "([^"]+)"', block).group(1) for block in _structured_scan_blocks()
    }
    invalid_rows: list[dict[str, str]] = []

    for row in _crosswalk_rows():
        scan_ids = re.findall(r"sec\.[A-Za-z0-9_.]+", row["catalog_scan_ids"])
        if not scan_ids or any(scan_id not in structured_ids for scan_id in scan_ids):
            invalid_rows.append(row)

    assert invalid_rows == []


def test_security_review_catalog_governance_remains_non_executing() -> None:
    text = _governance()
    required_terms = [
        "does not authorize target repo access",
        "scan execution",
        "runtime implementation",
        "CLI command implementation",
        "profile registry implementation",
        "DB/event/schema/Docker/dashboard/TORII/cloud/org/global/enterprise expansion",
        "dependency changes",
        "lockfile changes",
        "repository mutation",
        "Security Review catalog artifacts are not execution authority",
    ]
    forbidden_terms = [
        "this governance authorizes",
        "run this scan",
        "execute this scan",
        "git push",
        "npm install",
        "wrangler deploy",
    ]

    missing = [term for term in required_terms if term not in text]
    forbidden = [term for term in forbidden_terms if term in text.lower()]

    assert missing == []
    assert forbidden == []
