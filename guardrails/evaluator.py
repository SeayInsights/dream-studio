"""Guardrail rule evaluator — deterministic policy enforcement.

The evaluator:
1. Loads rules from YAML files
2. Queries activity_log for trigger conditions
3. Returns allow/block/require_approval decision
4. Logs decision to guardrail_decisions table

Exit codes:
- 0 = allow (no violations)
- 1 = block (violations found, action=block)
- 2 = require_approval (violations found, action=require_approval)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.event_store.studio_db import get_connection  # noqa: E402
from core.decisions import emit_decision  # noqa: E402
from canonical.events.envelope import CanonicalEventEnvelope  # noqa: E402
from canonical.events.types import EventType as CanonicalEventType  # noqa: E402
from emitters.shared.spool_writer import write_envelopes  # noqa: E402

from .loader import load_rules  # noqa: E402
from .models import EvaluationError, GuardrailAction, GuardrailDecision  # noqa: E402

CANONICAL_EVENTS_FIELDS = {
    "event_id",
    "event_type",
    "timestamp",
    "session_id",
    "project_id",
    "severity",
    "confidence",
    "trace",
    "payload",
    "schema_version",
    "source_type",
}

# activity_log was removed in migration 062-063 (TA0c). Any custom_query
# referencing it will fail with "no such table". Listed here for error messages.
_REMOVED_TABLES = {"activity_log"}


def _custom_query_matches(conn, query: str) -> bool:
    """Run a constrained read-only custom query against canonical_events."""
    normalized = query.strip()
    lowered = normalized.lower()

    if not lowered.startswith("select"):
        raise EvaluationError("Guardrail custom_query must be a read-only SELECT.")
    if ";" in normalized.rstrip(";"):
        raise EvaluationError("Guardrail custom_query must contain only one SELECT statement.")

    for removed in _REMOVED_TABLES:
        if re.search(rf"\b{re.escape(removed)}\b", lowered):
            raise EvaluationError(
                f"Guardrail custom_query references removed table {removed!r}. "
                f"Use canonical_events instead (columns: {', '.join(sorted(CANONICAL_EVENTS_FIELDS))})."
            )

    if "canonical_events" not in lowered and "hook_invocations" not in lowered:
        raise EvaluationError(
            "Guardrail custom_query must query canonical_events or hook_invocations. "
            f"Supported columns for canonical_events: {', '.join(sorted(CANONICAL_EVENTS_FIELDS))}."
        )

    cursor = conn.execute(normalized)
    return cursor.fetchone() is not None


def _event_data_matches_file_pattern(event_data: str | None, pattern: str) -> bool:
    """Match a trigger file regex against supported event_data path fields."""
    if not event_data:
        return False

    try:
        payload = json.loads(event_data)
    except (TypeError, json.JSONDecodeError):
        return False

    if not isinstance(payload, dict):
        return False

    for key in ("file", "file_path", "path", "filename"):
        value = payload.get(key)
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            if isinstance(candidate, str) and re.search(pattern, candidate):
                return True

    return False


def evaluate_rule_trigger(rule, event_id: str | None, conn) -> bool:
    """Check if a rule's trigger condition matches current state.

    Args:
        rule: GuardrailRule object
        event_id: Activity log event ID (optional)
        conn: Database connection

    Returns:
        True if trigger condition is met, False otherwise
    """
    trigger = rule.trigger

    if trigger.custom_query:
        return _custom_query_matches(conn, trigger.custom_query)

    # Build SQL query based on trigger conditions
    conditions = []
    params = []

    if trigger.event_type:
        conditions.append("event_type = ?")
        params.append(trigger.event_type)

    if trigger.finding_type:
        conditions.append("json_extract(payload, '$.finding_type') = ?")
        params.append(trigger.finding_type)

    if trigger.severity:
        conditions.append("severity = ?")
        params.append(trigger.severity.value)

    if trigger.tool_name:
        conditions.append("(stream_id = ? OR stream_id LIKE ? OR stream_type = ?)")
        params.extend([trigger.tool_name, f"{trigger.tool_name}:%", trigger.tool_name])

    if event_id:
        conditions.append("event_id = ?")
        params.append(event_id)

    if not conditions and not trigger.file_pattern:
        # No trigger conditions specified - rule doesn't apply
        return False

    where_clause = " AND ".join(conditions) if conditions else "1 = 1"

    if trigger.file_pattern:
        query = f"SELECT payload FROM canonical_events WHERE {where_clause}"
        cursor = conn.execute(query, params)
        return any(
            _event_data_matches_file_pattern(row[0], trigger.file_pattern)
            for row in cursor.fetchall()
        )

    query = f"SELECT COUNT(*) FROM canonical_events WHERE {where_clause}"
    cursor = conn.execute(query, params)
    count = cursor.fetchone()[0]

    return count > 0


def evaluate(event_id: str | None = None, rules_dir: Path | None = None) -> GuardrailAction:
    """Evaluate guardrail rules and return decision.

    Args:
        event_id: Optional activity log event ID to evaluate
        rules_dir: Directory containing rule YAML files (defaults to guardrails/rules/)

    Returns:
        GuardrailAction (allow, block, require_approval, advisory)

    Raises:
        EvaluationError: If evaluation fails
    """
    if rules_dir is None:
        rules_dir = Path(__file__).parent / "rules"

    try:
        rules = load_rules(rules_dir)
    except Exception as e:
        raise EvaluationError(f"Failed to load rules: {e}")

    if not rules:
        # No rules loaded - allow by default
        return GuardrailAction.ALLOW

    conn = get_connection()
    triggered_rules = []

    for rule in rules:
        if not rule.enabled:
            continue

        try:
            if evaluate_rule_trigger(rule, event_id, conn):
                triggered_rules.append(rule)
        except EvaluationError:
            raise
        except Exception as e:
            print(
                f"[guardrails] Warning: Failed to evaluate rule {rule.rule_id}: {e}",
                file=sys.stderr,
            )
            continue

    if not triggered_rules:
        return GuardrailAction.ALLOW

    # Determine most severe action
    # Priority: BLOCK > REQUIRE_APPROVAL > ADVISORY > ALLOW
    actions = [r.action for r in triggered_rules]

    if GuardrailAction.BLOCK in actions:
        final_action = GuardrailAction.BLOCK
    elif GuardrailAction.REQUIRE_APPROVAL in actions:
        final_action = GuardrailAction.REQUIRE_APPROVAL
    elif GuardrailAction.ADVISORY in actions:
        final_action = GuardrailAction.ADVISORY
    else:
        final_action = GuardrailAction.ALLOW

    # Emit decision for policy enforcement
    emit_decision(
        decision_type="guardrail.policy_enforcement",
        context={
            "event_id": event_id,
            "triggered_rules": [r.rule_id for r in triggered_rules],
            "rule_count": len(triggered_rules),
        },
        outcome=final_action.value,
        reasoning={
            "policy": "GUARDRAIL_PRIORITY",
            "rule": f"{len(triggered_rules)} rules triggered",
            "rationale": f"Most severe action among {len(actions)} triggered rules",
            "triggered_rule_ids": [r.rule_id for r in triggered_rules],
        },
        confidence=1.0,  # Deterministic policy application
        policy_applied="GUARDRAIL_PRIORITY_V1",
        source_subsystem="guardrails",
        event_id=event_id,
    )

    # Log decision for each triggered rule
    for rule in triggered_rules:
        decision = GuardrailDecision(
            decision_id=str(uuid.uuid4()),
            rule_id=rule.rule_id,
            event_id=event_id,
            action=rule.action,
            message=rule.message,
            evaluated_at=datetime.now(timezone.utc),
            metadata={"rule_name": rule.name, "severity": rule.severity.value},
        )

        try:
            log_decision(decision, conn)
        except Exception as e:
            print(
                f"[guardrails] Warning: Failed to log decision for {rule.rule_id}: {e}",
                file=sys.stderr,
            )

    # Print messages for triggered rules
    for rule in triggered_rules:
        severity_icon = {
            "critical": "❌",
            "high": "⚠️",
            "medium": "⚠️",
            "low": "ℹ️",
            "info": "ℹ️",
        }.get(rule.severity.value, "⚠️")
        print(f"\n{severity_icon} [guardrails] {rule.name} ({rule.rule_id})", file=sys.stderr)
        print(f"   {rule.message}", file=sys.stderr)
        if rule.action == GuardrailAction.BLOCK:
            print(f"   ACTION: BLOCKED\n", file=sys.stderr)
        elif rule.action == GuardrailAction.REQUIRE_APPROVAL:
            print(f"   ACTION: REQUIRES APPROVAL\n", file=sys.stderr)
        else:
            print(f"   ACTION: ADVISORY ONLY\n", file=sys.stderr)

    return final_action


def log_decision(decision: GuardrailDecision, conn) -> None:
    """Log a guardrail decision to the database.

    Args:
        decision: GuardrailDecision object
        conn: Database connection
    """
    # Emit event for compliance audit trail BEFORE DB write (STABILITY: fail if event fails)
    envelope = CanonicalEventEnvelope(
        event_type=CanonicalEventType.GUARDRAIL_DECISION.value,
        session_id=None,
        payload={
            "decision_id": decision.decision_id,
            "rule_id": decision.rule_id,
            "event_id": decision.event_id,
            "action": decision.action.value,
            "message": decision.message,
        },
        severity=decision.metadata.get("severity", "info") if decision.metadata else "info",
        confidence="unavailable",
        project_id=None,
    )
    try:
        write_envelopes([envelope])
    except Exception:
        # spool write failure means the event will not reach SQLite;
        # the calling operation must abort to preserve audit/consistency invariants.
        raise RuntimeError(
            f"Event emission failed for GUARDRAIL_DECISION (decision_id={decision.decision_id}). "
            f"Aborting guardrail logging to prevent compliance audit gap."
        )
    event_id = envelope.event_id

    conn.execute(
        """
        INSERT INTO guardrail_decisions
        (decision_id, rule_id, event_id, action, message, evaluated_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            decision.decision_id,
            decision.rule_id,
            decision.event_id,
            decision.action.value,
            decision.message,
            decision.evaluated_at.isoformat(),
            json.dumps(decision.metadata) if decision.metadata else None,
        ),
    )
    conn.commit()


def main() -> int:
    """CLI entry point for guardrail evaluation.

    Returns:
        Exit code: 0=allow, 1=block, 2=require_approval
    """
    parser = argparse.ArgumentParser(description="Evaluate guardrail rules")
    parser.add_argument("--event-id", help="Activity log event ID to evaluate")
    parser.add_argument("--rules-dir", type=Path, help="Directory containing rule YAML files")
    args = parser.parse_args()

    try:
        action = evaluate(event_id=args.event_id, rules_dir=args.rules_dir)
    except EvaluationError as e:
        print(f"[guardrails] Evaluation error: {e}", file=sys.stderr)
        return 1  # Fail closed (block on error)

    # Map actions to exit codes
    exit_codes = {
        GuardrailAction.ALLOW: 0,
        GuardrailAction.BLOCK: 1,
        GuardrailAction.REQUIRE_APPROVAL: 2,
        GuardrailAction.ADVISORY: 0,  # Advisory doesn't block
    }

    return exit_codes.get(action, 1)  # Default to block on unknown action


if __name__ == "__main__":
    sys.exit(main())
