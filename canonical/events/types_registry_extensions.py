from __future__ import annotations

from .types_enum import EventCategory, EventType
from .types_meta import EventTypeMeta
from .types_registry_core import _CORE_ENTRIES

_EXTENSION_ENTRIES: tuple[EventTypeMeta, ...] = (
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
        EventType.SECURITY_FINDING_LOGGED,
        "telemetry",
        "Security finding written to canonical log",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.SECURITY_FINDING_RESOLVED,
        "telemetry",
        "Security finding marked as resolved",
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
    # Findings spine events (WO-Y / AD-10)
    EventTypeMeta(
        EventType.FINDING_RECORDED,
        "security",
        "Security or readiness finding recorded on the findings spine",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.FINDING_STATUS_CHANGED,
        "security",
        "Finding status changed (open → mitigated/false_positive/accepted/resolved)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    # Eval + decision event family (WO-DBA-EVAL-DECISION)
    EventTypeMeta(
        EventType.WORK_ORDER_VERIFIED,
        "sdlc",
        "Independent review verdict recorded for a work order (status, scores, reasons)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.EVAL_RUN_COMPLETED,
        "telemetry",
        "Behavioral/outcome/guardrail eval run completed (scores, passed, failure reasons)",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
    EventTypeMeta(
        EventType.DECISION_RECORDED,
        "sdlc",
        "Governance decision recorded with context, outcome, reasoning, and policy",
        True,
        EventCategory.PRODUCTION_EMITTED,
    ),
)

EVENT_TYPE_REGISTRY: tuple[EventTypeMeta, ...] = _CORE_ENTRIES + _EXTENSION_ENTRIES

# Backward-compatible: hook-emitted types that are implemented in the emitter
EMITTER_IMPLEMENTED: frozenset[EventType] = frozenset(
    m.event_type
    for m in EVENT_TYPE_REGISTRY
    if m.category == EventCategory.HOOK_EMITTED and m.emitter_implemented
)

ALL_EVENT_TYPES: frozenset[str] = frozenset(t.value for t in EventType)
