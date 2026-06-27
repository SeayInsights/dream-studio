"""Model/provider registry read models backed by SQLite authority."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from typing import Any

from core.shared_intelligence.authority import require_shared_intelligence_tables

MODEL_REGISTRY_SOURCE_TABLES: tuple[str, ...] = ("model_provider_profiles",)


def model_provider_registry_summary(conn: sqlite3.Connection) -> dict[str, Any]:
    """Summarize recorded model/provider profiles without provider calls."""

    require_shared_intelligence_tables(conn)
    profiles = _model_profiles(conn)
    provider_counts = Counter(profile["provider"] for profile in profiles)
    capability_counts: Counter[str] = Counter()
    failure_mode_counts: Counter[str] = Counter()
    for profile in profiles:
        capability_counts.update(profile["capability_tags"])
        failure_mode_counts.update(profile["failure_modes"])

    return _with_authority(
        "shared_intelligence_model_provider_registry_summary",
        {
            "model_count": len(profiles),
            "provider_counts": dict(sorted(provider_counts.items())),
            "capability_counts": dict(sorted(capability_counts.items())),
            "failure_mode_counts": dict(sorted(failure_mode_counts.items())),
            "profiles": profiles,
            "facts_available": bool(profiles),
            "provider_api_calls_performed": False,
            "billing_authority": False,
            "cost_records_are_estimates": False,
            "cost_records_require_source": True,
            "cost_records_may_be_estimated_only_when_marked": True,
            "empty_state": "No model/provider profiles recorded in SQLite authority.",
        },
    )


def model_provider_capability_matrix(
    conn: sqlite3.Connection,
    *,
    required_capabilities: list[str] | tuple[str, ...] = (),
    min_context_tokens: int | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """Return model profiles matching recorded capability constraints."""

    require_shared_intelligence_tables(conn)
    required = {str(capability) for capability in required_capabilities}
    profiles = _model_profiles(conn)
    matches: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for profile_row in profiles:
        profile_capabilities = set(profile_row["capability_tags"])
        reasons: list[str] = []
        if provider and profile_row["provider"] != provider:
            reasons.append("provider_mismatch")
        missing = sorted(required - profile_capabilities)
        if missing:
            reasons.append("missing_capabilities:" + ",".join(missing))
        if min_context_tokens is not None:
            context_limit = profile_row.get("context_limit_tokens")
            if context_limit is None or int(context_limit) < int(min_context_tokens):
                reasons.append("context_limit_too_small")
        row = {
            **profile_row,
            "required_capabilities": sorted(required),
            "match_reasons": [] if reasons else ["recorded_profile_matches_constraints"],
            "rejection_reasons": reasons,
        }
        if reasons:
            rejected.append(row)
        else:
            matches.append(row)

    by_provider: dict[str, list[str]] = defaultdict(list)
    for match in matches:
        by_provider[str(match["provider"])].append(str(match["model_id"]))

    return _with_authority(
        "shared_intelligence_model_provider_capability_matrix",
        {
            "required_capabilities": sorted(required),
            "min_context_tokens": min_context_tokens,
            "provider": provider,
            "matches": matches,
            "rejected": rejected,
            "matches_by_provider": dict(sorted(by_provider.items())),
            "match_count": len(matches),
            "facts_available": bool(profiles),
            "provider_api_calls_performed": False,
            "billing_authority": False,
            "cost_records_are_estimates": False,
            "cost_records_require_source": True,
            "cost_records_may_be_estimated_only_when_marked": True,
            "empty_state": "No recorded model/provider profile matches the requested capabilities.",
        },
    )


def model_provider_registry_policy() -> dict[str, Any]:
    """Return the registry policy for future provider profile promotion."""

    return {
        "policy_id": "model_provider_registry_policy",
        "source_authority": "sqlite",
        "provider_api_calls_default": False,
        "billing_authority": False,
        "cost_records_are_estimates": False,
        "cost_records_require_source": True,
        "cost_records_may_be_estimated_only_when_marked": True,
        "requires_source_refs": True,
        "requires_evidence_refs": True,
        "latest_model_claims_require_fresh_verification": True,
        "profile_writes_require_injected_connection": True,
    }


def _model_profiles(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    # model_provider_profiles dropped migration 131 — return empty gracefully
    try:
        rows = conn.execute("""
            SELECT *
            FROM model_provider_profiles
            ORDER BY provider ASC, model_id ASC
            """).fetchall()
    except Exception:
        return []
    return [_decode_profile(row) for row in rows]


def _decode_profile(row: sqlite3.Row) -> dict[str, Any]:
    profile = dict(row)
    profile["capability_tags"] = _loads(profile.pop("capability_tags_json"), [])
    profile["cost_profile"] = _loads(profile.pop("cost_profile_json"), {})
    profile["token_behavior"] = _loads(profile.pop("token_behavior_json"), {})
    profile["output_quality"] = _loads(profile.pop("output_quality_json"), {})
    profile["failure_modes"] = _loads(profile.pop("failure_modes_json"), [])
    profile["best_use_patterns"] = _loads(profile.pop("best_use_patterns_json"), [])
    profile["source_refs"] = _loads(profile.pop("source_refs_json"), [])
    profile["evidence_refs"] = _loads(profile.pop("evidence_refs_json"), [])
    return profile


def _loads(raw: str | None, default: Any) -> Any:
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return default


def _with_authority(model_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_name": model_name,
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "source_tables": list(MODEL_REGISTRY_SOURCE_TABLES),
        **payload,
    }
