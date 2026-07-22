"""Project health-model derivation.

WO-GF-API-ROUTES: split out of project_helpers.py.
"""

from __future__ import annotations

from typing import Any

from .project_helpers_utils import _as_int

# ── Health model ─────────────────────────────────────────────────────────────


def _build_health_model(project: dict[str, Any]) -> dict[str, Any]:
    """Derive dashboard health from current evidence instead of stored legacy scores."""

    signals = {
        "path_confirmed": project.get("path_status") == "confirmed",
        "prd_count": _as_int(project.get("prd_count")),
        "security_open_count": _as_int(project.get("security_open_count")),
        "validation_failed_count": _as_int(project.get("validation_failed_count")),
        "validation_passed_count": _as_int(project.get("validation_passed_count")),
        "attention_open_count": _as_int(project.get("attention_open_count")),
        "route_blocker_count": _as_int(project.get("route_blocker_count")),
        "telemetry_event_count": _as_int(project.get("telemetry_event_count")),
        "dependency_count": _as_int(project.get("dependency_count")),
        "security_lifecycle_manual_review_count": _as_int(
            project.get("security_lifecycle_manual_review_count")
        ),
        "security_lifecycle_unknown_count": _as_int(
            project.get("security_lifecycle_unknown_count")
        ),
    }
    evidence_points = sum(
        1
        for value in (
            signals["prd_count"],
            signals["security_open_count"],
            signals["validation_failed_count"],
            signals["validation_passed_count"],
            signals["attention_open_count"],
            signals["route_blocker_count"],
            signals["telemetry_event_count"],
            signals["dependency_count"],
            signals["security_lifecycle_manual_review_count"],
            signals["security_lifecycle_unknown_count"],
        )
        if value > 0
    )
    if not signals["path_confirmed"] and evidence_points == 0:
        return {
            "status": "unavailable",
            "score": None,
            "label": "Health unavailable",
            "reason": "Project path is unverified and there are no current telemetry, PRD, security, validation, attention, or dependency signals.",
            "signals": signals,
            "derived_view": True,
            "primary_authority": False,
        }

    score = 100
    penalties: list[str] = []
    if not signals["path_confirmed"]:
        score -= 30
        penalties.append("project path is not confirmed")
    if signals["security_open_count"]:
        penalty = min(35, signals["security_open_count"] * 8)
        score -= penalty
        penalties.append(f"{signals['security_open_count']} open security finding(s)")
    if signals["validation_failed_count"]:
        penalty = min(25, signals["validation_failed_count"] * 10)
        score -= penalty
        penalties.append(f"{signals['validation_failed_count']} failed/incomplete validation(s)")
    if signals["attention_open_count"]:
        penalty = min(20, signals["attention_open_count"] * 4)
        score -= penalty
        penalties.append(f"{signals['attention_open_count']} open attention item(s)")
    if signals["route_blocker_count"]:
        penalty = min(20, signals["route_blocker_count"] * 8)
        score -= penalty
        penalties.append(f"{signals['route_blocker_count']} route blocker/approval item(s)")
    if signals["prd_count"] == 0:
        score -= 5
        penalties.append("no PRD authority linked")
    if signals["dependency_count"] == 0:
        score -= 5
        penalties.append("no confirmed dependency evidence")
    if signals["security_lifecycle_manual_review_count"]:
        penalty = min(20, signals["security_lifecycle_manual_review_count"] * 4)
        score -= penalty
        penalties.append(
            f"{signals['security_lifecycle_manual_review_count']} security lifecycle manual review control(s)"
        )
    if signals["security_lifecycle_unknown_count"]:
        penalty = min(30, signals["security_lifecycle_unknown_count"] * 10)
        score -= penalty
        penalties.append(
            f"{signals['security_lifecycle_unknown_count']} unknown security lifecycle control(s)"
        )

    score = max(0, min(100, score))
    if score >= 85:
        label = "Healthy"
    elif score >= 65:
        label = "Watch"
    elif score >= 40:
        label = "At risk"
    else:
        label = "Needs attention"
    return {
        "status": "scored",
        "score": score,
        "label": label,
        "reason": "; ".join(penalties) if penalties else "Current evidence has no active blockers.",
        "signals": signals,
        "derived_view": True,
        "primary_authority": False,
    }
