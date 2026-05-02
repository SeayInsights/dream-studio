"""InsightEngine - Generates actionable insights from analytics data"""
from typing import Dict, List, Any
from datetime import datetime, timezone


class InsightEngine:
    """Main insight generation engine - orchestrates analysis and recommendations"""

    def __init__(self):
        """Initialize InsightEngine"""
        self.insight_categories = ["strengths", "issues", "opportunities", "risks"]

    def generate_insights(self, metrics: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
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
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "version": "1.0"
        }

        # Generate summary
        insights["summary"] = self._generate_summary(insights)

        # Calculate confidence score
        insights["confidence_score"] = self._calculate_confidence(metrics, analysis)

        return insights

    def _identify_strengths(self, metrics: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify what's working well"""
        strengths = []

        # High performing skills
        if "performance" in analysis and "high_performers" in analysis["performance"]:
            high_performers = analysis["performance"]["high_performers"]
            if high_performers:
                top_skills = ', '.join(high_performers[:3])
                remaining = len(high_performers) - 3
                skill_list = f"{top_skills} and {remaining} more" if remaining > 0 else top_skills
                strengths.append({
                    "category": "skill_performance",
                    "title": f"{len(high_performers)} high-performing skills",
                    "description": (
                        f"{skill_list} all maintain above 90% success rates. "
                        f"This indicates reliable, well-tuned workflows that consistently deliver results."
                    ),
                    "impact": "high",
                    "evidence": {"skills": high_performers}
                })

        # High productivity
        if "sessions" in metrics:
            total_sessions = metrics["sessions"].get("total_sessions", 0)
            success_rate = metrics["sessions"].get("success_rate", 0) * 100

            if total_sessions > 50 and success_rate > 80:
                strengths.append({
                    "category": "productivity",
                    "title": f"Strong productivity: {total_sessions} sessions",
                    "description": (
                        f"Across {total_sessions} sessions, {success_rate:.0f}% completed successfully. "
                        f"This level of consistency shows the workflow is mature and producing reliable output."
                    ),
                    "impact": "high",
                    "evidence": {"sessions": total_sessions, "success_rate": success_rate}
                })

        # Positive trends
        if "trends" in analysis:
            for metric_name, trend_data in analysis["trends"].items():
                if trend_data.get("trend") == "increasing" and trend_data.get("slope", 0) > 0:
                    slope = trend_data.get("slope", 0)
                    readable_name = metric_name.replace("_", " ")
                    strengths.append({
                        "category": "growth",
                        "title": f"{metric_name.capitalize()} trending upward",
                        "description": (
                            f"{readable_name.capitalize()} is growing at {slope:.2f} per period, "
                            f"indicating increasing adoption and expanding usage over time."
                        ),
                        "impact": "medium",
                        "evidence": trend_data
                    })

        # Cost efficiency
        if "tokens" in metrics:
            total_cost = metrics["tokens"].get("total_cost_usd", 0)
            total_sessions = metrics.get("sessions", {}).get("total_sessions", 1)
            cost_per_session = total_cost / total_sessions if total_sessions > 0 else 0

            if cost_per_session < 0.50:
                strengths.append({
                    "category": "cost_efficiency",
                    "title": f"Excellent cost efficiency: ${cost_per_session:.2f}/session",
                    "description": (
                        f"At ${cost_per_session:.2f} per session (${total_cost:.2f} total across {total_sessions} sessions), "
                        f"token costs are well-controlled. This suggests efficient prompt design and appropriate model selection."
                    ),
                    "impact": "medium",
                    "evidence": {"cost_per_session": cost_per_session, "total_cost": total_cost}
                })

        return sorted(strengths, key=lambda x: {"high": 3, "medium": 2, "low": 1}.get(x["impact"], 0), reverse=True)

    def _identify_issues(self, metrics: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify problems and underperformance"""
        issues = []

        # Underperforming skills
        if "performance" in analysis and "underperformers" in analysis["performance"]:
            underperformers = analysis["performance"]["underperformers"]
            if underperformers:
                top_under = ', '.join(underperformers[:3])
                remaining = len(underperformers) - 3
                skill_list = f"{top_under} and {remaining} more" if remaining > 0 else top_under
                issues.append({
                    "category": "skill_performance",
                    "title": f"{len(underperformers)} underperforming skills",
                    "description": (
                        f"{skill_list} have success rates below 70%. "
                        f"These skills may have unclear prompts, missing context, or hit edge cases that need handling."
                    ),
                    "severity": "high",
                    "evidence": {"skills": underperformers},
                    "recommended_action": "Review error patterns in these skills' session logs and refine their instructions"
                })

        # Anomalies detected
        if "anomalies" in analysis:
            anomaly_data = analysis["anomalies"]
            anomaly_count = anomaly_data.get("anomaly_count", 0)
            if anomaly_data.get("overall_health") == "critical":
                issues.append({
                    "category": "anomalies",
                    "title": f"Critical anomalies detected ({anomaly_count})",
                    "description": (
                        f"{anomaly_count} data points fall significantly outside normal ranges. "
                        f"This may indicate broken workflows, misconfigured skills, or unusual usage spikes that need investigation."
                    ),
                    "severity": "critical",
                    "evidence": anomaly_data,
                    "recommended_action": "Investigate root causes of outliers and trend breaks"
                })
            elif anomaly_data.get("overall_health") == "warning":
                issues.append({
                    "category": "anomalies",
                    "title": f"Anomalies detected ({anomaly_count})",
                    "description": (
                        f"{anomaly_count} unusual patterns found. These aren't critical yet but could indicate "
                        f"emerging issues worth monitoring before they escalate."
                    ),
                    "severity": "medium",
                    "evidence": anomaly_data,
                    "recommended_action": "Monitor for recurring patterns in the next few sessions"
                })

        # Negative trends
        if "trends" in analysis:
            for metric_name, trend_data in analysis["trends"].items():
                if trend_data.get("trend") == "decreasing" and trend_data.get("slope", 0) < -1:
                    slope = trend_data.get("slope", 0)
                    readable_name = metric_name.replace("_", " ")
                    issues.append({
                        "category": "decline",
                        "title": f"{metric_name.capitalize()} declining",
                        "description": (
                            f"{readable_name.capitalize()} is dropping at {slope:.2f} per period. "
                            f"If this trend continues, it could signal reduced effectiveness or disengagement."
                        ),
                        "severity": "medium",
                        "evidence": trend_data,
                        "recommended_action": f"Review recent changes that may have caused the {readable_name} decline"
                    })

        # Low success rate
        if "sessions" in metrics:
            total = metrics["sessions"].get("total_sessions", 0)
            success_rate = metrics["sessions"].get("success_rate", 0) * 100
            completed = metrics["sessions"].get("outcomes", {}).get("completed", 0)
            failed = total - completed if total > 0 else 0

            if success_rate < 70 and total > 10:
                issues.append({
                    "category": "quality",
                    "title": f"Low success rate: {success_rate:.1f}%",
                    "description": (
                        f"Only {completed} of {total} sessions completed successfully ({failed} did not complete). "
                        f"This suggests sessions are being abandoned, timing out, or hitting errors before finishing."
                    ),
                    "severity": "high",
                    "evidence": {"success_rate": success_rate, "completed": completed, "total": total},
                    "recommended_action": "Review incomplete session logs to identify common failure points"
                })

        return sorted(issues, key=lambda x: {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(x["severity"], 0), reverse=True)

    def _identify_opportunities(self, metrics: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify growth and improvement opportunities"""
        opportunities = []

        # Improvement opportunities from performance analysis
        if "performance" in analysis and "improvement_opportunities" in analysis["performance"]:
            opps = analysis["performance"]["improvement_opportunities"]
            for opp in opps[:3]:  # Top 3
                opportunities.append({
                    "category": "optimization",
                    "title": f"Optimize {opp.get('skill', 'skill')}",
                    "description": opp.get("recommendation", "Review and improve"),
                    "potential_impact": "medium",
                    "evidence": opp
                })

        # Underutilized models (if using expensive models rarely)
        if "models" in metrics:
            by_model = metrics["models"].get("by_model", {})
            if "opus" in by_model and by_model["opus"].get("invocations", 0) < 5:
                opportunities.append({
                    "category": "cost_optimization",
                    "title": "Low Opus utilization",
                    "description": "Opus model rarely used - consider for complex tasks to improve quality",
                    "potential_impact": "medium",
                    "evidence": {"opus_usage": by_model["opus"]}
                })

        # Seasonal patterns (for optimization)
        if "trends" in analysis:
            for metric_name, trend_data in analysis["trends"].items():
                if trend_data.get("seasonality_detected"):
                    opportunities.append({
                        "category": "planning",
                        "title": f"Seasonal pattern in {metric_name}",
                        "description": "Predictable patterns detected - optimize resource allocation",
                        "potential_impact": "low",
                        "evidence": trend_data
                    })

        return opportunities

    def _identify_risks(self, metrics: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Identify potential risks and warning signs"""
        risks = []

        # High volatility
        if "trends" in analysis:
            for metric_name, trend_data in analysis["trends"].items():
                volatility = trend_data.get("volatility", 0)
                if volatility > 50:
                    readable_name = metric_name.replace("_", " ")
                    risks.append({
                        "category": "volatility",
                        "title": f"High volatility in {metric_name}",
                        "description": (
                            f"{readable_name.capitalize()} varies by {volatility:.1f}% between periods, "
                            f"making it difficult to predict capacity needs or spot real problems amid the noise."
                        ),
                        "risk_level": "medium",
                        "evidence": trend_data,
                        "mitigation": "Investigate what causes the swings — time of day, task type, or external factors"
                    })

        # Declining forecast
        if "forecast" in analysis:
            forecast_trend = analysis["forecast"].get("trend_direction", "")
            if forecast_trend == "decreasing":
                risks.append({
                    "category": "forecast",
                    "title": "Declining trend forecast",
                    "description": (
                        "Based on recent data, the predictive model projects continued decline. "
                        "Without intervention, key metrics may drop further in the coming periods."
                    ),
                    "risk_level": "high",
                    "evidence": analysis["forecast"],
                    "mitigation": "Identify and address the root causes driving the decline before it accelerates"
                })

        # Cost escalation
        if "tokens" in metrics:
            total_cost = metrics["tokens"].get("total_cost_usd", 0)
            if total_cost > 100:
                risks.append({
                    "category": "cost",
                    "title": f"High total cost: ${total_cost:.2f}",
                    "description": (
                        f"Total token spend has reached ${total_cost:.2f}. While not critical, "
                        f"costs at this level warrant periodic review to ensure spend aligns with value delivered."
                    ),
                    "risk_level": "low",
                    "evidence": {"total_cost": total_cost},
                    "mitigation": "Check if expensive models are being used where cheaper ones would suffice"
                })

        return sorted(risks, key=lambda x: {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(x["risk_level"], 0), reverse=True)

    def _generate_summary(self, insights: Dict[str, Any]) -> str:
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

    def _calculate_confidence(self, metrics: Dict[str, Any], analysis: Dict[str, Any]) -> float:
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
            max_volatility = max((t.get("volatility", 0) for t in analysis["trends"].values()), default=0)
            if max_volatility > 75:
                confidence *= 0.85  # Very unpredictable

        return round(confidence, 2)

    def get_insights_by_category(self, insights: Dict[str, Any], category: str) -> List[Dict[str, Any]]:
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

    def get_high_priority_insights(self, insights: Dict[str, Any]) -> List[Dict[str, Any]]:
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
