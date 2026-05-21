"""Context budget tracking for skill executions.

Provides a pure-function layer for checking token budget status and building
skill.budget_exceeded event payloads. Does not emit events directly — callers
use CanonicalEventEnvelope with the returned payload.

Usage in skill execution loop (e.g. runner.py):

    from core.telemetry.context_budget import check_budget_status, build_budget_exceeded_payload

    status = check_budget_status(tokens_used=used, budget_limit=limit)
    if status["exceeded"]:
        payload = build_budget_exceeded_payload(
            skill_id=skill_id,
            work_order_id=wo_id,
            tokens_used=used,
            budget_limit=limit,
        )
        # emit via CanonicalEventEnvelope(event_type="skill.budget_exceeded", payload=payload, ...)
"""

from __future__ import annotations

from typing import Any

DEFAULT_BUDGET_LIMIT = 100_000
DEFAULT_WARNING_THRESHOLD = 0.80


def check_budget_status(
    *,
    tokens_used: int,
    budget_limit: int,
    warning_threshold: float = DEFAULT_WARNING_THRESHOLD,
) -> dict[str, Any]:
    """Return budget status for a skill execution.

    Returns::

        {
            "tokens_used": int,
            "budget_limit": int,
            "utilization": float,      # 0.0–1.0+ (> 1.0 when exceeded)
            "exceeded": bool,
            "warning": bool,           # True when >= threshold but not yet exceeded
            "status": "ok" | "warning" | "exceeded",
        }
    """
    if budget_limit <= 0:
        utilization = 1.0
        exceeded = True
    else:
        utilization = tokens_used / budget_limit
        exceeded = tokens_used > budget_limit

    warning = (not exceeded) and (utilization >= warning_threshold)
    if exceeded:
        status = "exceeded"
    elif warning:
        status = "warning"
    else:
        status = "ok"

    return {
        "tokens_used": tokens_used,
        "budget_limit": budget_limit,
        "utilization": round(utilization, 4),
        "exceeded": exceeded,
        "warning": warning,
        "status": status,
    }


def build_budget_exceeded_payload(
    *,
    skill_id: str,
    work_order_id: str | None,
    tokens_used: int,
    budget_limit: int,
) -> dict[str, Any]:
    """Build the event payload for a skill.budget_exceeded event.

    Returns a dict suitable for use as the ``payload`` argument of
    ``CanonicalEventEnvelope``.
    """
    return {
        "skill_id": skill_id,
        "work_order_id": work_order_id,
        "tokens_used": tokens_used,
        "budget_limit": budget_limit,
        "overage": max(0, tokens_used - budget_limit),
    }
