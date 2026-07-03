"""Decision query engine for causal analysis and explainability.

Decisions are read from business_canonical_events (event_type='decision.recorded')
rather than the retired decision_log / decision_event_link tables (T4,
WO-DBA-EVAL-DECISION). Backfilled history (migration 135) stored context/
outcome/reasoning as JSON-encoded strings (decision_log columns were TEXT);
live-emitted events (core/decisions/emitter.py) carry them as native JSON
values. ``_parse_json_field`` handles both shapes defensively.
"""

from __future__ import annotations
import json
from typing import Any, Optional

from core.event_store.studio_db import _connect
from .schema import Decision

_DECISION_EVENT_TYPE = "decision.recorded"


def _parse_json_field(value: Any) -> Any:
    """Best-effort JSON parse of a decision payload sub-field.

    Backfilled rows carry context/outcome/reasoning as JSON-encoded strings;
    live rows carry them as native JSON values already decoded by json.loads()
    on the outer payload. If ``value`` is a string that itself parses as JSON,
    parse it one more level; otherwise return it unchanged (e.g. a bare scalar
    outcome like "allow").
    """
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, ValueError, TypeError):
        return value


def _decision_from_payload(payload: dict[str, Any], event_timestamp: str) -> Decision:
    return Decision(
        decision_id=payload.get("decision_id"),
        decision_type=payload.get("decision_type"),
        context=_parse_json_field(payload.get("context")) or {},
        outcome=_parse_json_field(payload.get("outcome")),
        reasoning=_parse_json_field(payload.get("reasoning")) or {},
        confidence=payload.get("confidence"),
        policy_applied=payload.get("policy_applied"),
        source_subsystem=payload.get("source_subsystem"),
        timestamp=event_timestamp,
    )


def get_decisions(
    decision_type: Optional[str] = None,
    subsystem: Optional[str] = None,
    min_confidence: Optional[float] = None,
    limit: int = 100,
) -> list[Decision]:
    """Query decisions with optional filters.

    Args:
        decision_type: Filter by decision type
        subsystem: Filter by source subsystem
        min_confidence: Minimum confidence threshold
        limit: Maximum number of results

    Returns:
        List of Decision objects matching filters
    """
    conditions = ["event_type = ?"]
    params: list[Any] = [_DECISION_EVENT_TYPE]

    if decision_type:
        conditions.append("json_extract(payload, '$.decision_type') = ?")
        params.append(decision_type)

    if subsystem:
        conditions.append("json_extract(payload, '$.source_subsystem') = ?")
        params.append(subsystem)

    if min_confidence is not None:
        conditions.append("CAST(json_extract(payload, '$.confidence') AS REAL) >= ?")
        params.append(min_confidence)

    query = (
        "SELECT payload, event_timestamp"
        " FROM business_canonical_events"
        " WHERE "
        + " AND ".join(conditions)  # constant fragments; values bound below
        + " ORDER BY event_timestamp DESC"
        " LIMIT ?"
    )
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    decisions = []
    for row in rows:
        payload = json.loads(row[0]) if row[0] else {}
        decisions.append(_decision_from_payload(payload, row[1]))

    return decisions


def explain_decision(decision_id: str) -> dict[str, Any]:
    """Explain a decision with full causal context.

    Args:
        decision_id: Decision ID to explain

    Returns:
        Dict with decision, linked events, reasoning, and causal context
    """
    with _connect() as conn:
        # Get decision
        row = conn.execute(
            """SELECT payload, event_timestamp
               FROM business_canonical_events
               WHERE event_type = ? AND json_extract(payload, '$.decision_id') = ?""",
            (_DECISION_EVENT_TYPE, decision_id),
        ).fetchone()

        if not row:
            return {"error": f"Decision {decision_id} not found"}

        payload = json.loads(row[0]) if row[0] else {}
        decision = _decision_from_payload(payload, row[1])

        # Linked events: the event this decision was triggered by, sourced from
        # payload.triggered_event_id (replaces the dropped decision_event_link
        # join table — emit_decision only ever recorded a single "triggered" link).
        events: list[dict[str, Any]] = []
        triggered_event_id = payload.get("triggered_event_id")
        if triggered_event_id:
            event_row = conn.execute(
                """SELECT event_id, event_type, timestamp, payload
                   FROM canonical_events
                   WHERE event_id = ?""",
                (triggered_event_id,),
            ).fetchone()
            if event_row:
                events.append(
                    {
                        "event_id": event_row[0],
                        "event_type": event_row[1],
                        "timestamp": event_row[2],
                        "payload": json.loads(event_row[3]) if event_row[3] else {},
                        "relation_type": "triggered",
                    }
                )

        # Get upstream events (events that occurred before this decision)
        try:
            upstream = conn.execute(
                """SELECT event_id, event_type, timestamp
                   FROM canonical_events
                   WHERE timestamp < ?
                   ORDER BY timestamp DESC
                   LIMIT 5""",
                (decision.timestamp,),
            ).fetchall()
            upstream_events = [
                {"event_id": r[0], "event_type": r[1], "timestamp": r[2]} for r in upstream
            ]
        except Exception:
            upstream_events = []

        # Get downstream events (events that occurred after this decision)
        try:
            downstream = conn.execute(
                """SELECT event_id, event_type, timestamp
                   FROM canonical_events
                   WHERE timestamp > ?
                   ORDER BY timestamp ASC
                   LIMIT 5""",
                (decision.timestamp,),
            ).fetchall()
            downstream_events = [
                {"event_id": r[0], "event_type": r[1], "timestamp": r[2]} for r in downstream
            ]
        except Exception:
            downstream_events = []

    return {
        "decision": decision,
        "linked_events": events,
        "reasoning": decision.reasoning,
        "policy_applied": decision.policy_applied,
        "causal_context": {
            "upstream_events": upstream_events,
            "downstream_events": downstream_events,
        },
    }


