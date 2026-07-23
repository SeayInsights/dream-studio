"""Best-effort dual-write emitters for the execution telemetry spine — facade over the split modules.

WO-AI-SPINE (migration 139, AD-5): decision_records, outcome_records, and
dashboard_attention_items were dropped — their writers already dual-wrote
execution_events, so the per-type tables were pure duplication (0/2/0
production rows). record_dashboard_attention() and the outcome_records INSERT
helper were removed from execution_spine.py alongside them; readers now
derive decision/outcome/attention state from execution_events filtered by
event_type + outcome_status (see core/telemetry/read_models.py).

WO-GF-TELEMETRY-SPLIT: implementation moved to emitters_{shared,activity,
validation,security,workflow,research_decision}.py; this module re-exports
the full prior public+private surface so existing
`from core.telemetry.emitters import X` callers are unchanged.
"""

from __future__ import annotations

from .emitters_activity import (
    emit_hook_tool_activity,
    emit_skill_invocations,
    emit_token_usage_record,
)
from .emitters_research_decision import emit_decision_record, emit_research_evidence_record
from .emitters_security import (
    _int_or_none,
    _severity,
    _stable_security_finding_id,
    emit_security_finding,
    emit_security_finding_resolved,
)
from .emitters_shared import (
    MODE_BEST_EFFORT,
    MODE_STRICT,
    TELEMETRY_DB_ENV,
    TELEMETRY_DISABLED_ENV,
    TelemetryContext,
    TelemetryEmitResult,
    _clean,
    _connect,
    _context,
    _default_db_path,
    _emit,
    _id,
    _refs,
    _require_tables,
    _stable_id,
    _status,
    _text,
    _truthy,
    _tuple,
)
from .emitters_validation import emit_validation_result
from .emitters_workflow import emit_workflow_invocation

__all__ = [
    "MODE_BEST_EFFORT",
    "MODE_STRICT",
    "TELEMETRY_DB_ENV",
    "TELEMETRY_DISABLED_ENV",
    "TelemetryContext",
    "TelemetryEmitResult",
    "_clean",
    "_connect",
    "_context",
    "_default_db_path",
    "_emit",
    "_id",
    "_int_or_none",
    "_refs",
    "_require_tables",
    "_severity",
    "_stable_id",
    "_stable_security_finding_id",
    "_status",
    "_text",
    "_truthy",
    "_tuple",
    "emit_decision_record",
    "emit_hook_tool_activity",
    "emit_research_evidence_record",
    "emit_security_finding",
    "emit_security_finding_resolved",
    "emit_skill_invocations",
    "emit_token_usage_record",
    "emit_validation_result",
    "emit_workflow_invocation",
]
