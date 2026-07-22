from __future__ import annotations

from .event_type_registry_shared import RegistryEntry, _AI, _RAW_ONLY

_AI_ENTRIES: tuple[RegistryEntry, ...] = (
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
)
