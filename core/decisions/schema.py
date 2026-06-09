"""Decision schema for system-wide decision transparency."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any


@dataclass
class Decision:
    """Canonical decision object for structured reasoning metadata.

    All subsystems that make meaningful decisions must emit Decision objects
    with structured reasoning, enabling audit trails and explainability.
    """

    decision_id: str  # UUID
    decision_type: str  # e.g., "trust_score", "ttl_assignment", "unlock_pattern"
    context: dict  # Input that led to decision
    outcome: Any  # The actual decision made
    reasoning: dict  # Structured explanation
    confidence: float  # 0.0-1.0
    policy_applied: str  # Policy name/version
    timestamp: str  # ISO8601
    source_subsystem: str  # e.g., "research_engine", "skill_router"
