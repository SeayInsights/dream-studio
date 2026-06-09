"""Decision emission with causal event linking."""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from core.config.database import transaction
from .schema import Decision


def emit_decision(
    decision_type: str,
    context: dict,
    outcome: Any,
    reasoning: dict,
    confidence: float,
    policy_applied: str,
    source_subsystem: str,
    event_id: Optional[str] = None,
) -> Decision:
    """Emit a decision to the decision log with optional event linkage.

    Args:
        decision_type: Type of decision (e.g., "trust_score.assignment")
        context: Input context that led to decision
        outcome: The actual decision made
        reasoning: Structured explanation
        confidence: Confidence score (0.0-1.0)
        policy_applied: Policy name/version
        source_subsystem: Subsystem making the decision
        event_id: Optional event ID to link this decision to

    Returns:
        Decision object

    Raises:
        RuntimeError: If decision write or event link fails
    """
    decision_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()

    decision = Decision(
        decision_id=decision_id,
        decision_type=decision_type,
        context=context,
        outcome=outcome,
        reasoning=reasoning,
        confidence=confidence,
        policy_applied=policy_applied,
        timestamp=timestamp,
        source_subsystem=source_subsystem,
    )

    try:
        with transaction() as conn:
            # Write decision to decision_log
            conn.execute(
                """INSERT INTO decision_log
                   (decision_id, decision_type, context, outcome, reasoning,
                    confidence, policy_applied, source_subsystem, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    decision_id,
                    decision_type,
                    json.dumps(context),
                    json.dumps(outcome),
                    json.dumps(reasoning),
                    confidence,
                    policy_applied,
                    source_subsystem,
                    timestamp,
                ),
            )

            # Link to event if provided
            if event_id:
                conn.execute(
                    """INSERT INTO decision_event_link
                       (decision_id, event_id, relation_type)
                       VALUES (?, ?, ?)""",
                    (decision_id, event_id, "triggered"),
                )

    except Exception as e:
        raise RuntimeError(
            f"Failed to emit decision {decision_id} (type={decision_type}). " f"Error: {e}"
        ) from e

    _emit_decision_telemetry(decision, event_id)
    return decision


def _emit_decision_telemetry(decision: Decision, event_id: Optional[str]) -> None:
    """Best-effort dual-write from canonical decision_log to telemetry spine."""

    try:
        from core.telemetry.emitters import TelemetryContext, emit_decision_record

        reasoning = decision.reasoning if isinstance(decision.reasoning, dict) else {}
        context = decision.context if isinstance(decision.context, dict) else {}
        outcome = decision.outcome
        if isinstance(outcome, dict):
            selected_option = (
                outcome.get("selected_option") or outcome.get("decision") or outcome.get("outcome")
            )
            outcome_impact = outcome.get("outcome_impact")
            route_impact = outcome.get("route_impact")
        else:
            selected_option = str(outcome)
            outcome_impact = None
            route_impact = None
        emit_decision_record(
            decision_type=decision.decision_type,
            decision_status="recorded",
            selected_option=str(selected_option) if selected_option is not None else None,
            rationale=str(reasoning.get("rationale") or reasoning.get("reason") or ""),
            options_considered=reasoning.get("options_considered")
            or context.get("options_considered")
            or [],
            route_impact=str(
                route_impact or reasoning.get("route_impact") or context.get("route_impact") or ""
            ),
            outcome_impact=str(outcome_impact or reasoning.get("outcome_impact") or ""),
            research_id=context.get("research_id"),
            operator_required=bool(
                reasoning.get("operator_required") or context.get("operator_required")
            ),
            approval_required=bool(
                reasoning.get("approval_required") or context.get("approval_required")
            ),
            prompt_required=bool(
                reasoning.get("prompt_required") or context.get("prompt_required")
            ),
            source_decision_id=decision.decision_id,
            context=TelemetryContext(
                project_id=str(context.get("project_id") or "dream-studio"),
                milestone_id=context.get("milestone_id"),
                task_id=context.get("task_id"),
                process_run_id=context.get("process_run_id"),
                source_refs=("core/decisions/emitter.py",),
                evidence_refs=(f"decision_log:{decision.decision_id}",),
            ),
            source_refs=[f"decision_log:{decision.decision_id}"],
            evidence_refs=[
                f"decision_log:{decision.decision_id}",
                *([event_id] if event_id else []),
            ],
            metadata={
                "confidence": decision.confidence,
                "policy_applied": decision.policy_applied,
                "source_subsystem": decision.source_subsystem,
            },
        )
    except Exception:
        return
