"""Event type routing registry for the v2 dual canonical architecture.

Declares routes_to for every known event_type. The ingestor reads this at
ingest time to decide which canonical table(s) to write to.

Routing destinations:
  ("business",)        → business_canonical_events only
  ("ai",)              → ai_canonical_events only
  ("business", "ai")   → both canonicals, linked by correlation_id
  ()                   → raw only (Commitment 9: mechanical detail)

Event-presence rule (data-model-v2.md):
  Pure operator actions with no AI involvement → business only
  AI mechanical work with no business outcome  → ai only
  AI-driven work producing a business artifact → both (paired)
  Individual tool calls / mechanical detail    → raw only
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RegistryEntry:
    event_type: str
    routes_to: tuple[str, ...]  # subset of {"business", "ai"}; () = raw only
    granularity_level: str  # "meaningful-unit" | "mechanical-detail"
    description: str
    # Keys that MUST be present in the payload dict for this event type.
    # Enforces the additive-only schema evolution policy. Empty = no enforcement.
    # Populated for event types consumed by at least one projection.
    payload_required_keys: frozenset = field(default_factory=frozenset, compare=False, hash=False)


_BUSINESS: tuple[str, ...] = ("business",)
_AI: tuple[str, ...] = ("ai",)
_BOTH: tuple[str, ...] = ("business", "ai")
_RAW_ONLY: tuple[str, ...] = ()

_ENTRIES: tuple[RegistryEntry, ...] = (
    # ── Business-only: Pure SDLC operator actions ─────────────────────────────
    # These represent changes TO the project/SDLC state, driven by operator
    # commands. No AI execution is the primary cause.
    RegistryEntry(
        "project.created", _BUSINESS, "meaningful-unit", "Project registered in Dream Studio"
    ),
    RegistryEntry(
        "project.deleted",
        _BUSINESS,
        "meaningful-unit",
        "Project deleted with cascade to milestones, work orders, tasks",
    ),
    RegistryEntry(
        "project.activated",
        _BUSINESS,
        "meaningful-unit",
        "Project set as the active project (status → active)",
        payload_required_keys=frozenset({"project_id"}),
    ),
    RegistryEntry(
        "project.deactivated",
        _BUSINESS,
        "meaningful-unit",
        "Project deactivated (status → paused)",
        payload_required_keys=frozenset({"project_id"}),
    ),
    RegistryEntry(
        "project.registered",
        _BUSINESS,
        "meaningful-unit",
        "Project registered in the analysis registry",
    ),
    RegistryEntry(
        "project.updated", _BUSINESS, "meaningful-unit", "Project metadata updated in registry"
    ),
    RegistryEntry(
        "milestone.created", _BUSINESS, "meaningful-unit", "New milestone created under a project"
    ),
    RegistryEntry("milestone.deleted", _BUSINESS, "meaningful-unit", "Milestone deleted"),
    RegistryEntry(
        "milestone.completed",
        _BUSINESS,
        "meaningful-unit",
        "Milestone closed after gate verification",
    ),
    RegistryEntry(
        "work_order.created",
        _BUSINESS,
        "meaningful-unit",
        "New work order created under a milestone or project",
        payload_required_keys=frozenset({"title", "status", "type"}),
    ),
    RegistryEntry(
        "work_order.started",
        _BUSINESS,
        "meaningful-unit",
        "Work order entered in_progress state",
        payload_required_keys=frozenset({"work_order_id", "title", "type", "project_id"}),
    ),
    RegistryEntry(
        "work_order.blocked",
        _BUSINESS,
        "meaningful-unit",
        "Work order blocked with a stated reason",
        payload_required_keys=frozenset({"work_order_id", "title", "project_id", "reason"}),
    ),
    RegistryEntry(
        "work_order.unblocked",
        _BUSINESS,
        "meaningful-unit",
        "Work order unblocked and returned to in_progress state",
        payload_required_keys=frozenset({"work_order_id", "title", "project_id"}),
    ),
    RegistryEntry(
        "work_order.closed",
        _BUSINESS,
        "meaningful-unit",
        "Work order closed after gate checks passed",
        payload_required_keys=frozenset({"work_order_id", "title", "project_id", "forced"}),
    ),
    RegistryEntry(
        "work_order.deleted",
        _BUSINESS,
        "meaningful-unit",
        "Work order deleted via cascade from project deletion",
        payload_required_keys=frozenset({"work_order_id", "project_id"}),
    ),
    RegistryEntry(
        "design_brief.created",
        _BUSINESS,
        "meaningful-unit",
        "Draft design brief created for a project",
        payload_required_keys=frozenset({"brief_id", "project_id"}),
    ),
    RegistryEntry(
        "design_brief.updated",
        _BUSINESS,
        "meaningful-unit",
        "One field updated on a draft design brief",
        payload_required_keys=frozenset({"brief_id", "field", "new_value"}),
    ),
    RegistryEntry(
        "design_brief.locked",
        _BUSINESS,
        "meaningful-unit",
        "Design brief locked (human approval gate passed)",
        payload_required_keys=frozenset({"brief_id"}),
    ),
    RegistryEntry(
        "design_brief.deleted",
        _BUSINESS,
        "meaningful-unit",
        "Design brief deleted via cascade from project deletion",
        payload_required_keys=frozenset({"brief_id", "project_id"}),
    ),
    RegistryEntry("task.created", _BUSINESS, "meaningful-unit", "New task added to a work order"),
    RegistryEntry("task.started", _BUSINESS, "meaningful-unit", "Work began on a task"),
    RegistryEntry(
        "task.deleted",
        _BUSINESS,
        "meaningful-unit",
        "Task deleted via cascade from project or work order deletion",
    ),
    RegistryEntry(
        "task.completed", _BUSINESS, "meaningful-unit", "Task marked complete within a work order"
    ),
    RegistryEntry(
        "preflight.created",
        _BUSINESS,
        "meaningful-unit",
        "New preflight finding recorded on a work order (blast_radius/impact/risk/spec_reference/dependency)",
    ),
    RegistryEntry(
        "preflight.status_changed",
        _BUSINESS,
        "meaningful-unit",
        "Preflight finding status updated (open/acknowledged/mitigated/accepted_risk/resolved)",
    ),
    RegistryEntry(
        "gate.bypassed",
        _BUSINESS,
        "meaningful-unit",
        "Gate check bypassed with --force (operator decision, auditable)",
    ),
    RegistryEntry(
        "gate.pre_push.failed",
        _BUSINESS,
        "meaningful-unit",
        "Pre-push gate failed during ds workflow run pre-push",
    ),
    RegistryEntry(
        "document.created", _BUSINESS, "meaningful-unit", "Document created in document store"
    ),
    RegistryEntry(
        "document.updated", _BUSINESS, "meaningful-unit", "Document updated in document store"
    ),
    RegistryEntry(
        "document.archived", _BUSINESS, "meaningful-unit", "Document archived in document store"
    ),
    RegistryEntry(
        "system.task_status.updated",
        _BUSINESS,
        "meaningful-unit",
        "PRD task status updated (blocked, in_progress, completed)",
    ),
    # ── AI-only: AI execution facts at meaningful-unit granularity ────────────
    # These record what AI did. No direct business-state change; business facts
    # are produced by downstream projections or paired business events.
    # Session and prompt lifecycle
    RegistryEntry(
        "session.lifecycle.started",
        _AI,
        "meaningful-unit",
        "Host AI session begun; session_id established",
    ),
    RegistryEntry(
        "session.lifecycle.ended", _AI, "meaningful-unit", "Host AI session ended normally"
    ),
    RegistryEntry(
        "prompt.lifecycle.submitted",
        _AI,
        "meaningful-unit",
        "User submitted a prompt (redacted: no raw prompt text retained)",
    ),
    RegistryEntry(
        "prompt.lifecycle.validated",
        _AI,
        "meaningful-unit",
        "Prompt passed Dream Studio validation gates",
    ),
    RegistryEntry(
        "token.consumption.recorded",
        _AI,
        "meaningful-unit",
        "Token count for a session turn (per-turn summary)",
    ),
    RegistryEntry(
        "token.consumed",
        _AI,
        "meaningful-unit",
        "Per-tool token consumption with full SDLC attribution",
    ),
    RegistryEntry(
        "context.threshold.crossed",
        _AI,
        "meaningful-unit",
        "Context window crossed a configured threshold",
    ),
    # Skill and workflow execution
    RegistryEntry(
        "skill.invoked",
        _AI,
        "meaningful-unit",
        "Dream Studio skill invoked via CLI (meaningful execution unit)",
    ),
    RegistryEntry(
        "skill.executed",
        _AI,
        "meaningful-unit",
        "Skill execution telemetry with status and duration",
    ),
    RegistryEntry(
        "skill.budget_exceeded", _AI, "meaningful-unit", "Skill execution exceeded its token budget"
    ),
    RegistryEntry(
        "skill.lifecycle.loaded",
        _AI,
        "meaningful-unit",
        "DS skill activated for the current session",
    ),
    RegistryEntry(
        "skill.lifecycle.completed", _AI, "meaningful-unit", "DS skill primary action completed"
    ),
    RegistryEntry(
        "workflow.node.completed", _AI, "meaningful-unit", "Workflow DAG node completed execution"
    ),
    RegistryEntry("workflow.completed", _AI, "meaningful-unit", "Workflow run completed"),
    # WO-AGENT-TELEMETRY: subagent (Task tool) invocations. Emitted by
    # emitters/claude_code/emitter.py with trace.agent_id=subagent_type, routed to
    # ai_canonical_events (where the agent_id dimension lives) so the agent
    # dashboard component finally has source data. Previously unregistered →
    # noisy per-invocation dual-write warning on the hot path.
    RegistryEntry(
        "agent.execution.completed", _AI, "meaningful-unit", "Subagent invocation completed"
    ),
    RegistryEntry("agent.execution.started", _AI, "meaningful-unit", "Subagent invocation started"),
    RegistryEntry("agent.execution.failed", _AI, "meaningful-unit", "Subagent invocation failed"),
    # WO-VALIDATION-CAPTURE: validation/eval check outcomes (SQL/TEST/API-CHECK)
    # emitted by core/work_orders/verify.py::run_executable_checks. Routed to
    # ai_canonical_events so the validations dashboard component (WO-1 read repoint
    # over events_fact validation.result_recorded) finally has a source. Distinct
    # from event.validation.failed (schema-rejected events — ingestion health).
    RegistryEntry(
        "validation.result_recorded",
        _AI,
        "meaningful-unit",
        "Validation/eval check result recorded",
    ),
    # WO 9f47a1a0: control/execution/workflow/state.py now reliably reaches
    # core/telemetry/emitters.py::emit_workflow_invocation on every terminal
    # workflow run (previously gated behind the write-orphaned
    # raw_workflow_runs INSERT — see migration 141). That function's
    # execution_events write is auto-mirrored to the spool by
    # record_execution_event(); this was previously unregistered, defaulting
    # to a noisy dual-canonical write. Raw-only: workflow.completed above is
    # already the canonical fact for this same event; this is a duplicate
    # execution_events telemetry mirror with no canonical-table reader.
    RegistryEntry(
        "workflow.invocation_recorded",
        _RAW_ONLY,
        "mechanical-detail",
        "execution_events telemetry mirror of a workflow invocation (see workflow.completed for the canonical fact)",
    ),
    RegistryEntry(
        "workflow.progress.updated", _AI, "meaningful-unit", "Workflow milestone progress updated"
    ),
    RegistryEntry(
        "workflow.learned",
        _AI,
        "meaningful-unit",
        "Workflow pattern learned from execution history",
    ),
    # Execution lifecycle
    RegistryEntry("execution.started", _AI, "meaningful-unit", "Execution run started"),
    RegistryEntry("execution.completed", _AI, "meaningful-unit", "Execution run completed"),
    RegistryEntry("execution.failed", _AI, "meaningful-unit", "Execution run failed"),
    RegistryEntry("execution.complete", _AI, "meaningful-unit", "GitHub PR execution completed"),
    RegistryEntry(
        "execution.tests_executed",
        _AI,
        "meaningful-unit",
        "Test suite executed and results collected",
    ),
    # Wave (orchestration units)
    RegistryEntry("wave.started", _AI, "meaningful-unit", "Execution wave started"),
    RegistryEntry("wave.completed", _AI, "meaningful-unit", "Execution wave completed"),
    RegistryEntry("wave.failed", _AI, "meaningful-unit", "Execution wave failed"),
    RegistryEntry("wave.task_updated", _AI, "meaningful-unit", "Wave task status updated"),
    # Research pipeline
    RegistryEntry(
        "research.validated", _AI, "meaningful-unit", "Research result validated by session outcome"
    ),
    RegistryEntry(
        "research.completed", _AI, "meaningful-unit", "Research query completed and result stored"
    ),
    RegistryEntry(
        "research.cache_stored", _AI, "meaningful-unit", "Research result stored in cache"
    ),
    RegistryEntry(
        "research.cache_cleared", _AI, "meaningful-unit", "Research cache entry cleared for a topic"
    ),
    # Analysis pipeline (each phase is a meaningful AI execution unit)
    RegistryEntry("analysis.started", _AI, "meaningful-unit", "Project analysis pipeline started"),
    RegistryEntry(
        "analysis.discovery_completed",
        _AI,
        "meaningful-unit",
        "Discovery phase of analysis completed",
    ),
    RegistryEntry(
        "analysis.research_completed",
        _AI,
        "meaningful-unit",
        "Research phase of analysis completed",
    ),
    RegistryEntry(
        "analysis.audit_completed", _AI, "meaningful-unit", "Audit phase of analysis completed"
    ),
    RegistryEntry(
        "analysis.bug_analysis_completed",
        _AI,
        "meaningful-unit",
        "Bug analysis phase of analysis completed",
    ),
    RegistryEntry(
        "analysis.synthesis_completed",
        _AI,
        "meaningful-unit",
        "Synthesis phase of analysis completed",
    ),
    RegistryEntry(
        "analysis.completed", _AI, "meaningful-unit", "Full project analysis pipeline completed"
    ),
    RegistryEntry("analysis.failed", _AI, "meaningful-unit", "Project analysis pipeline failed"),
    # Repository analysis
    RegistryEntry(
        "repo.analyzed", _AI, "meaningful-unit", "External repository analysis completed"
    ),
    RegistryEntry(
        "repo.extraction.stored", _AI, "meaningful-unit", "Repository pattern extraction stored"
    ),
    # Guardrail (AI governance)
    RegistryEntry(
        "guardrail.decision",
        _AI,
        "meaningful-unit",
        "Guardrail policy decision logged for compliance audit",
    ),
    # Operational session/hook telemetry
    RegistryEntry(
        "system.session.recorded", _AI, "meaningful-unit", "Session record inserted to database"
    ),
    RegistryEntry(
        "system.session.closed",
        _AI,
        "meaningful-unit",
        "Session record closed with outcome and token counts",
    ),
    RegistryEntry(
        "system.handoff.created",
        _AI,
        "meaningful-unit",
        "Session handoff document created in database",
    ),
    RegistryEntry(
        "system.hook.execution.logged",
        _AI,
        "meaningful-unit",
        "Hook execution logged with status, duration, and exit code",
    ),
    RegistryEntry(
        "system.lesson.captured",
        _AI,
        "meaningful-unit",
        "Operational lesson learned captured from analysis or execution",
    ),
    RegistryEntry(
        "system.approach.captured",
        _AI,
        "meaningful-unit",
        "Skill approach pattern captured for reuse",
    ),
    RegistryEntry(
        "system.project_stats.updated",
        _AI,
        "meaningful-unit",
        "Project session or token stats updated in registry",
    ),
    # Computed metrics (AI-internal, no business-state change per event)
    RegistryEntry(
        "risk.score.computed", _AI, "meaningful-unit", "Risk score computed for a security event"
    ),
    RegistryEntry(
        "audit.violations_cleared",
        _AI,
        "meaningful-unit",
        "Audit violations cleared before a new scan run",
    ),
    RegistryEntry(
        "audit.improvements_cleared",
        _AI,
        "meaningful-unit",
        "Audit improvements cleared before a new scan run",
    ),
    RegistryEntry(
        "integration.health.changed", _AI, "meaningful-unit", "Integration health state transition"
    ),
    # Pipeline diagnostic (spool validation error — operational, not business)
    RegistryEntry(
        "event.validation.failed",
        _AI,
        "meaningful-unit",
        "Spool event failed schema validation (operational diagnostic)",
    ),
    # Security scan start/failure (execution fact only; no business finding yet)
    RegistryEntry(
        "security.scan.started",
        _AI,
        "meaningful-unit",
        "Security scan initiated — AI execution only",
    ),
    RegistryEntry(
        "security.scan.failed",
        _AI,
        "meaningful-unit",
        "Security scan failed — AI execution error, no business finding",
    ),
    # ── Raw-only: Individual tool calls (Commitment 9) ─────────────────────────
    # Canonical records meaningful execution units, not individual tool calls.
    # These live in raw_claude_code_events, accessible via correlation_id drill-down.
    RegistryEntry(
        "tool.execution.completed",
        _RAW_ONLY,
        "mechanical-detail",
        "Individual tool call completed — raw only per Commitment 9",
    ),
    RegistryEntry(
        "tool.execution.started",
        _RAW_ONLY,
        "mechanical-detail",
        "Individual tool call started — raw only per Commitment 9",
    ),
    # Legacy per-tool hook event (pre-18.1.2 era, same category as tool.execution.*)
    RegistryEntry(
        "hook.tool_activity",
        _RAW_ONLY,
        "mechanical-detail",
        "Legacy per-tool hook activity event — raw only per Commitment 9",
    ),
    # ── Paired: AI-driven work producing business artifacts ────────────────────
    # Both an AI execution fact (what ran) AND a business fact (what was found).
    # Linked in both canonicals via shared correlation_id.
    # Security findings: AI scan runs (→ ai) AND produces a business finding (→ business)
    RegistryEntry(
        "security.finding.recorded",
        _BOTH,
        "meaningful-unit",
        "Security finding from SARIF scan — AI execution + business fact",
    ),
    RegistryEntry(
        "security.finding.logged",
        _BOTH,
        "meaningful-unit",
        "Security finding written to execution telemetry spine (W25 path)",
        payload_required_keys=frozenset({"finding_id", "project_id", "severity", "status"}),
    ),
    RegistryEntry(
        "security.finding.resolved",
        _BOTH,
        "meaningful-unit",
        # resolution values: fixed|mitigated|accepted|false_positive (non-exhaustive; may extend in 18.4.x)
        "Security finding status transitioned to resolved/fixed/mitigated",
        payload_required_keys=frozenset({"finding_id", "project_id"}),
    ),
    RegistryEntry(
        "security.finding.detected",
        _BOTH,
        "meaningful-unit",
        "Security finding detected by scan — AI execution + business fact",
    ),
    RegistryEntry(
        "security.scan.completed",
        _BOTH,
        "meaningful-unit",
        "Security scan completed with results — AI execution + business outcome",
    ),
    # Findings spine (WO-Y / AD-10): AI scan (→ ai) + business finding fact (→ business)
    RegistryEntry(
        "finding.recorded",
        _BOTH,
        "meaningful-unit",
        "Security or readiness finding recorded — AI scan produces business finding fact",
    ),
    RegistryEntry(
        "finding.status_changed",
        _BOTH,
        "meaningful-unit",
        "Finding status changed — AI resolution produces business status update",
    ),
    # Eval + decision family (WO-DBA-EVAL-DECISION): eval/decision facts are events
    # attached to business entities; replaces ds_eval_runs/hook_eval_runs/decision_log rows.
    RegistryEntry(
        "work_order.verified",
        _BUSINESS,
        "meaningful-unit",
        "Independent review verdict recorded for a work order",
    ),
    RegistryEntry(
        "eval.run.completed",
        _BUSINESS,
        "meaningful-unit",
        "Behavioral/outcome/guardrail eval run completed",
    ),
    RegistryEntry(
        "decision.recorded",
        _BUSINESS,
        "meaningful-unit",
        "Governance decision recorded with context, outcome, and policy",
    ),
    # Audit findings: AI audit (→ ai) discovers business violations/improvements (→ business)
    RegistryEntry(
        "audit.violation_found",
        _BOTH,
        "meaningful-unit",
        "Architecture violation detected — AI audit produces business fact",
    ),
    RegistryEntry(
        "audit.improvement_found",
        _BOTH,
        "meaningful-unit",
        "Architecture improvement found — AI audit produces business fact",
    ),
    # Quality metrics: AI-computed score (→ ai) with business significance (→ business)
    RegistryEntry(
        "quality.score.recorded",
        _BOTH,
        "meaningful-unit",
        "Quality score computed — AI metric with business significance",
    ),
    # Hook findings: hook analysis (→ ai) produces business-relevant findings (→ business)
    RegistryEntry(
        "system.hook.finding.created",
        _BOTH,
        "meaningful-unit",
        "Hook analysis finding — AI inspection produces business finding",
    ),
)

# Primary lookup dict: event_type string → RegistryEntry
_REGISTRY: dict[str, RegistryEntry] = {e.event_type: e for e in _ENTRIES}


def get_routes(event_type: str) -> tuple[str, ...]:
    """Return routing destinations for event_type.

    Unknown event_types default to ("business", "ai") — the safe over-record
    default. Callers should log a warning when this fallback fires.
    """
    entry = _REGISTRY.get(event_type)
    if entry is None:
        return ("business", "ai")
    return entry.routes_to


def is_registered(event_type: str) -> bool:
    """Return True if event_type has an explicit registry entry."""
    return event_type in _REGISTRY


def get_entry(event_type: str) -> RegistryEntry | None:
    """Return the RegistryEntry for event_type, or None if not registered."""
    return _REGISTRY.get(event_type)


def all_entries() -> tuple[RegistryEntry, ...]:
    """Return all registry entries (for inspection and tooling)."""
    return _ENTRIES
