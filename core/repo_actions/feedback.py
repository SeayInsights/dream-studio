"""Feedback evaluation engine for action effectiveness."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List

from core.config.database import transaction
from .executor import ActionExecution


@dataclass
class ActionFeedback:
    """Feedback metrics for an executed action."""

    execution_id: str
    action_id: str

    structural_impact: Dict[str, float] = field(default_factory=dict)
    decision_impact: Dict[str, float] = field(default_factory=dict)
    risk_impact: Dict[str, float] = field(default_factory=dict)
    system_health_delta: Dict[str, float] = field(default_factory=dict)

    overall_effectiveness: float = 0.0  # 0.0-1.0
    confirmed_effective: bool = False


class FeedbackEngine:
    """Evaluate action effectiveness and store feedback."""

    def __init__(self):
        self.feedbacks: List[ActionFeedback] = []

    def evaluate_action_effectiveness(self, execution: ActionExecution) -> ActionFeedback:
        """Evaluate effectiveness of an executed action.

        Args:
            execution: Action execution record

        Returns:
            ActionFeedback with computed metrics
        """
        feedback = ActionFeedback(
            execution_id=execution.execution_id, action_id=execution.action_id
        )

        # A. Structural Impact
        feedback.structural_impact = self._compute_structural_impact(execution)

        # B. Decision Impact
        feedback.decision_impact = self._compute_decision_impact(execution)

        # C. Risk Impact
        feedback.risk_impact = self._compute_risk_impact(execution)

        # D. System Health Delta
        feedback.system_health_delta = self._compute_system_health_delta(execution)

        # Overall effectiveness (weighted average)
        feedback.overall_effectiveness = self._compute_overall_effectiveness(
            feedback.structural_impact,
            feedback.decision_impact,
            feedback.risk_impact,
            feedback.system_health_delta,
        )

        # Confirm if effective (threshold: 0.5)
        feedback.confirmed_effective = feedback.overall_effectiveness > 0.5

        self.feedbacks.append(feedback)
        return feedback

    def _compute_structural_impact(self, execution: ActionExecution) -> Dict[str, float]:
        """Compute structural impact metrics.

        Args:
            execution: Action execution

        Returns:
            Structural impact metrics
        """
        before = execution.before_state
        after = execution.after_state

        metrics = {}

        # Coupling delta
        coupling_before = before.get("coupling_score", 0)
        coupling_after = after.get("coupling_score", 0)
        if coupling_before > 0:
            coupling_delta = (coupling_before - coupling_after) / coupling_before
            metrics["coupling_reduction"] = max(0, coupling_delta)

        # Module dependency change
        # (Would compute from actual dependency graph)
        metrics["dependency_delta"] = 0.0

        return metrics

    def _compute_decision_impact(self, execution: ActionExecution) -> Dict[str, float]:
        """Compute decision/transparency impact metrics.

        Args:
            execution: Action execution

        Returns:
            Decision impact metrics
        """
        before = execution.before_state
        after = execution.after_state

        metrics = {}

        # Instrumentation coverage change
        coverage_before = before.get("instrumentation_coverage", 0.0)
        coverage_after = after.get("instrumentation_coverage", 0.0)
        metrics["coverage_increase"] = coverage_after - coverage_before

        # Orphan decision delta
        orphans_before = before.get("orphan_decision_count", 0)
        orphans_after = after.get("orphan_decision_count", 0)
        metrics["orphan_reduction"] = orphans_before - orphans_after

        return metrics

    def _compute_risk_impact(self, execution: ActionExecution) -> Dict[str, float]:
        """Compute risk impact metrics.

        Args:
            execution: Action execution

        Returns:
            Risk impact metrics
        """
        before = execution.before_state
        after = execution.after_state

        metrics = {}

        # Audit risk change
        risk_before = before.get("risk_score", 0.0)
        risk_after = after.get("risk_score", 0.0)
        metrics["risk_reduction"] = risk_before - risk_after

        # Compliance improvement
        # (Would compute from compliance audit results)
        metrics["compliance_score_delta"] = 0.0

        return metrics

    def _compute_system_health_delta(self, execution: ActionExecution) -> Dict[str, float]:
        """Compute overall system health delta.

        Args:
            execution: Action execution

        Returns:
            System health metrics
        """
        metrics = {}

        # LOC change (smaller is often better for maintainability)
        before_loc = execution.before_state.get("loc", 0)
        after_loc = execution.after_state.get("loc", 0)
        if before_loc > 0:
            loc_delta = (before_loc - after_loc) / before_loc
            metrics["maintainability_delta"] = loc_delta * 0.1  # Small weight

        # Overall delta from diff summary
        if execution.diff_summary and execution.diff_summary.get("deltas"):
            metrics["total_metrics_improved"] = len(
                [
                    k
                    for k, v in execution.diff_summary["deltas"].items()
                    if v.get("delta", 0) < 0  # Negative delta = improvement for risk/coupling
                ]
            )

        return metrics

    def _compute_overall_effectiveness(
        self,
        structural: Dict[str, float],
        decision: Dict[str, float],
        risk: Dict[str, float],
        health: Dict[str, float],
    ) -> float:
        """Compute overall effectiveness score.

        Args:
            structural: Structural impact metrics
            decision: Decision impact metrics
            risk: Risk impact metrics
            health: System health metrics

        Returns:
            Overall effectiveness (0.0-1.0)
        """
        # Weighted sum of positive impacts
        weights = {"structural": 0.30, "decision": 0.25, "risk": 0.30, "health": 0.15}

        # Average positive metrics per category
        structural_score = self._average_positive(structural)
        decision_score = self._average_positive(decision)
        risk_score = self._average_positive(risk)
        health_score = self._average_positive(health)

        total = (
            weights["structural"] * structural_score
            + weights["decision"] * decision_score
            + weights["risk"] * risk_score
            + weights["health"] * health_score
        )

        return min(1.0, max(0.0, total))

    def _average_positive(self, metrics: Dict[str, float]) -> float:
        """Average positive metric values.

        Args:
            metrics: Metrics dict

        Returns:
            Average of positive values
        """
        if not metrics:
            return 0.0

        positive_values = [v for v in metrics.values() if v > 0]
        if not positive_values:
            return 0.0

        return sum(positive_values) / len(positive_values)

    def store_feedback(self, feedback: ActionFeedback):
        """Store feedback in database.

        Args:
            feedback: Action feedback to store
        """
        try:
            with transaction() as conn:
                # Ensure table exists
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS action_feedback (
                        execution_id TEXT,
                        action_id TEXT,
                        metric_type TEXT,
                        before_value REAL,
                        after_value REAL,
                        delta REAL,
                        timestamp TEXT
                    )
                """)

                timestamp = feedback.execution_id  # Use execution timestamp

                # Store structural metrics
                for metric, value in feedback.structural_impact.items():
                    conn.execute(
                        """INSERT INTO action_feedback
                           (execution_id, action_id, metric_type, before_value, after_value, delta, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            feedback.execution_id,
                            feedback.action_id,
                            f"structural.{metric}",
                            0.0,
                            value,
                            value,
                            timestamp,
                        ),
                    )

                # Store decision metrics
                for metric, value in feedback.decision_impact.items():
                    conn.execute(
                        """INSERT INTO action_feedback
                           (execution_id, action_id, metric_type, before_value, after_value, delta, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            feedback.execution_id,
                            feedback.action_id,
                            f"decision.{metric}",
                            0.0,
                            value,
                            value,
                            timestamp,
                        ),
                    )

                # Store risk metrics
                for metric, value in feedback.risk_impact.items():
                    conn.execute(
                        """INSERT INTO action_feedback
                           (execution_id, action_id, metric_type, before_value, after_value, delta, timestamp)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            feedback.execution_id,
                            feedback.action_id,
                            f"risk.{metric}",
                            0.0,
                            value,
                            value,
                            timestamp,
                        ),
                    )

                # Store overall effectiveness
                conn.execute(
                    """INSERT INTO action_feedback
                       (execution_id, action_id, metric_type, before_value, after_value, delta, timestamp)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        feedback.execution_id,
                        feedback.action_id,
                        "overall_effectiveness",
                        0.0,
                        feedback.overall_effectiveness,
                        feedback.overall_effectiveness,
                        timestamp,
                    ),
                )

        except Exception as e:
            print(f"Warning: Failed to store feedback: {e}")

    def get_effectiveness_statistics(self) -> Dict[str, any]:
        """Get aggregate effectiveness statistics.

        Returns:
            Statistics dict
        """
        if not self.feedbacks:
            return {"total_actions": 0, "effective_count": 0, "average_effectiveness": 0.0}

        effective = sum(1 for f in self.feedbacks if f.confirmed_effective)
        avg_eff = sum(f.overall_effectiveness for f in self.feedbacks) / len(self.feedbacks)

        return {
            "total_actions": len(self.feedbacks),
            "effective_count": effective,
            "ineffective_count": len(self.feedbacks) - effective,
            "average_effectiveness": avg_eff,
            "effectiveness_rate": effective / len(self.feedbacks) if self.feedbacks else 0.0,
        }
