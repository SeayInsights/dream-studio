"""Local-only audit export packet builder."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

FORBIDDEN_EXPORT_FIELDS = frozenset(
    {
        "secret",
        "api_key",
        "access_token",
        "raw_prompt",
        "completion",
        "file_contents",
        "raw_evidence",
        "private_notes",
    }
)


def build_audit_export_packet(
    *,
    release_id: str,
    milestones: Sequence[Mapping[str, Any]] = (),
    validations: Sequence[Mapping[str, Any]] = (),
    decisions: Sequence[Mapping[str, Any]] = (),
    findings: Sequence[Mapping[str, Any]] = (),
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a portable audit packet from structured summaries only."""

    safe_milestones = [_strip_forbidden(item) for item in milestones]
    safe_validations = [_strip_forbidden(item) for item in validations]
    safe_decisions = [_strip_forbidden(item) for item in decisions]
    safe_security = [_strip_forbidden(item) for item in findings]
    refs = [str(ref).strip() for ref in evidence_refs if str(ref).strip()]
    return {
        "packet_type": "dream_studio_audit_export",
        "release_id": release_id,
        "derived_view": True,
        "primary_authority": False,
        "privacy_export_classification": "local_summary_only",
        "raw_content_exported": False,
        "evidence_refs": refs,
        "executive_summary": {
            "milestone_count": len(safe_milestones),
            "validation_count": len(safe_validations),
            "decision_count": len(safe_decisions),
            "security_finding_count": len(safe_security),
            "open_security_finding_count": sum(
                1
                for item in safe_security
                if str(item.get("status", "")).lower() in {"open", "new"}
            ),
            "failed_validation_count": sum(
                1
                for item in safe_validations
                if str(item.get("status", "")).lower() in {"failed", "fail"}
            ),
        },
        "sections": {
            "milestones": safe_milestones,
            "validations": safe_validations,
            "decisions": safe_decisions,
            "findings": safe_security,
            "release_evidence": [{"ref": ref} for ref in refs],
        },
        "export_policy": {
            "forbidden_fields": sorted(FORBIDDEN_EXPORT_FIELDS),
            "raw_files_embedded": False,
            "secret_values_embedded": False,
            "dashboard_is_primary_authority": False,
        },
    }


def validate_audit_export_packet(packet: Mapping[str, Any]) -> list[str]:
    """Return privacy or completeness violations for an audit export packet."""

    issues: list[str] = []
    if _truthy(packet.get("primary_authority")):
        issues.append("audit_packet_must_not_be_primary_authority")
    if _truthy(packet.get("raw_content_exported")):
        issues.append("raw_content_must_not_be_exported")
    if not packet.get("release_id"):
        issues.append("release_id_required")
    sections = packet.get("sections")
    if not isinstance(sections, Mapping):
        issues.append("sections_required")
        return issues
    for section_name, rows in sections.items():
        for index, row in enumerate(_sequence_mapping(rows)):
            forbidden = sorted(FORBIDDEN_EXPORT_FIELDS.intersection(row))
            if forbidden:
                issues.append(
                    f"{section_name}_{index}_contains_forbidden_fields:{','.join(forbidden)}"
                )
    return issues


def _strip_forbidden(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): value for key, value in item.items() if str(key) not in FORBIDDEN_EXPORT_FIELDS
    }


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
