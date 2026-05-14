"""Dashboard maturity gate for replacing prompt-based human-loop interaction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REQUIRED_SURFACES = (
    "approvals",
    "blockers",
    "attention_items",
    "operator_decisions",
    "route_state",
    "evidence_refs",
)


def evaluate_dashboard_human_loop_gate(dashboard_state: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate whether the dashboard can be the primary human-loop surface."""

    surfaces = _mapping(dashboard_state.get("surfaces"))
    missing = [surface for surface in REQUIRED_SURFACES if not _truthy(surfaces.get(surface))]
    authority_ok = (
        _truthy(dashboard_state.get("derived_view"))
        and not _truthy(dashboard_state.get("primary_authority"))
        and not _truthy(dashboard_state.get("routing_authority"))
    )
    stale = _truthy(dashboard_state.get("stale"))
    fatal_errors = _sequence_text(dashboard_state.get("fatal_errors"))
    passed = not missing and authority_ok and not stale and not fatal_errors
    return {
        "gate": "dashboard_as_human_loop",
        "passed": passed,
        "derived_view": True,
        "primary_authority": False,
        "missing_surfaces": missing,
        "authority_ok": authority_ok,
        "stale": stale,
        "fatal_errors": fatal_errors,
        "decision": "dashboard_primary_human_loop_ready" if passed else "keep_prompt_fallback",
        "prompt_fallback_required": not passed,
    }


def validate_dashboard_human_loop_gate(gate: Mapping[str, Any]) -> list[str]:
    """Return inconsistencies in a dashboard human-loop gate result."""

    issues: list[str] = []
    if gate.get("passed") and gate.get("missing_surfaces"):
        issues.append("passed_gate_has_missing_surfaces")
    if gate.get("passed") and not gate.get("authority_ok"):
        issues.append("passed_gate_without_authority_ok")
    if gate.get("passed") and gate.get("prompt_fallback_required"):
        issues.append("passed_gate_requires_prompt_fallback")
    return issues


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, Sequence):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "present"}
    return bool(value)
