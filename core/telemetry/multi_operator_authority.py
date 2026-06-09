"""Authority model for future multi-operator Dream Studio rollups."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.telemetry.org_rollups import build_org_team_rollup_design

ALLOWED_AUTHORITY_MODES = frozenset({"local_instance", "sanitized_summary", "aggregate_rollup"})
FORBIDDEN_CONTRIBUTION_FIELDS = frozenset(
    {
        "raw_prompt",
        "completion",
        "file_contents",
        "secret",
        "api_key",
        "access_token",
        "db_path",
        "local_path",
        "raw_evidence",
    }
)


def build_multi_operator_authority_model(
    contributions: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a model for private local instances contributing summaries later."""

    normalized = [_normalize_contribution(item) for item in contributions]
    return {
        "derived_view": True,
        "primary_authority": False,
        "operator_local_authority_preserved": True,
        "raw_state_exposed": False,
        "allowed_authority_modes": sorted(ALLOWED_AUTHORITY_MODES),
        "forbidden_contribution_fields": sorted(FORBIDDEN_CONTRIBUTION_FIELDS),
        "contributions": normalized,
        "rollup_design": build_org_team_rollup_design([item["summary"] for item in normalized]),
        "conflict_policy": {
            "raw_state_conflict_resolution": "operator_local_instance_wins",
            "summary_conflict_resolution": "newer_signed_summary_supersedes_older_summary",
            "missing_signature": "manual_review_required",
            "stale_summary": "manual_review_required",
        },
        "privacy_policy": {
            "private_raw_state_export_allowed": False,
            "cross_operator_raw_query_allowed": False,
            "summary_hash_or_signature_required": True,
            "operator_revocation_supported": True,
        },
    }


def validate_multi_operator_authority_model(model: Mapping[str, Any]) -> list[str]:
    """Return authority/privacy violations in a multi-operator model."""

    issues: list[str] = []
    if not _truthy(model.get("operator_local_authority_preserved")):
        issues.append("operator_local_authority_must_be_preserved")
    if _truthy(model.get("raw_state_exposed")):
        issues.append("raw_state_must_not_be_exposed")
    for index, contribution in enumerate(_sequence_mapping(model.get("contributions"))):
        raw = _mapping(contribution.get("raw"))
        forbidden = sorted(FORBIDDEN_CONTRIBUTION_FIELDS.intersection(raw))
        if forbidden:
            issues.append(
                f"contribution_{index}_contains_forbidden_raw_fields:{','.join(forbidden)}"
            )
        if not contribution.get("summary_hash"):
            issues.append(f"contribution_{index}_missing_summary_hash")
    return issues


def _normalize_contribution(contribution: Mapping[str, Any]) -> dict[str, Any]:
    summary = _mapping(contribution.get("summary") or contribution)
    raw = _mapping(contribution.get("raw"))
    return {
        "operator_id": str(
            summary.get("operator_id") or contribution.get("operator_id") or "unknown"
        ),
        "authority_mode": _authority_mode(contribution.get("authority_mode")),
        "summary": _strip_forbidden(summary),
        "summary_hash": str(contribution.get("summary_hash") or "").strip(),
        "signature_ref": str(contribution.get("signature_ref") or "").strip(),
        "raw": _strip_forbidden(raw),
        "raw_fields_rejected": sorted(
            FORBIDDEN_CONTRIBUTION_FIELDS.intersection(set(summary) | set(raw))
        ),
    }


def _authority_mode(value: Any) -> str:
    mode = str(value or "sanitized_summary").strip().lower()
    return mode if mode in ALLOWED_AUTHORITY_MODES else "sanitized_summary"


def _strip_forbidden(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): item
        for key, item in value.items()
        if str(key) not in FORBIDDEN_CONTRIBUTION_FIELDS
    }


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


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