def trace_event(event_id: str) -> dict[str, Any]:
    """Trace full causal chain: Event → Decision(s) → Linked Events.

    Args:
        event_id: Event ID to trace

    Returns:
        Dict with event, decisions made, and causal chain
    """
    with _connect() as conn:
        # Get the event
        event_row = conn.execute(
            """SELECT event_id, event_type, timestamp, payload, severity
               FROM canonical_events
               WHERE event_id = ?""",
            (event_id,),
        ).fetchone()

        if not event_row:
            return {"error": f"Event {event_id} not found"}

        event = {
            "event_id": event_row[0],
            "event_type": event_row[1],
            "timestamp": event_row[2],
            "payload": json.loads(event_row[3]) if event_row[3] else {},
            "severity": event_row[4],
        }

        # Get decisions triggered by this event, sourced from
        # payload.triggered_event_id (replaces the dropped decision_event_link
        # join table).
        decision_rows = conn.execute(
            """SELECT payload
               FROM business_canonical_events
               WHERE event_type = ? AND json_extract(payload, '$.triggered_event_id') = ?""",
            (_DECISION_EVENT_TYPE, event_id),
        ).fetchall()

        decisions = []
        for (d_payload_json,) in decision_rows:
            d_payload = json.loads(d_payload_json) if d_payload_json else {}
            decisions.append(
                {
                    "decision_id": d_payload.get("decision_id"),
                    "decision_type": d_payload.get("decision_type"),
                    "outcome": _parse_json_field(d_payload.get("outcome")),
                    "reasoning": _parse_json_field(d_payload.get("reasoning")) or {},
                    "confidence": d_payload.get("confidence"),
                    "policy_applied": d_payload.get("policy_applied"),
                    "relation_type": "triggered",
                }
            )

        # Get events caused by these decisions
        caused_events = []
        for decision in decisions:
            caused = conn.execute(
                """SELECT e.event_id, e.event_type, e.timestamp
                   FROM canonical_events e
                   WHERE json_extract(e.payload, '$.decision_id') = ?""",
                (decision["decision_id"],),
            ).fetchall()

            for e in caused:
                caused_events.append(
                    {
                        "event_id": e[0],
                        "event_type": e[1],
                        "timestamp": e[2],
                        "caused_by_decision": decision["decision_id"],
                    }
                )

    return {
        "event": event,
        "decisions_made": decisions,
        "caused_events": caused_events,
        "causal_chain_length": len(decisions) + len(caused_events),
    }


def audit_decisions(decision_type: str) -> dict[str, Any]:
    """Audit decisions of a specific type.

    Args:
        decision_type: Decision type to audit

    Returns:
        Dict with outcome distribution, reasoning factors, and confidence histogram
    """
    with _connect() as conn:
        # Get all decisions of this type
        rows = conn.execute(
            """SELECT payload
               FROM business_canonical_events
               WHERE event_type = ? AND json_extract(payload, '$.decision_type') = ?""",
            (_DECISION_EVENT_TYPE, decision_type),
        ).fetchall()

        if not rows:
            return {
                "decision_type": decision_type,
                "total_decisions": 0,
                "error": "No decisions of this type found",
            }

        # Count outcomes
        outcome_counts: dict[str, int] = {}
        reasoning_factors: dict[str, dict[str, int]] = {}
        confidence_buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        policies_used: dict[str, int] = {}

        for (payload_json,) in rows:
            payload = json.loads(payload_json) if payload_json else {}
            outcome = _parse_json_field(payload.get("outcome"))
            reasoning = _parse_json_field(payload.get("reasoning")) or {}
            confidence = payload.get("confidence")
            policy = payload.get("policy_applied")

            # Count outcomes
            outcome_key = str(outcome)
            outcome_counts[outcome_key] = outcome_counts.get(outcome_key, 0) + 1

            # Extract reasoning factors
            if isinstance(reasoning, dict):
                for key, value in reasoning.items():
                    if key not in reasoning_factors:
                        reasoning_factors[key] = {}
                    value_key = str(value)
                    reasoning_factors[key][value_key] = reasoning_factors[key].get(value_key, 0) + 1

            # Bucket confidence
            if confidence is not None:
                if confidence < 0.2:
                    confidence_buckets["0.0-0.2"] += 1
                elif confidence < 0.4:
                    confidence_buckets["0.2-0.4"] += 1
                elif confidence < 0.6:
                    confidence_buckets["0.4-0.6"] += 1
                elif confidence < 0.8:
                    confidence_buckets["0.6-0.8"] += 1
                else:
                    confidence_buckets["0.8-1.0"] += 1

            # Count policies
            policies_used[policy] = policies_used.get(policy, 0) + 1

    return {
        "decision_type": decision_type,
        "total_decisions": len(rows),
        "outcome_distribution": outcome_counts,
        "common_reasoning_factors": reasoning_factors,
        "confidence_histogram": confidence_buckets,
        "policies_used": policies_used,
    }
