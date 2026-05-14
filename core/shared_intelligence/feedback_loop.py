"""Cross-model learning feedback derived from SQLite authority."""

from __future__ import annotations

import sqlite3
from collections import Counter
from typing import Any

from core.shared_intelligence.authority import require_shared_intelligence_tables
from core.shared_intelligence.model_registry import model_provider_registry_summary
from core.shared_intelligence.read_models import component_learning_health, learning_event_summary
from core.shared_intelligence.result_normalization import adapter_result_summary

NEGATIVE_STATUSES: frozenset[str] = frozenset({"failed", "blocked", "partial"})
POSITIVE_STATUSES: frozenset[str] = frozenset({"validated", "completed"})


def cross_model_learning_feedback(
    conn: sqlite3.Connection,
    *,
    project_id: str | None = None,
) -> dict[str, Any]:
    """Compare recorded results and learning signals without changing policy."""

    require_shared_intelligence_tables(conn)
    results = adapter_result_summary(conn, project_id=project_id, limit=100)
    learning = learning_event_summary(conn, project_id=project_id, limit=100)
    component_health = component_learning_health(conn, project_id=project_id)
    model_registry = model_provider_registry_summary(conn)

    recommendations = [
        *_adapter_recommendations(results["results"]),
        *_component_recommendations(component_health["components"]),
        *_model_profile_recommendations(model_registry["profiles"]),
    ]

    return {
        "model_name": "shared_intelligence_cross_model_learning_feedback",
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "policy_mutation_authorized": False,
        "source_tables": [
            "adapter_result_records",
            "learning_event_records",
            "hardening_candidate_records",
            "model_provider_profiles",
        ],
        "project_id": project_id,
        "adapter_result_summary": results,
        "learning_event_summary": learning,
        "component_learning_health": component_health,
        "model_provider_registry": model_registry,
        "recommendations": recommendations,
        "preferred_adapter_candidates": _preferred_adapter_candidates(results["results"]),
        "hardening_candidates": [
            recommendation
            for recommendation in recommendations
            if recommendation["action"].startswith("harden_")
        ],
        "empty_state": "No cross-model learning feedback is available from recorded facts.",
    }


def _adapter_recommendations(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_adapter: dict[str, Counter[str]] = {}
    for result in results:
        adapter_id = str(result["adapter_id"])
        by_adapter.setdefault(adapter_id, Counter())[str(result["normalized_status"])] += 1

    recommendations: list[dict[str, Any]] = []
    for adapter_id, statuses in sorted(by_adapter.items()):
        negative = sum(statuses[status] for status in NEGATIVE_STATUSES)
        positive = sum(statuses[status] for status in POSITIVE_STATUSES)
        if negative:
            recommendations.append(
                _recommendation(
                    action="harden_adapter",
                    target_type="adapter",
                    target_id=adapter_id,
                    reason=f"Adapter has {negative} non-green normalized result(s).",
                    risk_level="medium",
                )
            )
        elif positive:
            recommendations.append(
                _recommendation(
                    action="prefer_adapter_candidate",
                    target_type="adapter",
                    target_id=adapter_id,
                    reason=f"Adapter has {positive} green normalized result(s) and no non-green result in scope.",
                    risk_level="low",
                )
            )
    return recommendations


def _component_recommendations(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for component in components:
        if component["highest_severity"] in {"high", "critical"} or component["recurrence_keys"]:
            recommendations.append(
                _recommendation(
                    action=f"harden_{component['component_type']}",
                    target_type=str(component["component_type"]),
                    target_id=str(component["component_id"]),
                    reason="Component has high-severity or recurring learning events.",
                    risk_level="high" if component["highest_severity"] == "critical" else "medium",
                )
            )
    return recommendations


def _model_profile_recommendations(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for profile in profiles:
        if profile["failure_modes"]:
            recommendations.append(
                _recommendation(
                    action="review_model_profile",
                    target_type="model_profile",
                    target_id=str(profile["model_profile_id"]),
                    reason="Model profile has recorded failure modes.",
                    risk_level="low",
                )
            )
    return recommendations


def _preferred_adapter_candidates(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, Counter[str]] = {}
    for result in results:
        adapter_id = str(result["adapter_id"])
        counts.setdefault(adapter_id, Counter())[str(result["normalized_status"])] += 1
    preferred: list[dict[str, Any]] = []
    for adapter_id, statuses in sorted(counts.items()):
        negative = sum(statuses[status] for status in NEGATIVE_STATUSES)
        positive = sum(statuses[status] for status in POSITIVE_STATUSES)
        if positive and not negative:
            preferred.append(
                {
                    "adapter_id": adapter_id,
                    "green_result_count": positive,
                    "policy_mutation_authorized": False,
                    "requires_future_route_policy_work": True,
                }
            )
    return preferred


def _recommendation(
    *,
    action: str,
    target_type: str,
    target_id: str,
    reason: str,
    risk_level: str,
) -> dict[str, Any]:
    return {
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "reason": reason,
        "risk_level": risk_level,
        "requires_future_work_order": True,
        "policy_mutation_authorized": False,
        "execution_authorized": False,
    }
