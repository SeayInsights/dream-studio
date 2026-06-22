"""Event criticality system.

Defines which events must succeed (CRITICAL), which should warn on failure
(IMPORTANT), and which can fail silently (OPTIONAL).

Created: 2026-05-07 (Phase 1 - Event System Improvements)
"""

from enum import Enum
from typing import Set


class EventCriticality(Enum):
    """Event criticality levels determine failure handling behavior."""

    OPTIONAL = "optional"  # Can fail silently (logs, telemetry, metrics)
    IMPORTANT = "important"  # Should fail loudly but not block execution
    CRITICAL = "critical"  # Must succeed or raise exception


# Define which event types are critical
# These events MUST be persisted or execution should stop
CRITICAL_EVENT_TYPES: Set[str] = {
    "execution.started",
    "execution.completed",
    "execution.failed",
    "workflow.started",
    "workflow.completed",
    "workflow.failed",
    "decision.made",
    "decision.reverted",
    "prd.created",
    "prd.updated",
    "plan.created",
    "plan.updated",
    "plan.activated",
    "plan.completed",
}


# Important events should log errors but not block
IMPORTANT_EVENT_TYPES: Set[str] = {
    "task.started",
    "task.completed",
    "task.failed",
    "skill.activated",
    "agent.spawned",
    "phase.started",
    "phase.completed",
    "phase.failed",
    "wave.started",
    "wave.completed",
    "wave.failed",
}


def get_criticality(event_type: str) -> EventCriticality:
    """
    Determine criticality level of an event type.

    Args:
        event_type: Event type string (e.g., 'execution.started')

    Returns:
        EventCriticality: Criticality level for this event type

    Example:
        criticality = get_criticality('execution.started')
        # Returns EventCriticality.CRITICAL

        criticality = get_criticality('telemetry.recorded')
        # Returns EventCriticality.OPTIONAL
    """
    if event_type in CRITICAL_EVENT_TYPES:
        return EventCriticality.CRITICAL
    if event_type in IMPORTANT_EVENT_TYPES:
        return EventCriticality.IMPORTANT
    return EventCriticality.OPTIONAL


def is_critical(event_type: str) -> bool:
    """Check if an event type is critical."""
    return event_type in CRITICAL_EVENT_TYPES


def is_important(event_type: str) -> bool:
    """Check if an event type is important."""
    return event_type in IMPORTANT_EVENT_TYPES
