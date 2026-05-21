from __future__ import annotations
from dataclasses import dataclass
from enum import Enum


class EventCategory(str, Enum):
    HOOK_EMITTED = "hook_emitted"
    PRODUCTION_EMITTED = "production_emitted"
    RESERVED = "reserved"


class EventType(str, Enum):
    # Hook-emitted types (14 existing)
    SESSION_LIFECYCLE_STARTED = "session.lifecycle.started"
    SESSION_LIFECYCLE_ENDED = "session.lifecycle.ended"
    PROMPT_LIFECYCLE_SUBMITTED = "prompt.lifecycle.submitted"
    PROMPT_LIFECYCLE_VALIDATED = "prompt.lifecycle.validated"
    TOOL_EXECUTION_STARTED = "tool.execution.started"
    TOOL_EXECUTION_COMPLETED = "tool.execution.completed"
    TOKEN_CONSUMPTION_RECORDED = "token.consumption.recorded"
    SKILL_LIFECYCLE_LOADED = "skill.lifecycle.loaded"
    SKILL_LIFECYCLE_COMPLETED = "skill.lifecycle.completed"
    WORKFLOW_PROGRESS_UPDATED = "workflow.progress.updated"
    CONTEXT_THRESHOLD_CROSSED = "context.threshold.crossed"
    SECURITY_SCAN_COMPLETED = "security.scan.completed"
    QUALITY_SCORE_RECORDED = "quality.score.recorded"
    INTEGRATION_HEALTH_CHANGED = "integration.health.changed"

    # Production-emitted types (migrated from core/events/types.py)
    GUARDRAIL_DECISION = "guardrail.decision"
    RESEARCH_VALIDATED = "research.validated"
    RESEARCH_COMPLETED = "research.completed"
    RESEARCH_CACHE_STORED = "research.cache_stored"
    RESEARCH_CACHE_CLEARED = "research.cache_cleared"
    PROJECT_REGISTERED = "project.registered"
    PROJECT_UPDATED = "project.updated"
    ANALYSIS_STARTED = "analysis.started"
    ANALYSIS_DISCOVERY_COMPLETED = "analysis.discovery_completed"
    ANALYSIS_RESEARCH_COMPLETED = "analysis.research_completed"
    ANALYSIS_AUDIT_COMPLETED = "analysis.audit_completed"
    ANALYSIS_BUG_ANALYSIS_COMPLETED = "analysis.bug_analysis_completed"
    ANALYSIS_SYNTHESIS_COMPLETED = "analysis.synthesis_completed"
    ANALYSIS_COMPLETED = "analysis.completed"
    ANALYSIS_FAILED = "analysis.failed"
    AUDIT_VIOLATIONS_CLEARED = "audit.violations_cleared"
    AUDIT_VIOLATION_FOUND = "audit.violation_found"
    AUDIT_IMPROVEMENTS_CLEARED = "audit.improvements_cleared"
    AUDIT_IMPROVEMENT_FOUND = "audit.improvement_found"
    REPO_ANALYZED = "repo.analyzed"
    REPO_EXTRACTION_STORED = "repo.extraction.stored"
    EXECUTION_COMPLETE = "execution.complete"
    TESTS_EXECUTED = "execution.tests_executed"
    WAVE_STARTED = "wave.started"
    WAVE_COMPLETED = "wave.completed"
    WAVE_FAILED = "wave.failed"
    WAVE_TASK_UPDATED = "wave.task_updated"
    WORKFLOW_LEARNED = "workflow.learned"
    DOCUMENT_CREATED = "document.created"
    DOCUMENT_UPDATED = "document.updated"
    DOCUMENT_ARCHIVED = "document.archived"

    # Workflow execution events (emitted by runner.py)
    WORKFLOW_NODE_COMPLETED = "workflow.node.completed"

    # CLI lifecycle events (emitted by interfaces/cli/ds.py)
    WORK_ORDER_STARTED = "work_order.started"
    WORK_ORDER_CLOSED = "work_order.closed"
    WORK_ORDER_BLOCKED = "work_order.blocked"
    GATE_BYPASSED = "gate.bypassed"
    TASK_COMPLETED = "task.completed"
    MILESTONE_COMPLETED = "milestone.completed"
    SKILL_INVOKED = "skill.invoked"

    # Skill execution telemetry
    SKILL_BUDGET_EXCEEDED = "skill.budget_exceeded"


@dataclass(frozen=True)
class EventTypeMeta:
    event_type: EventType
    domain: str
    description: str
    emitter_implemented: bool
    category: EventCategory


