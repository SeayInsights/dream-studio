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
    PROJECT_REGISTERED = (
        "project.registered"  # DEPRECATED — no callers; superseded by project.created
    )
    PROJECT_UPDATED = (
        "project.updated"  # DEPRECATED — no callers; superseded by project.activated/deactivated
    )
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

    # Pre-push gate failure (B.4)
    GATE_PRE_PUSH_FAILED = "gate.pre_push.failed"

    # Execution lifecycle telemetry (TA0b)
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    EXECUTION_FAILED = "execution.failed"

    # SDLC entity creation events (TA0)
    PROJECT_CREATED = "project.created"
    PROJECT_DELETED = "project.deleted"
    PROJECT_ACTIVATED = "project.activated"
    PROJECT_DEACTIVATED = "project.deactivated"
    MILESTONE_CREATED = "milestone.created"
    MILESTONE_DELETED = "milestone.deleted"
    WORK_ORDER_CREATED = "work_order.created"
    WORK_ORDER_DELETED = "work_order.deleted"

    # Task lifecycle events (TA1)
    TASK_CREATED = "task.created"
    TASK_STARTED = "task.started"
    TASK_DELETED = "task.deleted"

    # Design brief lifecycle events (18.2.4)
    DESIGN_BRIEF_CREATED = "design_brief.created"
    DESIGN_BRIEF_UPDATED = "design_brief.updated"
    DESIGN_BRIEF_LOCKED = "design_brief.locked"
    DESIGN_BRIEF_DELETED = "design_brief.deleted"

    # Token attribution events (TA3)
    TOKEN_CONSUMED = "token.consumed"

    # Activity-log retirement (TA0c) — operational telemetry migrated from legacy store
    WORKFLOW_COMPLETED = "workflow.completed"
    LESSON_CAPTURED = "system.lesson.captured"
    SKILL_EXECUTED = "skill.executed"
    RISK_SCORE_COMPUTED = "risk.score.computed"
    SECURITY_FINDING_RECORDED = "security.finding.recorded"
    SECURITY_FINDING_LOGGED = "security.finding.logged"
    SECURITY_FINDING_RESOLVED = "security.finding.resolved"
    APPROACH_CAPTURED = "system.approach.captured"
    PROJECT_STATS_UPDATED = "system.project_stats.updated"
    SESSION_RECORDED = "system.session.recorded"
    SESSION_CLOSED = "system.session.closed"
    HANDOFF_CREATED = "system.handoff.created"
    TASK_STATUS_UPDATED = "system.task_status.updated"
    HOOK_EXECUTION_LOGGED = "system.hook.execution.logged"
    HOOK_FINDING_CREATED = "system.hook.finding.created"


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
        "telemetry",
        "Host AI session begun; session_id established",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.SESSION_LIFECYCLE_ENDED,
        "telemetry",
        "Host AI session ended normally",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROMPT_LIFECYCLE_SUBMITTED,
        "telemetry",
        "User submitted a prompt (redacted: no raw text)",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROMPT_LIFECYCLE_VALIDATED,
        "telemetry",
        "Prompt passed DS validation gates",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.TOOL_EXECUTION_STARTED,
        "telemetry",
        "A tool call began (tool name + args shape; no raw output)",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.TOOL_EXECUTION_COMPLETED,
        "telemetry",
        "A tool call completed (result shape; no raw output)",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.TOKEN_CONSUMPTION_RECORDED,
        "telemetry",
        "Token count for a session turn",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.SKILL_LIFECYCLE_LOADED,
        "telemetry",
        "A DS skill was activated for this session",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.SKILL_LIFECYCLE_COMPLETED,
        "telemetry",
        "A DS skill's primary action completed",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORKFLOW_PROGRESS_UPDATED,
        "telemetry",
        "A workflow milestone progressed",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.CONTEXT_THRESHOLD_CROSSED,
        "telemetry",
        "Context window crossed a configured threshold",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.SECURITY_SCAN_COMPLETED,
        "telemetry",
        "Security scan ran against a file or diff",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.QUALITY_SCORE_RECORDED,
        "telemetry",
        "Quality score computed for an artifact",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    EventTypeMeta(
        EventType.INTEGRATION_HEALTH_CHANGED,
        "telemetry",
        "An integration health state transition occurred",
        False,
        EventCategory.HOOK_EMITTED,
    ),
    # Production-emitted types
    EventTypeMeta(
        EventType.GUARDRAIL_DECISION,
        "telemetry",
        "Guardrail policy decision logged for compliance audit",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.RESEARCH_VALIDATED,
        "telemetry",
        "Research result validated by session outcome",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.RESEARCH_COMPLETED,
        "telemetry",
        "Research query completed and result stored",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.RESEARCH_CACHE_STORED,
        "telemetry",
        "Research result stored in cache",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.RESEARCH_CACHE_CLEARED,
        "telemetry",
        "Research cache entry cleared for topic",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROJECT_REGISTERED,
        "sdlc",
        "Project registered in the analysis registry",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROJECT_UPDATED,
        "sdlc",
        "Project metadata updated in registry",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_STARTED,
        "telemetry",
        "Project analysis pipeline started",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_DISCOVERY_COMPLETED,
        "telemetry",
        "Discovery phase of analysis completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_RESEARCH_COMPLETED,
        "telemetry",
        "Research phase of analysis completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_AUDIT_COMPLETED,
        "telemetry",
        "Audit phase of analysis completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_BUG_ANALYSIS_COMPLETED,
        "telemetry",
        "Bug analysis phase completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_SYNTHESIS_COMPLETED,
        "telemetry",
        "Synthesis phase of analysis completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_COMPLETED,
        "telemetry",
        "Full project analysis pipeline completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.ANALYSIS_FAILED,
        "telemetry",
        "Project analysis pipeline failed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.AUDIT_VIOLATIONS_CLEARED,
        "telemetry",
        "Audit violations cleared before new scan",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.AUDIT_VIOLATION_FOUND,
        "telemetry",
        "Architecture violation detected during audit",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.AUDIT_IMPROVEMENTS_CLEARED,
        "telemetry",
        "Audit improvements cleared before new scan",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.AUDIT_IMPROVEMENT_FOUND,
        "telemetry",
        "Architecture improvement opportunity detected",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.REPO_ANALYZED,
        "telemetry",
        "External repository analysis completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.REPO_EXTRACTION_STORED,
        "telemetry",
        "Repository pattern extraction stored",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.EXECUTION_COMPLETE,
        "telemetry",
        "GitHub PR execution completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.TESTS_EXECUTED,
        "telemetry",
        "Test suite executed and results collected",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WAVE_STARTED,
        "telemetry",
        "Execution wave started",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WAVE_COMPLETED,
        "telemetry",
        "Execution wave completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WAVE_FAILED,
        "telemetry",
        "Execution wave failed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WAVE_TASK_UPDATED,
        "telemetry",
        "Wave task status updated",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORKFLOW_LEARNED,
        "telemetry",
        "Workflow pattern learned from execution history",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.DOCUMENT_CREATED,
        "sdlc",
        "Document created in document store",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.DOCUMENT_UPDATED,
        "sdlc",
        "Document updated in document store",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.DOCUMENT_ARCHIVED,
        "sdlc",
        "Document archived in document store",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    # CLI lifecycle events
    EventTypeMeta(
        EventType.WORK_ORDER_STARTED,
        "sdlc",
        "Work order entered in_progress state",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORK_ORDER_CLOSED,
        "sdlc",
        "Work order closed after gate checks passed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORK_ORDER_BLOCKED,
        "sdlc",
        "Work order blocked with a stated reason",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.GATE_BYPASSED,
        "sdlc",
        "A gate check was bypassed with --force",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.TASK_COMPLETED,
        "sdlc",
        "A task within a work order was marked complete",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.MILESTONE_COMPLETED,
        "sdlc",
        "A milestone was closed after verification",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.SKILL_INVOKED,
        "sdlc",
        "A Dream Studio skill was invoked via CLI",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORKFLOW_NODE_COMPLETED,
        "telemetry",
        "A workflow DAG node completed execution",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.GATE_PRE_PUSH_FAILED,
        "sdlc",
        "A pre-push gate failed during `ds workflow run pre-push --non-interactive`",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    # Execution lifecycle telemetry (TA0b)
    EventTypeMeta(
        EventType.EXECUTION_STARTED,
        "telemetry",
        "Execution run started",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.EXECUTION_COMPLETED,
        "telemetry",
        "Execution run completed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.EXECUTION_FAILED,
        "telemetry",
        "Execution run failed",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    # SDLC entity creation events (TA0)
    EventTypeMeta(
        EventType.PROJECT_CREATED,
        "sdlc",
        "A new project was registered in Dream Studio",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROJECT_DELETED,
        "sdlc",
        "A project was deleted (cascade to milestones, work orders, tasks)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROJECT_ACTIVATED,
        "sdlc",
        "A project was set as the active project (status → active)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROJECT_DEACTIVATED,
        "sdlc",
        "A project was deactivated (status → paused)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.MILESTONE_CREATED,
        "sdlc",
        "A new milestone was created under a project",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.MILESTONE_DELETED,
        "sdlc",
        "A milestone was deleted",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORK_ORDER_CREATED,
        "sdlc",
        "A new work order was created under a milestone/project",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.WORK_ORDER_DELETED,
        "sdlc",
        "A work order was deleted via cascade from project deletion",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    # Design brief + task lifecycle events (18.2.4 / TA1)
    EventTypeMeta(
        EventType.DESIGN_BRIEF_CREATED,
        "sdlc",
        "Draft design brief created for a project",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.DESIGN_BRIEF_UPDATED,
        "sdlc",
        "One field updated on a draft design brief",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.DESIGN_BRIEF_LOCKED,
        "sdlc",
        "Design brief locked (human approval gate passed)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.DESIGN_BRIEF_DELETED,
        "sdlc",
        "A design brief was deleted via cascade from project deletion",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.TASK_CREATED,
        "sdlc",
        "A new task was added to a work order",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.TASK_STARTED,
        "sdlc",
        "Work began on a task (no call site yet — registered for TA2 active-task wiring)",
        False,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.TASK_DELETED,
        "sdlc",
        "A task was deleted (cascade from project or work order deletion)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    # Activity-log retirement (TA0c) — operational telemetry migrated from legacy store
    EventTypeMeta(
        EventType.WORKFLOW_COMPLETED,
        "telemetry",
        "Workflow run completed (replaces activity_log workflow_run rows)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.LESSON_CAPTURED,
        "telemetry",
        "Operational lesson learned captured from analysis or execution",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.SKILL_EXECUTED,
        "telemetry",
        "Skill execution telemetry with status and duration",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.RISK_SCORE_COMPUTED,
        "telemetry",
        "Risk score computed for a security event",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.SECURITY_FINDING_RECORDED,
        "telemetry",
        "Security finding from SARIF scan recorded",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.APPROACH_CAPTURED,
        "telemetry",
        "Skill approach pattern captured for reuse",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.PROJECT_STATS_UPDATED,
        "telemetry",
        "Project session or token stats updated in registry",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.SESSION_RECORDED,
        "telemetry",
        "Session record inserted to database (DB-level, distinct from hook lifecycle)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.SESSION_CLOSED,
        "telemetry",
        "Session record closed in database with outcome and token counts",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.HANDOFF_CREATED,
        "telemetry",
        "Session handoff document created in database",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.TASK_STATUS_UPDATED,
        "telemetry",
        "PRD task status updated (blocked, in_progress, completed)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.HOOK_EXECUTION_LOGGED,
        "telemetry",
        "Hook execution logged with status, duration, and exit code",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.HOOK_FINDING_CREATED,
        "telemetry",
        "Hook analysis finding (anomaly, violation, etc.) created",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    # TA3: Per-tool-invocation token consumption with full SDLC attribution
    EventTypeMeta(
        EventType.TOKEN_CONSUMED,
        "telemetry",
        "Token consumption attributed to a specific tool invocation, with SDLC trace from active task",
        True,
        EventCategory.HOOK_EMITTED,
    ),
    # Skill execution budget telemetry
    EventTypeMeta(
        EventType.SKILL_BUDGET_EXCEEDED,
        "telemetry",
        "Skill execution exceeded its configured token/context budget",
        False,
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
