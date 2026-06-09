"""Contract Atlas lifecycle and sanitized export management.

This module orchestrates existing Contract Atlas, maturity ledger, and docs
drift read models. It does not create authority, mutate SQLite, or maintain a
parallel generated-export system. Exports are written only to an explicit
output directory when a caller asks for execution.
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.shared_intelligence.contract_atlas import (
    build_contract_atlas,
    validate_contract_atlas,
)
from core.shared_intelligence.contract_registry import change_impact_report
from core.shared_intelligence.maturity_ledger import (
    maturity_ledger,
    validate_maturity_ledger,
)

CONTRACT_ATLAS_LIFECYCLE_SCHEMA = "dream_studio.contract_atlas_lifecycle.v1"
PUBLIC_SANITIZED_EXPORT_FILENAME = "contract-atlas.public_sanitized.json"
PRIVATE_INTERNAL_EXPORT_FILENAME = "contract-atlas.private_internal.json"
FRESHNESS_MANIFEST_FILENAME = "contract-atlas.freshness-manifest.json"

_PRIVATE_LEAK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("absolute_drive_path", re.compile(r"[A-Za-z]:[\\/]")),
    ("unc_path", re.compile(r"\\\\[^\\/\s]+[\\/]")),
    ("windows_user_path_forward_slash", re.compile(r"\bC:/Users/", re.IGNORECASE)),
    ("windows_user_path_backslash", re.compile(r"\bC:\\Users\\", re.IGNORECASE)),
    ("dream_studio_runtime_path", re.compile(r"\.dream-studio[\\/]", re.IGNORECASE)),
    ("live_backup_root_name", re.compile(r"Dream Studio Live Backups", re.IGNORECASE)),
    ("appdata_path", re.compile(r"\bAppData[\\/]", re.IGNORECASE)),
)


def build_contract_atlas_freshness_manifest(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    project_id: str | None = None,
    changed_files: Iterable[str] = (),
    reviewed_no_change_domains: Iterable[str] = (),
) -> dict[str, Any]:
    """Build a non-mutating freshness manifest for Atlas lifecycle checks."""

    root = Path(repo_root).resolve()
    private_atlas = build_contract_atlas(
        conn,
        repo_root=root,
        project_id=project_id,
        export_scope="private",
    )
    public_atlas = build_contract_atlas(
        conn,
        repo_root=root,
        project_id=project_id,
        export_scope="public",
    )
    private_errors = validate_contract_atlas(private_atlas)
    public_errors = validate_contract_atlas(public_atlas)
    docs_drift = change_impact_report(
        changed_files,
        reviewed_no_change_domains=reviewed_no_change_domains,
    )
    ledger = maturity_ledger(project_id=project_id)
    maturity_errors = validate_maturity_ledger(ledger)
    public_payload = json.dumps(public_atlas, sort_keys=True, ensure_ascii=False)
    leakage = _private_data_leakage_check(public_payload)
    checks = [
        _check(
            "private_internal_contract_atlas_refresh",
            not private_errors,
            errors=private_errors,
            summary="Private/internal Contract Atlas can be regenerated from authority.",
        ),
        _check(
            "public_sanitized_contract_atlas_refresh",
            not public_errors and not leakage["leak_detected"],
            errors=[*public_errors, *leakage["matches"]],
            summary="Public sanitized Contract Atlas export can be regenerated.",
        ),
        _check(
            "maturity_ledger_refresh",
            not maturity_errors,
            errors=maturity_errors,
            summary="Maturity ledger is available and evidence-backed.",
        ),
        _check(
            "docs_prd_readme_impact_detection",
            docs_drift.get("status") == "pass",
            errors=[
                f"{domain['domain_id']}: {domain['missing_required_doc_refs']}"
                for domain in docs_drift.get("blocking_domains", [])
            ],
            summary="Changed files map to required docs, PRD, README, and contract refs.",
        ),
    ]
    status = "pass" if all(item["status"] == "pass" for item in checks) else "fail"
    return {
        "schema": CONTRACT_ATLAS_LIFECYCLE_SCHEMA,
        "model_name": "contract_atlas_lifecycle_freshness_manifest",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id or private_atlas.get("project_id") or "dream-studio",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "db_write_authorized": False,
        "execution_authorized": False,
        "export_write_authorized": False,
        "status": status,
        "source_refs": [
            "core.shared_intelligence.contract_atlas.build_contract_atlas",
            "core.shared_intelligence.contract_registry.change_impact_report",
            "core.shared_intelligence.maturity_ledger.maturity_ledger",
        ],
        "freshness_checks": checks,
        "private_internal_refresh": _export_summary(private_atlas, private_errors),
        "public_sanitized_export_refresh": _export_summary(
            public_atlas,
            [*public_errors, *leakage["matches"]],
        ),
        "public_private_data_leakage_check": leakage,
        "maturity_ledger_refresh": {
            "status": "pass" if not maturity_errors else "fail",
            "area_count": ledger.get("area_count"),
            "status_counts": ledger.get("status_counts"),
            "validation_errors": maturity_errors,
        },
        "docs_prd_readme_impact": _docs_prd_readme_impact(docs_drift),
        "docs_drift_status": docs_drift,
        "release_gate_checks": {
            "status": status,
            "blocking_check_count": sum(1 for item in checks if item["status"] != "pass"),
            "checks": checks,
            "ci_gate_entry": "interfaces/cli/contract_atlas_lifecycle_gate.py",
        },
        "dashboard_api_freshness_status": {
            "status": status,
            "routes": [
                "/api/shared-intelligence/contract-atlas",
                "/api/shared-intelligence/contract-atlas/maturity-ledger",
                "/api/shared-intelligence/contract-atlas/docs-drift",
                "/api/shared-intelligence/contract-atlas/freshness",
            ],
            "dashboard_consumable": True,
            "writes_authorized": False,
        },
        "empty_state": "No changed files were supplied, so the manifest reports current on-demand atlas freshness.",
    }


def refresh_contract_atlas_exports(
    conn: sqlite3.Connection,
    *,
    repo_root: Path,
    output_dir: Path | None,
    project_id: str | None = None,
    changed_files: Iterable[str] = (),
    reviewed_no_change_domains: Iterable[str] = (),
    include_private: bool = False,
    execute: bool = False,
) -> dict[str, Any]:
    """Plan or write explicit Contract Atlas export files.

    Public exports are sanitized. Private/internal exports are available only
    when explicitly requested and should be directed to a private runtime or
    review directory, not the public repo.
    """

    if execute and output_dir is None:
        raise ValueError("contract atlas export execution requires an explicit output_dir")

    root = Path(repo_root).resolve()
    manifest = build_contract_atlas_freshness_manifest(
        conn,
        repo_root=root,
        project_id=project_id,
        changed_files=changed_files,
        reviewed_no_change_domains=reviewed_no_change_domains,
    )
    public_atlas = build_contract_atlas(
        conn,
        repo_root=root,
        project_id=project_id,
        export_scope="public",
    )
    private_atlas = None
    if include_private:
        private_atlas = build_contract_atlas(
            conn,
            repo_root=root,
            project_id=project_id,
            export_scope="private",
        )
    writes = _planned_writes(output_dir=output_dir, include_private=include_private)
    if execute and output_dir is not None:
        target = Path(output_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)
        _write_json(target / PUBLIC_SANITIZED_EXPORT_FILENAME, public_atlas)
        _write_json(target / FRESHNESS_MANIFEST_FILENAME, manifest)
        if include_private and private_atlas is not None:
            _write_json(target / PRIVATE_INTERNAL_EXPORT_FILENAME, private_atlas)

    return {
        "schema": "dream_studio.contract_atlas_export_refresh.v1",
        "model_name": "contract_atlas_export_refresh",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "db_write_authorized": False,
        "sqlite_mutated": False,
        "execute": execute,
        "include_private": include_private,
        "output_dir": str(Path(output_dir).resolve()) if output_dir is not None else None,
        "planned_writes": writes,
        "written_files": writes if execute else [],
        "private_export_repo_safe": False,
        "public_export_sanitized": manifest["public_private_data_leakage_check"]["status"]
        == "pass",
        "manifest_status": manifest["status"],
        "manifest": manifest,
    }


def validate_contract_atlas_lifecycle_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Validate manifest authority and release-gate semantics."""

    errors: list[str] = []
    if manifest.get("derived_view") is not True:
        errors.append("manifest derived_view must be true")
    if manifest.get("primary_authority") is not False:
        errors.append("manifest primary_authority must be false")
    if manifest.get("db_write_authorized") is not False:
        errors.append("manifest must not authorize db writes")
    if manifest.get("execution_authorized") is not False:
        errors.append("manifest must not authorize execution")
    leakage = manifest.get("public_private_data_leakage_check") or {}
    if leakage.get("status") != "pass":
        errors.append("public sanitized export leakage check failed")
    if manifest.get("status") not in {"pass", "fail"}:
        errors.append("manifest status must be pass or fail")
    return errors


