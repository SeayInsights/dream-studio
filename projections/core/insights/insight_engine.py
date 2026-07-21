"""InsightEngine - Generates actionable insights from analytics data

WO-GF-READINESS-INSIGHTS: InsightEngine's method groups are implemented as mixins
in the sibling insight_engine_* modules; this file wires them together and keeps
the orchestrating entry point (__init__, generate_insights). Public import path
``from projections.core.insights.insight_engine import InsightEngine`` is unchanged.
"""

from datetime import UTC, datetime
from typing import Any

from .insight_engine_cross_project import _CrossProjectMixin
from .insight_engine_opportunities_risks import _OpportunitiesRisksMixin
from .insight_engine_scoring import _ScoringMixin
from .insight_engine_strengths_issues import _StrengthsIssuesMixin

__all__ = ["InsightEngine"]


class InsightEngine(
    _StrengthsIssuesMixin,
    _OpportunitiesRisksMixin,
    _ScoringMixin,
    _CrossProjectMixin,
):
    """Main insight generation engine - orchestrates analysis and recommendations"""

    def __init__(self):
        """Initialize InsightEngine"""
        self.insight_categories = ["strengths", "issues", "opportunities", "risks"]

    def generate_insights(
        self, metrics: dict[str, Any], analysis: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Generate comprehensive insights from metrics and analysis

        Args:
            metrics: Raw metrics from collectors
            analysis: Analysis results from analyzers

        Returns:
            Dict containing:
                - strengths: List[Dict] - What's working well
                - issues: List[Dict] - Problems detected
                - opportunities: List[Dict] - Growth potential
                - risks: List[Dict] - Warning signs
                - summary: str - Executive summary
                - confidence_score: float - Overall confidence (0-1)
        """
        insights = {
            "strengths": self._identify_strengths(metrics, analysis),
            "issues": self._identify_issues(metrics, analysis),
            "opportunities": self._identify_opportunities(metrics, analysis),
            "risks": self._identify_risks(metrics, analysis),
            "generated_at": datetime.now(UTC).isoformat(),
            "version": "1.0",
        }

        # Generate summary
        insights["summary"] = self._generate_summary(insights)

        # Calculate confidence score
        insights["confidence_score"] = self._calculate_confidence(metrics, analysis)

        return insights
