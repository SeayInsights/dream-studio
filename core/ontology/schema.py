"""Canonical ontology — typed entity and relationship definitions.

This module is the authoritative semantic layer for Dream Studio. All systems
(events, projections, memory, workflows, analytics) reference these types
instead of using ad-hoc string constants.

Entities have lifecycle states, relationships have cardinality constraints,
and artifacts have classification types. These replace the implicit ontology
previously scattered across 72 database tables and 40+ event types.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, FrozenSet, List, Optional, Set

# ============================================================================
# ENTITY TYPES — canonical things that exist in the system
# ============================================================================


class EntityType(str, Enum):
    PROJECT = "project"
    SESSION = "session"
    WORKFLOW = "workflow"
    WORKFLOW_NODE = "workflow_node"
    SKILL = "skill"
    SKILL_MODE = "skill_mode"
    EVENT = "event"
    DECISION = "decision"
    MEMORY = "memory"
    LESSON = "lesson"
    GOTCHA = "gotcha"
    PATTERN = "pattern"
    SCAN = "scan"
    FINDING = "finding"
    ARTIFACT = "artifact"
    AGENT = "agent"
    POLICY = "policy"
    TRACE = "trace"


# ============================================================================
# LIFECYCLE STATES — DEPRECATED: use core.ontology.lifecycles instead
#
# Domain-specific lifecycle enums (MemoryLifecycle, ExecutionLifecycle,
# DocumentLifecycle) in core/ontology/lifecycles.py replace this generic enum.
# Kept here temporarily for backward compatibility.
# ============================================================================


class LifecycleState(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"
    DEPRECATED = "deprecated"


# DEPRECATED: use LIFECYCLE_CATALOG from core.ontology.lifecycles instead.
ENTITY_LIFECYCLES: Dict[EntityType, List[LifecycleState]] = {
    EntityType.PROJECT: [
        LifecycleState.CREATED,
        LifecycleState.ACTIVE,
        LifecycleState.ARCHIVED,
    ],
    EntityType.SESSION: [
        LifecycleState.CREATED,
        LifecycleState.ACTIVE,
        LifecycleState.COMPLETED,
    ],
    EntityType.WORKFLOW: [
        LifecycleState.CREATED,
        LifecycleState.RUNNING,
        LifecycleState.PAUSED,
        LifecycleState.COMPLETED,
        LifecycleState.FAILED,
    ],
    EntityType.WORKFLOW_NODE: [
        LifecycleState.CREATED,
        LifecycleState.RUNNING,
        LifecycleState.COMPLETED,
        LifecycleState.FAILED,
    ],
    EntityType.SKILL: [
        LifecycleState.ACTIVE,
        LifecycleState.DEPRECATED,
    ],
    EntityType.FINDING: [
        LifecycleState.CREATED,
        LifecycleState.ACTIVE,
        LifecycleState.COMPLETED,
        LifecycleState.ARCHIVED,
    ],
    EntityType.MEMORY: [
        LifecycleState.ACTIVE,
        LifecycleState.ARCHIVED,
    ],
}


# ============================================================================
# RELATIONSHIP TYPES — how entities connect
# ============================================================================


class RelationType(str, Enum):
    CONTAINS = "contains"  # project contains sessions
    BELONGS_TO = "belongs_to"  # session belongs to project
    TRIGGERS = "triggers"  # event triggers workflow
    PRODUCES = "produces"  # workflow produces artifact
    DEPENDS_ON = "depends_on"  # node depends on node
    CAUSED_BY = "caused_by"  # decision caused by event
    APPLIED_TO = "applied_to"  # policy applied to skill
    DETECTED_IN = "detected_in"  # finding detected in scan
    LEARNED_FROM = "learned_from"  # lesson learned from session
    REFERENCES = "references"  # memory references event
    CORRECTS = "corrects"  # correction corrects decision
    SUPERSEDES = "supersedes"  # newer version supersedes older


@dataclass(frozen=True)
class RelationshipSpec:
    relation_type: RelationType
    source_type: EntityType
    target_type: EntityType
    cardinality: str  # "1:1", "1:N", "N:1", "N:M"


CANONICAL_RELATIONSHIPS: List[RelationshipSpec] = [
    RelationshipSpec(RelationType.CONTAINS, EntityType.PROJECT, EntityType.SESSION, "1:N"),
    RelationshipSpec(RelationType.CONTAINS, EntityType.SESSION, EntityType.EVENT, "1:N"),
    RelationshipSpec(RelationType.CONTAINS, EntityType.WORKFLOW, EntityType.WORKFLOW_NODE, "1:N"),
    RelationshipSpec(RelationType.TRIGGERS, EntityType.EVENT, EntityType.WORKFLOW, "N:1"),
    RelationshipSpec(RelationType.PRODUCES, EntityType.WORKFLOW, EntityType.ARTIFACT, "1:N"),
    RelationshipSpec(
        RelationType.DEPENDS_ON, EntityType.WORKFLOW_NODE, EntityType.WORKFLOW_NODE, "N:M"
    ),
    RelationshipSpec(RelationType.CAUSED_BY, EntityType.DECISION, EntityType.EVENT, "N:1"),
    RelationshipSpec(RelationType.APPLIED_TO, EntityType.POLICY, EntityType.SKILL, "N:M"),
    RelationshipSpec(RelationType.DETECTED_IN, EntityType.FINDING, EntityType.SCAN, "N:1"),
    RelationshipSpec(RelationType.LEARNED_FROM, EntityType.LESSON, EntityType.SESSION, "N:1"),
    RelationshipSpec(RelationType.REFERENCES, EntityType.MEMORY, EntityType.EVENT, "N:M"),
    RelationshipSpec(RelationType.CORRECTS, EntityType.DECISION, EntityType.DECISION, "N:1"),
]


# ============================================================================
# ARTIFACT CLASSIFICATION — types of things the system produces
# ============================================================================


class ArtifactType(str, Enum):
    CODE = "code"
    DOCUMENTATION = "documentation"
    CONFIGURATION = "configuration"
    REPORT = "report"
    PLAN = "plan"
    PRD = "prd"
    DASHBOARD = "dashboard"
    EXPORT = "export"
    SCAN_RESULT = "scan_result"
    MIGRATION = "migration"


# ============================================================================
# EVENT SEMANTIC CATEGORIES
# ============================================================================


class EventCategory(str, Enum):
    LIFECYCLE = "lifecycle"  # entity created/updated/deleted
    EXECUTION = "execution"  # workflow/skill execution
    ANALYSIS = "analysis"  # code analysis, security scanning
    DECISION = "decision"  # routing decisions, policy application
    TELEMETRY = "telemetry"  # token usage, performance metrics
    SYSTEM = "system"  # health, validation, infrastructure


EVENT_TYPE_CATEGORIES: Dict[str, EventCategory] = {
    "session.": EventCategory.LIFECYCLE,
    "project.": EventCategory.LIFECYCLE,
    "workflow.": EventCategory.EXECUTION,
    "skill.": EventCategory.EXECUTION,
    "analysis.": EventCategory.ANALYSIS,
    "security.": EventCategory.ANALYSIS,
    "decision.": EventCategory.DECISION,
    "token.": EventCategory.TELEMETRY,
    "hook.": EventCategory.SYSTEM,
    "event.validation": EventCategory.SYSTEM,
}


def classify_event(event_type: str) -> EventCategory:
    """Classify an event type into its semantic category."""
    for prefix, category in EVENT_TYPE_CATEGORIES.items():
        if event_type.startswith(prefix):
            return category
    return EventCategory.SYSTEM


# ============================================================================
# SKILL TAXONOMY
# ============================================================================


@dataclass(frozen=True)
class SkillSpec:
    pack: str
    skill: str
    modes: FrozenSet[str]
    domain: str  # "core", "quality", "security", "analysis", "career", "domain"


SKILL_TAXONOMY: List[SkillSpec] = [
    SkillSpec(
        "core",
        "ds-core",
        frozenset(
            {"think", "plan", "build", "review", "verify", "ship", "handoff", "recap", "explain"}
        ),
        "core",
    ),
    SkillSpec(
        "quality",
        "ds-quality",
        frozenset({"debug", "polish", "harden", "secure", "structure-audit", "learn", "coach"}),
        "quality",
    ),
    SkillSpec(
        "security",
        "ds-security",
        frozenset({"scan", "dast", "binary-scan", "mitigate", "comply", "netcompat", "dashboard"}),
        "security",
    ),
    SkillSpec("analyze", "ds-analyze", frozenset({"multi", "domain-re", "repo"}), "analysis"),
    SkillSpec(
        "career",
        "ds-career",
        frozenset({"ops", "scan", "evaluate", "apply", "track", "pdf"}),
        "career",
    ),
    SkillSpec(
        "domains",
        "ds-domains",
        frozenset(
            {
                "game-dev",
                "saas-build",
                "mcp-build",
                "dashboard-dev",
                "client-work",
                "design",
                "website",
                "fullstack",
            }
        ),
        "domain",
    ),
]


def get_skill_spec(pack_or_skill: str) -> Optional[SkillSpec]:
    for spec in SKILL_TAXONOMY:
        if spec.pack == pack_or_skill or spec.skill == pack_or_skill:
            return spec
    return None


def validate_mode(pack: str, mode: str) -> bool:
    spec = get_skill_spec(pack)
    return spec is not None and mode in spec.modes