def _export_summary(atlas: Mapping[str, Any], errors: list[str]) -> dict[str, Any]:
    payload = json.dumps(atlas, sort_keys=True, ensure_ascii=False)
    return {
        "status": "pass" if not errors else "fail",
        "export_scope": atlas.get("export_scope"),
        "schema": atlas.get("schema"),
        "sanitized_public_export": atlas.get("sanitized_public_export", False),
        "sha256": hashlib.sha256(payload.encode("utf-8")).hexdigest(),
        "byte_length": len(payload.encode("utf-8")),
        "validation_errors": errors,
    }


def _private_data_leakage_check(public_payload: str) -> dict[str, Any]:
    matches: list[str] = []
    for rule_id, pattern in _PRIVATE_LEAK_PATTERNS:
        if pattern.search(public_payload):
            matches.append(f"public export matched private pattern: {rule_id}")
    return {
        "status": "fail" if matches else "pass",
        "leak_detected": bool(matches),
        "matches": matches,
        "patterns_checked": [rule_id for rule_id, _pattern in _PRIVATE_LEAK_PATTERNS],
        "secret_files_read": False,
        "raw_runtime_state_included": False,
    }


def _docs_prd_readme_impact(docs_drift: Mapping[str, Any]) -> dict[str, Any]:
    impacted = [domain for domain in docs_drift.get("domains", []) if domain.get("impacted")]
    prd_domains = [domain["domain_id"] for domain in impacted if domain.get("prd_update_required")]
    readme_domains = [
        domain["domain_id"] for domain in impacted if domain.get("readme_update_required")
    ]
    docs_domains = [
        domain["domain_id"] for domain in impacted if domain.get("docs_update_required")
    ]
    return {
        "status": "pass" if docs_drift.get("status") == "pass" else "attention_required",
        "changed_file_count": docs_drift.get("changed_file_count", 0),
        "impacted_domain_count": docs_drift.get("impacted_domain_count", 0),
        "docs_update_required_domains": docs_domains,
        "prd_update_required_domains": prd_domains,
        "readme_update_required_domains": readme_domains,
        "publication_risk": docs_drift.get("publication_risk", {}),
    }


def _check(
    check_id: str,
    passed: bool,
    *,
    errors: list[str],
    summary: str,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": "pass" if passed else "fail",
        "summary": summary,
        "blocking": not passed,
        "errors": errors,
    }


def _planned_writes(*, output_dir: Path | None, include_private: bool) -> list[str]:
    if output_dir is None:
        return []
    target = Path(output_dir).resolve()
    writes = [
        str(target / PUBLIC_SANITIZED_EXPORT_FILENAME),
        str(target / FRESHNESS_MANIFEST_FILENAME),
    ]
    if include_private:
        writes.append(str(target / PRIVATE_INTERNAL_EXPORT_FILENAME))
    return writes


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
