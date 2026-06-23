"""Guardrail data models for rule definitions and decisions.

Guardrails are gatekeepers — they enforce policy BEFORE or DURING execution.
They are deterministic (same input = same output) and YAML-driven.
"""

from __future__ import annotations

from datetime import datetime, UTC
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class GuardrailAction(str, Enum):
    """Action a guardrail can take."""

    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_APPROVAL = "require_approval"
    ADVISORY = "advisory"  # Pilot mode: print warning but don't block


class Severity(str, Enum):
    """Severity level for findings."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TriggerCondition(BaseModel):
    """Defines when a guardrail rule should evaluate.

    Named fields map to the legacy-compatible activity_log schema:
    event_type -> activity_type, finding_type -> event_data.finding_type,
    severity -> severity, tool_name -> stream metadata, event_id -> activity_id.

    Examples:
    - event_type: "hook_finding.created"
    - finding_type: "hardcoded credential"
    - severity: "critical"
    """

    event_type: str | None = None
    finding_type: str | None = None
    severity: Severity | None = None
    tool_name: str | None = None
    file_pattern: str | None = None  # Regex pattern
    custom_query: str | None = None  # SQL query against activity_log


class GuardrailRule(BaseModel):
    """A single guardrail rule definition.

    Rules are loaded from YAML files in guardrails/rules/*.yaml
    """

    rule_id: str = Field(..., description="Unique rule ID (e.g., GR-001)")
    name: str = Field(..., description="Human-readable name")
    description: str | None = Field(None, description="What this rule enforces")
    trigger: TriggerCondition = Field(..., description="When to evaluate this rule")
    action: GuardrailAction = Field(..., description="What to do if triggered")
    message: str = Field(..., description="Message to show user when triggered")
    severity: Severity = Field(default=Severity.MEDIUM, description="Rule severity")
    enabled: bool = Field(default=True, description="Whether rule is active")
    metadata: dict[str, Any] | None = Field(None, description="Additional context")


class GuardrailDecision(BaseModel):
    """Record of a guardrail evaluation decision.

    Logged to guardrail_decisions table for audit trail.
    """

    decision_id: str | None = None  # Auto-generated UUID
    rule_id: str = Field(..., description="Which rule was evaluated")
    event_id: str | None = Field(None, description="Activity log event that triggered evaluation")
    action: GuardrailAction = Field(..., description="Decision made")
    message: str = Field(..., description="Message shown to user")
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="When evaluation happened"
    )
    metadata: dict[str, Any] | None = Field(
        None, description="Additional context (matched patterns, etc.)"
    )


class RuleLoadError(Exception):
    """Raised when rule YAML is malformed or invalid."""


class EvaluationError(Exception):
    """Raised when rule evaluation fails."""
