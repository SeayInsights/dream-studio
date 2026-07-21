"""InsightEngine mixin: summary, confidence, and insight filtering.

WO-GF-READINESS-INSIGHTS: split from ``projections/core/insights/insight_engine.py``.
Methods extracted verbatim onto a mixin; ``InsightEngine`` inherits it.
"""

from typing import Any


class _ScoringMixin:
    def _generate_summary(self, insights: dict[str, Any]) -> str:
        """Generate executive summary from insights"""
        strengths_count = len(insights["strengths"])
        issues_count = len(insights["issues"])
        opps_count = len(insights["opportunities"])
        risks_count = len(insights["risks"])

        # Overall health assessment
        if issues_count == 0 and strengths_count >= 2:
            health = "Excellent"
        elif issues_count <= 2 and strengths_count >= 1:
            health = "Good"
        elif issues_count > strengths_count:
            health = "Needs Attention"
        else:
            health = "Critical"

        summary = f"{health} overall health. "

        if strengths_count > 0:
            summary += f"{strengths_count} key strengths identified. "

        if issues_count > 0:
            summary += f"{issues_count} issues requiring attention. "
        else:
            summary += "No major issues detected. "

        if opps_count > 0:
            summary += f"{opps_count} optimization opportunities available. "

        if risks_count > 0:
            summary += f"{risks_count} risks to monitor."

        return summary.strip()

    def _calculate_confidence(self, metrics: dict[str, Any], analysis: dict[str, Any]) -> float:
        """
        Calculate confidence score for insights based on data quality

        Returns:
            float: 0-1 confidence score
        """
        confidence = 1.0

        # Reduce confidence if insufficient data
        total_sessions = metrics.get("sessions", {}).get("total_sessions", 0)
        if total_sessions < 10:
            confidence *= 0.5  # Low sample size
        elif total_sessions < 30:
            confidence *= 0.75  # Medium sample size

        # Reduce confidence if high anomaly rate
        if "anomalies" in analysis:
            anomaly_rate = analysis["anomalies"].get("anomaly_rate_pct", 0)
            if anomaly_rate > 25:
                confidence *= 0.8  # High noise in data

        # Reduce confidence if high volatility
        if "trends" in analysis:
            max_volatility = max(
                (t.get("volatility", 0) for t in analysis["trends"].values()), default=0
            )
            if max_volatility > 75:
                confidence *= 0.85  # Very unpredictable

        return round(confidence, 2)

    def get_insights_by_category(
        self, insights: dict[str, Any], category: str
    ) -> list[dict[str, Any]]:
        """
        Filter insights by category

        Args:
            insights: Full insights dict from generate_insights()
            category: One of ["strengths", "issues", "opportunities", "risks"]

        Returns:
            List of insights in that category
        """
        if category not in self.insight_categories:
            return []

        return insights.get(category, [])

    def get_high_priority_insights(self, insights: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Get only high-priority/high-impact insights

        Returns:
            List of critical issues, high-impact strengths, and high-risk items
        """
        high_priority = []

        # Critical/high severity issues
        for issue in insights.get("issues", []):
            if issue.get("severity") in ["critical", "high"]:
                high_priority.append({**issue, "type": "issue"})

        # High impact strengths
        for strength in insights.get("strengths", []):
            if strength.get("impact") == "high":
                high_priority.append({**strength, "type": "strength"})

        # High/critical risks
        for risk in insights.get("risks", []):
            if risk.get("risk_level") in ["critical", "high"]:
                high_priority.append({**risk, "type": "risk"})

        return high_priority
