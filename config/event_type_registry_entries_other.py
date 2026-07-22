from __future__ import annotations

from .event_type_registry_shared import RegistryEntry, _BOTH, _BUSINESS, _RAW_ONLY

_OTHER_ENTRIES: tuple[RegistryEntry, ...] = (
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