EVENT_TYPE_REGISTRY: tuple[EventTypeMeta, ...] = (
    # Hook-emitted types
    EventTypeMeta(
        EventType.SESSION_LIFECYCLE_STARTED,
        "session",
        "Host AI session begun; session_id established",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.SESSION_LIFECYCLE_ENDED,
        "session",
        "Host AI session ended normally",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROMPT_LIFECYCLE_SUBMITTED,
        "prompt",
        "User submitted a prompt (redacted: no raw text)",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROMPT_LIFECYCLE_VALIDATED,
        "prompt",
        "Prompt passed DS validation gates",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.TOOL_EXECUTION_STARTED,
        "tool",
        "A tool call began (tool name + args shape; no raw output)",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.TOOL_EXECUTION_COMPLETED,
        "tool",
        "A tool call completed (result shape; no raw output)",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.TOKEN_CONSUMPTION_RECORDED,
        "token",
        "Token count for a session turn",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.SKILL_LIFECYCLE_LOADED,
        "skill",
        "A DS skill was activated for this session",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.SKILL_LIFECYCLE_COMPLETED,
        "skill",
        "A DS skill's primary action completed",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORKFLOW_PROGRESS_UPDATED,
        "workflow",
        "A workflow milestone progressed",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.CONTEXT_THRESHOLD_CROSSED,
        "context",
        "Context window crossed a configured threshold",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.SECURITY_SCAN_COMPLETED,
        "security",
        "Security scan ran against a file or diff",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.QUALITY_SCORE_RECORDED,
        "quality",
        "Quality score computed for an artifact",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.INTEGRATION_HEALTH_CHANGED,
        "integration",
        "An integration health state transition occurred",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    # Production-emitted types
    EventTypeMeta(
        EventType.GUARDRAIL_DECISION,
        "guardrail",
        "Guardrail policy decision logged for compliance audit",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.RESEARCH_VALIDATED,
        "research",
        "Research result validated by session outcome",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.RESEARCH_COMPLETED,
        "research",
        "Research query completed and result stored",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.RESEARCH_CACHE_STORED,
        "research",
        "Research result stored in cache",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.RESEARCH_CACHE_CLEARED,
        "research",
        "Research cache entry cleared for topic",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROJECT_REGISTERED,
        "project",
        "Project registered in the analysis registry",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROJECT_UPDATED,
        "project",
        "Project metadata updated in registry",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_STARTED,
        "analysis",
        "Project analysis pipeline started",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_DISCOVERY_COMPLETED,
        "analysis",
        "Discovery phase of analysis completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_RESEARCH_COMPLETED,
        "analysis",
        "Research phase of analysis completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_AUDIT_COMPLETED,
        "analysis",
        "Audit phase of analysis completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_BUG_ANALYSIS_COMPLETED,
        "analysis",
        "Bug analysis phase completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_SYNTHESIS_COMPLETED,
        "analysis",
        "Synthesis phase of analysis completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_COMPLETED,
        "analysis",
        "Full project analysis pipeline completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_FAILED,
        "analysis",
        "Project analysis pipeline failed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.AUDIT_VIOLATIONS_CLEARED,
        "audit",
        "Audit violations cleared before new scan",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.AUDIT_VIOLATION_FOUND,
        "audit",
        "Architecture violation detected during audit",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.AUDIT_IMPROVEMENTS_CLEARED,
        "audit",
        "Audit improvements cleared before new scan",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.AUDIT_IMPROVEMENT_FOUND,
        "audit",
        "Architecture improvement opportunity detected",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.REPO_ANALYZED,
        "repo",
        "External repository analysis completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.REPO_EXTRACTION_STORED,
        "repo",
        "Repository pattern extraction stored",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.EXECUTION_COMPLETE,
        "execution",
        "GitHub PR execution completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.TESTS_EXECUTED,
        "execution",
        "Test suite executed and results collected",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WAVE_STARTED,
        "wave",
        "Execution wave started",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WAVE_COMPLETED,
        "wave",
        "Execution wave completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WAVE_FAILED,
        "wave",
        "Execution wave failed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WAVE_TASK_UPDATED,
        "wave",
        "Wave task status updated",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORKFLOW_LEARNED,
        "workflow",
        "Workflow pattern learned from execution history",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.DOCUMENT_CREATED,
        "document",
        "Document created in document store",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.DOCUMENT_UPDATED,
        "document",
        "Document updated in document store",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.DOCUMENT_ARCHIVED,
        "document",
        "Document archived in document store",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    # CLI lifecycle events
    EventTypeMeta(
        EventType.WORK_ORDER_STARTED,
        "work_order",
        "Work order entered in_progress state",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORK_ORDER_CLOSED,
        "work_order",
        "Work order closed after gate checks passed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORK_ORDER_BLOCKED,
        "work_order",
        "Work order blocked with a stated reason",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.GATE_BYPASSED,
        "gate",
        "A gate check was bypassed with --force",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.TASK_COMPLETED,
        "task",
        "A task within a work order was marked complete",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.MILESTONE_COMPLETED,
        "milestone",
        "A milestone was closed after verification",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.SKILL_INVOKED,
        "skill",
        "A Dream Studio skill was invoked via CLI",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORKFLOW_NODE_COMPLETED,
        "workflow",
        "A workflow DAG node completed execution",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
)

# Backward-compatible: hook-emitted types that are implemented in the emitter
EMITTER_IMPLEMENTED: frozenset[EventType] = frozenset(
    m.event_type
    for m in EVENT_TYPE_REGISTRY
    if m.category == EventCategory.HOOK_EMITTED and m.emitter_implemented
)

ALL_EVENT_TYPES: frozenset[str] = frozenset(t.value for t in EventType)
