from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from core.shared_intelligence.contract_registry import (
    change_impact_report,
    contract_registry,
    validate_contract_registry,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_contract_registry_has_required_release_blocking_domains() -> None:
    registry = contract_registry()

    assert validate_contract_registry(registry) == []
    assert registry["derived_view"] is True
    assert registry["primary_authority"] is False
    assert registry["db_write_authorized"] is False
    domain_ids = {domain["domain_id"] for domain in registry["domains"]}
    assert domain_ids >= {
        "contract_atlas",
        "shared_intelligence_adapters",
        "sqlite_schema_authority",
        "dashboard_runtime",
        "workflow_and_hooks",
        "release_publication_gate",
    }
    assert all(domain["release_blocking"] is True for domain in registry["domains"])


def test_contract_docs_drift_blocks_source_change_without_required_docs() -> None:
    report = change_impact_report(["core/shared_intelligence/contract_atlas.py"])

    assert report["status"] == "fail"
    assert report["blocking_domain_count"] == 1
    blocking = report["blocking_domains"][0]
    assert blocking["domain_id"] == "contract_atlas"
    assert "docs/architecture/contract-atlas.md" in blocking["missing_required_doc_refs"]
    assert "docs/README.md" in blocking["missing_required_doc_refs"]
    assert blocking["docs_update_required"] is True
    assert blocking["contract_atlas_update_required"] is True


def test_contract_docs_drift_passes_when_required_docs_are_refreshed() -> None:
    report = change_impact_report(
        [
            "core/shared_intelligence/contract_atlas.py",
            "docs/architecture/contract-atlas.md",
            "docs/README.md",
            "docs/operations/lint-format-baseline-policy.md",
        ]
    )

    assert report["status"] == "pass"
    impacted = [domain for domain in report["domains"] if domain["impacted"]]
    assert [domain["domain_id"] for domain in impacted] == ["contract_atlas"]
    assert impacted[0]["freshness_status"] == "fresh"
    assert impacted[0]["docs_update_required"] is False


def test_contract_docs_drift_supports_explicit_reviewed_no_change_decision() -> None:
    report = change_impact_report(
        ["core/config/database.py"],
        reviewed_no_change_domains=["sqlite_schema_authority"],
    )

    assert report["status"] == "pass"
    impacted = [domain for domain in report["domains"] if domain["impacted"]]
    assert impacted[0]["domain_id"] == "sqlite_schema_authority"
    assert impacted[0]["freshness_status"] == "docs_reviewed_no_change_needed"
    assert impacted[0]["docs_reviewed_no_change_needed"] is True


def test_contract_docs_drift_detects_private_artifact_publication_risk() -> None:
    report = change_impact_report([".dream-studio/state/studio.db"])

    assert report["status"] == "fail"
    assert report["publication_risk"]["private_artifact_risk_detected"] is True
    assert (
        "remove_private_artifact_from_repo_change_set"
        in report["publication_risk"]["required_actions"]
    )


def test_contract_docs_drift_cli_uses_explicit_changed_files() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "interfaces/cli/contract_docs_drift_gate.py",
            "--changed-file",
            "interfaces/cli/ci_gate.py",
            "--changed-file",
            "interfaces/cli/contract_docs_drift_gate.py",
            "--changed-file",
            "docs/operations/lint-format-baseline-policy.md",
            "--changed-file",
            "README.md",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["impacted_domain_count"] == 1
    assert payload["domains"][-1]["domain_id"] == "release_publication_gate"


def test_contract_docs_drift_cli_fails_on_missing_impacted_docs() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "interfaces/cli/contract_docs_drift_gate.py",
            "--changed-file",
            "core/config/database.py",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["status"] == "fail"
    assert payload["blocking_domains"][0]["domain_id"] == "sqlite_schema_authority"
    assert "docs/DATABASE.md" in payload["blocking_domains"][0]["missing_required_doc_refs"]


def test_contract_docs_drift_cli_accepts_reviewed_no_change() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "interfaces/cli/contract_docs_drift_gate.py",
            "--changed-file",
            "core/config/database.py",
            "--docs-reviewed-no-change",
            "sqlite_schema_authority",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert payload["status"] == "pass"
    assert payload["domains"][2]["freshness_status"] == "docs_reviewed_no_change_needed"
