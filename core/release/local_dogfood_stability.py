"""Long-run local dogfood stability evaluation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def evaluate_local_dogfood_stability(
    sessions: Sequence[Mapping[str, Any]],
    *,
    min_sessions: int = 2,
) -> dict[str, Any]:
    """Evaluate dogfood stability from structured session summaries."""

    issues: list[str] = []
    if len(sessions) < min_sessions:
        issues.append("insufficient_session_count")
    for index, session in enumerate(sessions):
        prefix = f"session_{index}"
        if _truthy(session.get("prompt_chaining_detected")):
            issues.append(f"{prefix}_prompt_chaining_detected")
        if _truthy(session.get("hidden_mutation_detected")):
            issues.append(f"{prefix}_hidden_mutation_detected")
        if _truthy(session.get("dashboard_authority_drift_detected")):
            issues.append(f"{prefix}_dashboard_authority_drift_detected")
        if _truthy(session.get("evidence_sprawl_detected")):
            issues.append(f"{prefix}_evidence_sprawl_detected")
        if not _truthy(session.get("validation_passed")):
            issues.append(f"{prefix}_validation_not_passed")
        if not session.get("evidence_refs"):
            issues.append(f"{prefix}_missing_evidence_refs")
    return {
        "evaluation": "local_dogfood_long_run_stability",
        "derived_view": True,
        "primary_authority": False,
        "session_count": len(sessions),
        "stable": not issues,
        "issues": issues,
        "summary": {
            "prompt_chaining_regressions": sum(
                1 for session in sessions if _truthy(session.get("prompt_chaining_detected"))
            ),
            "hidden_mutation_events": sum(
                1 for session in sessions if _truthy(session.get("hidden_mutation_detected"))
            ),
            "dashboard_authority_drift_events": sum(
                1
                for session in sessions
                if _truthy(session.get("dashboard_authority_drift_detected"))
            ),
            "evidence_sprawl_events": sum(
                1 for session in sessions if _truthy(session.get("evidence_sprawl_detected"))
            ),
            "validation_passed_count": sum(
                1 for session in sessions if _truthy(session.get("validation_passed"))
            ),
        },
    }


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "present", "passed"}
    return bool(value)
