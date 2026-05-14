"""Local-first org/team rollup boundary definitions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

ALLOWED_ROLLUP_FIELDS = frozenset(
    {
        "operator_id",
        "team_id",
        "project_count",
        "milestone_count",
        "work_order_count",
        "validation_pass_count",
        "validation_fail_count",
        "security_open_count",
        "security_closed_count",
        "token_total",
        "cost_estimate",
        "approval_waiting_count",
        "blocked_count",
        "generated_at",
    }
)

FORBIDDEN_RAW_FIELDS = frozenset(
    {
        "raw_prompt",
        "prompt",
        "completion",
        "secret",
        "api_key",
        "access_token",
        "file_contents",
        "raw_evidence",
        "local_path",
        "db_path",
        "stack_trace",
    }
)


def build_org_team_rollup_design(operator_summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a future-facing rollup design from sanitized operator summaries."""

    sanitized = [_sanitize_summary(item) for item in operator_summaries]
    return {
        "derived_view": True,
        "primary_authority": False,
        "local_first": True,
        "raw_state_exposed": False,
        "cloud_required": False,
        "aggregation_levels": ["operator", "team", "org"],
        "allowed_fields": sorted(ALLOWED_ROLLUP_FIELDS),
        "forbidden_raw_fields": sorted(FORBIDDEN_RAW_FIELDS),
        "operator_summaries": sanitized,
        "team_rollups": _team_rollups(sanitized),
        "privacy_boundary": {
            "raw_prompts_allowed": False,
            "raw_file_contents_allowed": False,
            "secret_values_allowed": False,
            "local_paths_allowed": False,
            "evidence_refs": "hash_or_summary_only",
        },
    }


def validate_org_team_rollup_design(design: Mapping[str, Any]) -> list[str]:
    """Return boundary violations for an org/team rollup design."""

    issues: list[str] = []
    if not _truthy(design.get("local_first")):
        issues.append("rollup_must_preserve_local_first")
    if _truthy(design.get("raw_state_exposed")):
        issues.append("raw_state_must_not_be_exposed")
    if _truthy(design.get("cloud_required")):
        issues.append("cloud_must_not_be_required")
    for index, summary in enumerate(_sequence_mapping(design.get("operator_summaries"))):
        forbidden = sorted(FORBIDDEN_RAW_FIELDS.intersection(summary))
        if forbidden:
            issues.append(
                f"operator_summary_{index}_contains_forbidden_fields:{','.join(forbidden)}"
            )
    return issues


def _sanitize_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in summary.items():
        normalized = str(key).strip()
        if normalized in ALLOWED_ROLLUP_FIELDS:
            sanitized[normalized] = value
    sanitized.setdefault("operator_id", "unknown")
    sanitized.setdefault("team_id", "local")
    return sanitized


def _team_rollups(summaries: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    teams: dict[str, dict[str, Any]] = {}
    numeric_fields = ALLOWED_ROLLUP_FIELDS - {"operator_id", "team_id", "generated_at"}
    for summary in summaries:
        team_id = str(summary.get("team_id") or "local")
        team = teams.setdefault(team_id, {"team_id": team_id, "operator_count": 0})
        team["operator_count"] += 1
        for field in numeric_fields:
            value = summary.get(field)
            if isinstance(value, (int, float)):
                team[field] = team.get(field, 0) + value
    return sorted(teams.values(), key=lambda item: item["team_id"])


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
