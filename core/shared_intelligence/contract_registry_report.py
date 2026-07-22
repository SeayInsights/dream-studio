"""Contract registry report — contract_registry(), change_impact_report(), validate.

WO-GF-SHARED-INTEL-SPLIT: extracted from contract_registry.py.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Mapping
from datetime import datetime, UTC
from typing import Any

from .contract_registry_constants import (
    CONTRACT_ATLAS_DOC,
    CONTRACT_REGISTRY_SCHEMA,
    DOC_DRIFT_GATE_SCHEMA,
    PRD_DOC,
    PRIVATE_ARTIFACT_PATTERNS,
    PUBLICATION_BOUNDARY_DOC,
    PUBLICATION_RISK_PATTERNS,
    README_DOC,
)
from .contract_registry_domains_ops import CONTRACT_DOMAINS


def contract_registry() -> dict[str, Any]:
    """Return the repo-backed contract registry."""

    return {
        "schema": CONTRACT_REGISTRY_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "db_write_authorized": False,
        "domain_count": len(CONTRACT_DOMAINS),
        "domains": [dict(domain) for domain in CONTRACT_DOMAINS],
        "tracking_mode": "changed_files_same_change_set",
        "empty_state": "No contract domains are registered.",
    }


def change_impact_report(
    changed_files: Iterable[str],
    *,
    reviewed_no_change_domains: Iterable[str] = (),
) -> dict[str, Any]:
    """Map changed files to contract/doc freshness obligations."""

    changed = sorted({_normalize(path) for path in changed_files if path})
    reviewed = sorted({item for item in reviewed_no_change_domains if item})
    private_hits = _matches_any(changed, PRIVATE_ARTIFACT_PATTERNS)
    publication_hits = _matches_any(changed, PUBLICATION_RISK_PATTERNS)
    domains: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    for domain in CONTRACT_DOMAINS:
        source_hits = _matches_any(changed, domain["source_patterns"])
        docs = list(dict.fromkeys(domain["contract_refs"] + domain["docs_refs"]))
        doc_hits = [path for path in changed if path in docs]
        required_docs = list(domain["required_doc_refs"])
        missing = [path for path in required_docs if path not in changed]
        impacted = bool(source_hits)
        reviewed_no_change = bool(impacted and domain["domain_id"] in reviewed)
        status = "not_impacted"
        if impacted:
            if reviewed_no_change:
                status = "docs_reviewed_no_change_needed"
                missing = []
            else:
                status = "fresh" if not missing else "stale_docs_required"
        required_actions = _required_actions(domain, impacted, missing, reviewed_no_change)
        item = {
            "domain_id": domain["domain_id"],
            "domain_name": domain["domain_name"],
            "impacted": impacted,
            "source_hits": source_hits,
            "doc_hits": doc_hits,
            "required_doc_refs": required_docs,
            "missing_required_doc_refs": missing if impacted else [],
            "freshness_status": status,
            "required_actions": required_actions,
            "docs_update_required": "docs_update_required" in required_actions,
            "docs_reviewed_no_change_needed": reviewed_no_change,
            "prd_update_required": "prd_update_required" in required_actions,
            "readme_update_required": "readme_update_required" in required_actions,
            "contract_atlas_update_required": (
                "contract_atlas_update_required" in required_actions
            ),
            "publication_boundary_review_required": (
                "publication_boundary_review_required" in required_actions
            ),
            "release_blocking": bool(domain["release_blocking"]),
            "freshness_policy": domain["freshness_policy"],
            "public_export_boundary": domain["public_export_boundary"],
        }
        domains.append(item)
        if impacted and missing and domain["release_blocking"]:
            blocking.append(item)

    private_artifact_risk_detected = bool(private_hits)
    publication_risk_detected = bool(publication_hits)
    publication_risk = {
        "publication_risk_detected": publication_risk_detected,
        "private_artifact_risk_detected": private_artifact_risk_detected,
        "publication_hits": publication_hits,
        "private_artifact_hits": private_hits,
        "release_blocking": private_artifact_risk_detected,
        "required_actions": _publication_required_actions(
            publication_risk_detected=publication_risk_detected,
            private_artifact_risk_detected=private_artifact_risk_detected,
        ),
    }
    status = "fail" if blocking or private_artifact_risk_detected else "pass"
    return {
        "schema": DOC_DRIFT_GATE_SCHEMA,
        "generated_at": datetime.now(UTC).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "db_write_authorized": False,
        "changed_files": changed,
        "changed_file_count": len(changed),
        "reviewed_no_change_domains": reviewed,
        "tracking_mode": "changed_files_same_change_set",
        "status": status,
        "blocking_domain_count": len(blocking) + (1 if private_artifact_risk_detected else 0),
        "impacted_domain_count": sum(1 for domain in domains if domain["impacted"]),
        "domains": domains,
        "blocking_domains": blocking,
        "publication_risk": publication_risk,
        "gate_distinctions": [
            "docs_update_required",
            "docs_reviewed_no_change_needed",
            "prd_update_required",
            "contract_atlas_update_required",
            "publication_risk_detected",
            "private_artifact_risk_detected",
        ],
        "empty_state": "No changed files were supplied, so no docs drift is detected.",
    }


def validate_contract_registry(registry: Mapping[str, Any] | None = None) -> list[str]:
    """Validate registry shape and referenced docs."""

    payload = dict(registry or contract_registry())
    errors: list[str] = []
    seen: set[str] = set()
    for domain in payload.get("domains", []):
        domain_id = str(domain.get("domain_id") or "")
        if not domain_id:
            errors.append("domain_id is required")
        if domain_id in seen:
            errors.append(f"duplicate domain_id: {domain_id}")
        seen.add(domain_id)
        for key in ("source_patterns", "contract_refs", "required_doc_refs"):
            if not domain.get(key):
                errors.append(f"domain {domain_id} missing {key}")
        required = set(domain.get("required_doc_refs") or [])
        known_docs = set(domain.get("contract_refs") or []) | set(domain.get("docs_refs") or [])
        missing_known = sorted(required - known_docs)
        if missing_known:
            errors.append(f"domain {domain_id} required docs not declared: {missing_known}")
        if domain.get("release_blocking") is not True:
            errors.append(f"domain {domain_id} must be release blocking")
    return errors


def _matches_any(paths: list[str], patterns: Iterable[str]) -> list[str]:
    return [path for path in paths if any(_matches(path, pattern) for pattern in patterns)]


def _matches(path: str, pattern: str) -> bool:
    normalized = _normalize(path)
    normalized_pattern = _normalize(pattern)
    return fnmatch.fnmatchcase(normalized, normalized_pattern)


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _required_actions(
    domain: Mapping[str, Any],
    impacted: bool,
    missing: list[str],
    reviewed_no_change: bool,
) -> list[str]:
    if not impacted:
        return []
    if reviewed_no_change:
        return ["docs_reviewed_no_change_needed"]
    actions: list[str] = []
    if missing:
        actions.append("docs_update_required")
    if PRD_DOC in missing:
        actions.append("prd_update_required")
    if README_DOC in missing:
        actions.append("readme_update_required")
    if CONTRACT_ATLAS_DOC in missing or domain.get("domain_id") == "contract_atlas":
        if missing:
            actions.append("contract_atlas_update_required")
    if PUBLICATION_BOUNDARY_DOC in missing:
        actions.append("publication_boundary_review_required")
    return actions


def _publication_required_actions(
    *,
    publication_risk_detected: bool,
    private_artifact_risk_detected: bool,
) -> list[str]:
    actions: list[str] = []
    if publication_risk_detected:
        actions.append("publication_boundary_review")
    if private_artifact_risk_detected:
        actions.append("remove_private_artifact_from_repo_change_set")
    return actions
