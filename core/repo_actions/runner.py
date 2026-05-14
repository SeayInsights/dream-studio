"""Execution runner - orchestrates action execution and feedback loop."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List

from .model import RepoActionPlan
from .executor import ActionExecutor
from .feedback import FeedbackEngine, ActionFeedback
from .priority import PRIORITY_WEIGHTS


@dataclass
class ExecutionReport:
    """Report of execution results."""

    repo_name: str
    total_actions: int = 0
    executed_count: int = 0
    success_count: int = 0
    failed_count: int = 0
    partial_count: int = 0

    system_impact_summary: Dict[str, any] = field(default_factory=dict)
    feedbacks: List[ActionFeedback] = field(default_factory=list)


@dataclass
class FeedbackReport:
    """Report of feedback analysis."""

    repo_name: str
    effective_actions: List[str] = field(default_factory=list)
    ineffective_actions: List[str] = field(default_factory=list)
    partially_effective_actions: List[str] = field(default_factory=list)

    metric_improvements: Dict[str, float] = field(default_factory=dict)
    weight_adjustments: Dict[str, float] = field(default_factory=dict)


class ExecutionRunner:
    """Orchestrate action execution and feedback loop."""

    def __init__(self, repo_path: str):
        self.repo_path = repo_path
        self.executor = ActionExecutor(repo_path)
        self.feedback_engine = FeedbackEngine()

    def run_plan(
        self, plan: RepoActionPlan, simulate_only: bool = True, max_actions: int = 10
    ) -> ExecutionReport:
        """Run action plan with simulation and feedback.

        Args:
            plan: Repository action plan
            simulate_only: If True, only simulate (don't actually execute)
            max_actions: Maximum actions to execute

        Returns:
            ExecutionReport with results
        """
        report = ExecutionReport(repo_name=plan.repo_name)
        report.total_actions = len(plan.actions)

        # Execute top N actions
        for action in plan.actions[:max_actions]:
            # 1. Validate
            is_valid, error = self.executor.validate_action(action)
            if not is_valid:
                print(f"Skipping {action.action_id}: {error}")
                report.failed_count += 1
                continue

            # 2. Simulate execution
            execution = self.executor.simulate_execution(action)
            report.executed_count += 1

            # 3. Evaluate effectiveness
            feedback = self.feedback_engine.evaluate_action_effectiveness(execution)
            report.feedbacks.append(feedback)

            # 4. Store feedback
            self.feedback_engine.store_feedback(feedback)

            # 5. Update counts
            if feedback.confirmed_effective:
                report.success_count += 1
            elif feedback.overall_effectiveness > 0.2:
                report.partial_count += 1
            else:
                report.failed_count += 1

        # Compute system impact summary
        report.system_impact_summary = self._compute_system_impact(report.feedbacks)

        return report

    def _compute_system_impact(self, feedbacks: List[ActionFeedback]) -> Dict[str, any]:
        """Compute aggregate system impact.

        Args:
            feedbacks: List of action feedbacks

        Returns:
            System impact summary
        """
        if not feedbacks:
            return {}

        # Aggregate structural improvements
        total_coupling_reduction = sum(
            f.structural_impact.get("coupling_reduction", 0.0) for f in feedbacks
        )

        # Aggregate decision improvements
        total_coverage_increase = sum(
            f.decision_impact.get("coverage_increase", 0.0) for f in feedbacks
        )

        total_orphan_reduction = sum(
            f.decision_impact.get("orphan_reduction", 0) for f in feedbacks
        )

        # Aggregate risk improvements
        total_risk_reduction = sum(f.risk_impact.get("risk_reduction", 0.0) for f in feedbacks)

        return {
            "coupling_reduction": total_coupling_reduction,
            "coverage_increase": total_coverage_increase,
            "orphan_reduction": total_orphan_reduction,
            "risk_reduction": total_risk_reduction,
            "average_effectiveness": sum(f.overall_effectiveness for f in feedbacks)
            / len(feedbacks),
        }

    def generate_feedback_report(self, execution_report: ExecutionReport) -> FeedbackReport:
        """Generate feedback report from execution.

        Args:
            execution_report: Execution report

        Returns:
            Feedback report
        """
        report = FeedbackReport(repo_name=execution_report.repo_name)

        # Categorize actions by effectiveness
        for feedback in execution_report.feedbacks:
            if feedback.confirmed_effective:
                report.effective_actions.append(feedback.action_id)
            elif feedback.overall_effectiveness > 0.2:
                report.partially_effective_actions.append(feedback.action_id)
            else:
                report.ineffective_actions.append(feedback.action_id)

        # Aggregate metric improvements
        report.metric_improvements = execution_report.system_impact_summary

        # Compute weight adjustments (deterministic calibration)
        report.weight_adjustments = self._compute_weight_adjustments(execution_report.feedbacks)

        return report

    def _compute_weight_adjustments(self, feedbacks: List[ActionFeedback]) -> Dict[str, float]:
        """Compute deterministic weight adjustments based on feedback.

        Args:
            feedbacks: List of action feedbacks

        Returns:
            Weight adjustments dict
        """
        adjustments = {"risk": 0.0, "centrality": 0.0, "usage": 0.0, "product_impact": 0.0}

        if not feedbacks:
            return adjustments

        # Analyze which priority factors correlate with effectiveness
        risk_effective = []
        centrality_effective = []

        for feedback in feedbacks:
            if feedback.confirmed_effective:
                # If risk-related metrics improved, risk weight is working
                if feedback.risk_impact.get("risk_reduction", 0) > 0:
                    risk_effective.append(1)
                else:
                    risk_effective.append(0)

                # If structural metrics improved, centrality weight is working
                if feedback.structural_impact.get("coupling_reduction", 0) > 0:
                    centrality_effective.append(1)
                else:
                    centrality_effective.append(0)

        # Compute effectiveness rates
        risk_rate = sum(risk_effective) / len(risk_effective) if risk_effective else 0.5
        centrality_rate = (
            sum(centrality_effective) / len(centrality_effective) if centrality_effective else 0.5
        )

        # Adjust weights (small increments, deterministic)
        # If effectiveness rate > 0.7, slightly increase weight
        # If effectiveness rate < 0.3, slightly decrease weight
        if risk_rate > 0.7:
            adjustments["risk"] = +0.02
        elif risk_rate < 0.3:
            adjustments["risk"] = -0.02

        if centrality_rate > 0.7:
            adjustments["centrality"] = +0.02
        elif centrality_rate < 0.3:
            adjustments["centrality"] = -0.02

        return adjustments

    def apply_weight_adjustments(self, adjustments: Dict[str, float]):
        """Apply weight adjustments to priority model.

        Args:
            adjustments: Weight adjustments to apply

        Note:
            This modifies PRIORITY_WEIGHTS in priority.py
            In production, this would be stored and loaded from config
        """
        for key, adjustment in adjustments.items():
            if key in PRIORITY_WEIGHTS:
                new_weight = PRIORITY_WEIGHTS[key] + adjustment
                # Clamp to reasonable bounds
                new_weight = max(0.05, min(0.60, new_weight))
                PRIORITY_WEIGHTS[key] = new_weight

        # Renormalize to sum to 1.0
        total = sum(PRIORITY_WEIGHTS.values())
        if total > 0:
            for key in PRIORITY_WEIGHTS:
                PRIORITY_WEIGHTS[key] /= total

    def get_effectiveness_stats(self) -> Dict[str, any]:
        """Get aggregate effectiveness statistics.

        Returns:
            Statistics dict
        """
        return self.feedback_engine.get_effectiveness_statistics()
