"""Decision coverage model and computation."""

from __future__ import annotations
from dataclasses import dataclass
from typing import List

from core.event_store.studio_db import _connect


@dataclass
class DecisionCoverageReport:
    """Coverage analysis of decision instrumentation."""

    total_behavioral_decision_points: int
    instrumented_decisions: int
    missing_decisions: List[dict]
    orphan_events: List[dict]
    unlinked_decisions: List[dict]
    coverage_ratio: float


def compute_coverage() -> DecisionCoverageReport:
    """Compute decision coverage from database state.

    Returns:
        DecisionCoverageReport with current system state
    """
    with _connect() as conn:
        # Count instrumented decisions
        instrumented = conn.execute("SELECT COUNT(*) FROM decision_log").fetchone()[0]

        # Find decisions without event links
        unlinked = conn.execute("""SELECT d.decision_id, d.decision_type, d.source_subsystem
               FROM decision_log d
               WHERE NOT EXISTS (
                   SELECT 1 FROM decision_event_link l
                   WHERE l.decision_id = d.decision_id
               )""").fetchall()

        unlinked_decisions = [
            {"decision_id": r[0], "decision_type": r[1], "subsystem": r[2]} for r in unlinked
        ]

        # Find events without decision links
        orphan_events_rows = conn.execute("""SELECT e.event_id, e.event_type, e.timestamp
               FROM canonical_events e
               WHERE e.event_type NOT IN (
                   'system.startup', 'system.shutdown', 'metric.recorded'
               )
               AND NOT EXISTS (
                   SELECT 1 FROM decision_event_link l
                   WHERE l.event_id = e.event_id
               )
               LIMIT 100""").fetchall()

        orphan_events = [
            {"event_id": r[0], "event_type": r[1], "timestamp": r[2]} for r in orphan_events_rows
        ]

    # Note: total_behavioral_decision_points will be populated by discovery.py
    # For now, use placeholder based on instrumented count
    total_estimated = max(instrumented * 3, 20)  # Heuristic: we've covered ~33%

    coverage_ratio = instrumented / total_estimated if total_estimated > 0 else 0.0

    return DecisionCoverageReport(
        total_behavioral_decision_points=total_estimated,
        instrumented_decisions=instrumented,
        missing_decisions=[],  # Populated by audit.py
        orphan_events=orphan_events,
        unlinked_decisions=unlinked_decisions,
        coverage_ratio=coverage_ratio,
    )
