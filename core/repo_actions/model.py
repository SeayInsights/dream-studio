"""Repository action model and data structures."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class ActionType(Enum):
    """Allowed action types (strict enum)."""

    REFACTOR = "refactor"
    EXTRACT = "extract"
    FIX = "fix"
    INSTRUMENT = "instrument"
    DELETE = "delete"
    CONSOLIDATE = "consolidate"


class RiskLevel(Enum):
    """Risk levels for actions."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EffortEstimate(Enum):
    """Effort estimates."""

    SMALL = "S"  # < 1 week
    MEDIUM = "M"  # 1-3 weeks
    LARGE = "L"  # > 3 weeks


@dataclass
class SupportingSignal:
    """A signal supporting an action from existing system."""

    signal_type: str  # "decision" | "event" | "coverage" | "coupling" | "capability"
    signal_id: str  # ID or identifier
    description: str
    relevance: float  # 0.0-1.0


@dataclass
class RepoAction:
    """An actionable engineering task derived from system analysis."""

    action_id: str
    repo: str
    target: str  # file / module / subsystem
    action_type: ActionType
    priority_score: float  # 0.0 - 1.0
    rationale: Dict[str, any]  # MUST reference existing system outputs
    supporting_signals: List[SupportingSignal] = field(default_factory=list)
    estimated_effort: EffortEstimate = EffortEstimate.MEDIUM
    risk_level: RiskLevel = RiskLevel.MEDIUM
    expected_impact: str = ""

    # Traceability requirements
    decision_ids: List[str] = field(default_factory=list)
    event_ids: List[str] = field(default_factory=list)
    coverage_finding_ids: List[str] = field(default_factory=list)
    capability_ids: List[str] = field(default_factory=list)

    def is_traceable(self) -> bool:
        """Check if action is traceable to existing system output.

        Returns:
            True if traceable to at least one system output
        """
        return bool(
            self.decision_ids or self.event_ids or self.coverage_finding_ids or self.capability_ids
        )


@dataclass
class RepoActionPlan:
    """Complete action plan for a repository."""

    repo_name: str
    actions: List[RepoAction] = field(default_factory=list)
    total_estimated_effort: str = ""
    high_priority_count: int = 0
    subsystem_grouping: Dict[str, List[RepoAction]] = field(default_factory=dict)


@dataclass
class SystemPriorityMap:
    """System-wide prioritization across all repositories."""

    top_actions: List[RepoAction] = field(default_factory=list)
    by_capability_domain: Dict[str, List[RepoAction]] = field(default_factory=dict)
    dependency_ordered_actions: List[RepoAction] = field(default_factory=list)
