"""Decision query engine for causal analysis and explainability."""

from __future__ import annotations
import json
from typing import Any, Optional

from core.event_store.studio_db import _connect
from .schema import Decision


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
    conditions = []
    params = []

    if decision_type:
        conditions.append("decision_type = ?")
        params.append(decision_type)

    if subsystem:
        conditions.append("source_subsystem = ?")
        params.append(subsystem)

    if min_confidence is not None:
        conditions.append("confidence >= ?")
        params.append(min_confidence)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"""
        SELECT decision_id, decision_type, context, outcome, reasoning,
               confidence, policy_applied, source_subsystem, timestamp
        FROM decision_log
        {where_clause}
        ORDER BY timestamp DESC
        LIMIT ?
    """
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()

    decisions = []
    for row in rows:
        decisions.append(
            Decision(
                decision_id=row[0],
                decision_type=row[1],
                context=json.loads(row[2]) if row[2] else {},
                outcome=json.loads(row[3]) if row[3] else None,
                reasoning=json.loads(row[4]) if row[4] else {},
                confidence=row[5],
                policy_applied=row[6],
                source_subsystem=row[7],
                timestamp=row[8],
            )
        )

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
            """SELECT decision_id, decision_type, context, outcome, reasoning,
                      confidence, policy_applied, source_subsystem, timestamp
               FROM decision_log
               WHERE decision_id = ?""",
            (decision_id,),
        ).fetchone()

        if not row:
            return {"error": f"Decision {decision_id} not found"}

        decision = Decision(
            decision_id=row[0],
            decision_type=row[1],
            context=json.loads(row[2]) if row[2] else {},
            outcome=json.loads(row[3]) if row[3] else None,
            reasoning=json.loads(row[4]) if row[4] else {},
            confidence=row[5],
            policy_applied=row[6],
            source_subsystem=row[7],
            timestamp=row[8],
        )

        # Get linked events
        linked_events = conn.execute(
            """SELECT e.event_id, e.event_type, e.timestamp, e.payload, l.relation_type
               FROM decision_event_link l
               JOIN canonical_events e ON l.event_id = e.event_id
               WHERE l.decision_id = ?""",
            (decision_id,),
        ).fetchall()

        events = []
        for event_row in linked_events:
            events.append(
                {
                    "event_id": event_row[0],
                    "event_type": event_row[1],
                    "timestamp": event_row[2],
                    "payload": json.loads(event_row[3]) if event_row[3] else {},
                    "relation_type": event_row[4],
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

        # Get decisions linked to this event
        decision_rows = conn.execute(
            """SELECT d.decision_id, d.decision_type, d.outcome, d.reasoning,
                      d.confidence, d.policy_applied, l.relation_type
               FROM decision_event_link l
               JOIN decision_log d ON l.decision_id = d.decision_id
               WHERE l.event_id = ?""",
            (event_id,),
        ).fetchall()

        decisions = []
        for d_row in decision_rows:
            decisions.append(
                {
                    "decision_id": d_row[0],
                    "decision_type": d_row[1],
                    "outcome": json.loads(d_row[2]) if d_row[2] else None,
                    "reasoning": json.loads(d_row[3]) if d_row[3] else {},
                    "confidence": d_row[4],
                    "policy_applied": d_row[5],
                    "relation_type": d_row[6],
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
            """SELECT outcome, reasoning, confidence, policy_applied
               FROM decision_log
               WHERE decision_type = ?""",
            (decision_type,),
        ).fetchall()

        if not rows:
            return {
                "decision_type": decision_type,
                "total_decisions": 0,
                "error": "No decisions of this type found",
            }

        # Count outcomes
        outcome_counts = {}
        reasoning_factors = {}
        confidence_buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
        policies_used = {}

        for row in rows:
            outcome = json.loads(row[0]) if row[0] else None
            reasoning = json.loads(row[1]) if row[1] else {}
            confidence = row[2]
            policy = row[3]

            # Count outcomes
            outcome_key = str(outcome)
            outcome_counts[outcome_key] = outcome_counts.get(outcome_key, 0) + 1

            # Extract reasoning factors
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
