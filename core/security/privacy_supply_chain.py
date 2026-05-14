"""Structured security/privacy/supply-chain review packets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REVIEW_CATEGORIES = (
    "sensitive_data_boundaries",
    "dependency_posture",
    "local_file_access",
    "backup_safety",
    "secret_handling",
    "supply_chain_exposure",
)


def build_security_privacy_supply_chain_review(
    findings: Sequence[Mapping[str, Any]] = (),
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a local review packet without extracting secrets or scanning externally."""

    safe_findings = [_safe_finding(item) for item in findings]
    return {
        "packet_type": "security_privacy_supply_chain_review",
        "derived_view": True,
        "primary_authority": False,
        "secret_values_extracted": False,
        "external_scan_run": False,
        "package_commands_run": False,
        "categories": list(REVIEW_CATEGORIES),
        "checklist": _checklist(),
        "findings": safe_findings,
        "summary": {
            "finding_count": len(safe_findings),
            "high_risk_count": sum(1 for item in safe_findings if item.get("risk") == "high"),
            "manual_review_count": sum(
                1 for item in safe_findings if item.get("status") == "manual_review_required"
            ),
        },
        "evidence_refs": [str(ref) for ref in evidence_refs],
    }


def validate_security_privacy_supply_chain_review(packet: Mapping[str, Any]) -> list[str]:
    """Return review packet safety/completeness violations."""

    issues: list[str] = []
    if _truthy(packet.get("secret_values_extracted")):
        issues.append("secret_values_must_not_be_extracted")
    if _truthy(packet.get("external_scan_run")):
        issues.append("external_scan_not_allowed_in_packet_builder")
    if _truthy(packet.get("package_commands_run")):
        issues.append("package_commands_not_allowed_in_packet_builder")
    categories = set(str(item) for item in packet.get("categories", []))
    missing = [category for category in REVIEW_CATEGORIES if category not in categories]
    if missing:
        issues.append(f"missing_review_categories:{','.join(missing)}")
    for index, finding in enumerate(_sequence_mapping(packet.get("findings"))):
        if "secret_value" in finding or "raw_secret" in finding:
            issues.append(f"finding_{index}_contains_secret_value")
    return issues


def _safe_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(finding.get("id") or "unknown"),
        "category": str(finding.get("category") or "manual_review"),
        "risk": str(finding.get("risk") or "unknown").lower(),
        "status": str(finding.get("status") or "manual_review_required"),
        "evidence_ref": str(finding.get("evidence_ref") or ""),
        "secret_value_present": False,
    }


def _checklist() -> list[dict[str, str]]:
    return [
        {
            "category": "sensitive_data_boundaries",
            "check": "No raw secrets or private file contents in evidence.",
        },
        {
            "category": "dependency_posture",
            "check": "Dependency review is read-only unless separately approved.",
        },
        {
            "category": "local_file_access",
            "check": "Local state reads are bounded and source paths are classified.",
        },
        {"category": "backup_safety", "check": "Backups have restore evidence before mutation."},
        {
            "category": "secret_handling",
            "check": "Secret values are never printed, copied, or summarized.",
        },
        {
            "category": "supply_chain_exposure",
            "check": "Push, deploy, package, and external scan boundaries are explicit.",
        },
    ]


def _sequence_mapping(value: Any) -> list[Mapping[str, Any]]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return [item for item in value if isinstance(item, Mapping)]
    return []


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "present"}
    return bool(value)
