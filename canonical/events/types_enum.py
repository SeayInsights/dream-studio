from __future__ import annotations

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

    # Findings spine event types (WO-Y / AD-10)
    FINDING_RECORDED = "finding.recorded"
    FINDING_STATUS_CHANGED = "finding.status_changed"

    # Eval + decision event family (WO-DBA-EVAL-DECISION)
    WORK_ORDER_VERIFIED = "work_order.verified"
    EVAL_RUN_COMPLETED = "eval.run.completed"
    DECISION_RECORDED = "decision.recorded"

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
