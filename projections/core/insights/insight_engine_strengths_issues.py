"""InsightEngine mixin: strength and issue identification.

WO-GF-READINESS-INSIGHTS: split from ``projections/core/insights/insight_engine.py``.
Methods extracted verbatim onto a mixin; ``InsightEngine`` inherits it.
"""

from typing import Any


class _StrengthsIssuesMixin:
    def _identify_strengths(
        self, metrics: dict[str, Any], analysis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Identify what's working well"""
        strengths = []

        # High performing skills
        if "performance" in analysis and "high_performers" in analysis["performance"]:
            high_performers = analysis["performance"]["high_performers"]
            if high_performers:
                top_skills = ", ".join(high_performers[:3])
                remaining = len(high_performers) - 3
                skill_list = f"{top_skills} and {remaining} more" if remaining > 0 else top_skills
                strengths.append(
                    {
                        "category": "skill_performance",
                        "title": f"{len(high_performers)} high-performing skills",
                        "description": (
                            f"{skill_list} all maintain above 90% success rates. "
                            f"This indicates reliable, well-tuned workflows that consistently deliver results."
                        ),
                        "impact": "high",
                        "evidence": {"skills": high_performers},
                    }
                )

        # High productivity
        if "sessions" in metrics:
            total_sessions = metrics["sessions"].get("total_sessions", 0)
            success_rate = metrics["sessions"].get("success_rate", 0) * 100

            if total_sessions > 50 and success_rate > 80:
                strengths.append(
                    {
                        "category": "productivity",
                        "title": f"Strong productivity: {total_sessions} sessions",
                        "description": (
                            f"Across {total_sessions} sessions, {success_rate:.0f}% completed successfully. "
                            f"This level of consistency shows the workflow is mature and producing reliable output."
                        ),
                        "impact": "high",
                        "evidence": {"sessions": total_sessions, "success_rate": success_rate},
                    }
                )

        # Positive trends
        if "trends" in analysis:
            for metric_name, trend_data in analysis["trends"].items():
                if trend_data.get("trend") == "increasing" and trend_data.get("slope", 0) > 0:
                    slope = trend_data.get("slope", 0)
                    readable_name = metric_name.replace("_", " ")
                    strengths.append(
                        {
                            "category": "growth",
                            "title": f"{metric_name.capitalize()} trending upward",
                            "description": (
                                f"{readable_name.capitalize()} is growing at {slope:.2f} per period, "
                                f"indicating increasing adoption and expanding usage over time."
                            ),
                            "impact": "medium",
                            "evidence": trend_data,
                        }
                    )

        # Cost efficiency
        if "tokens" in metrics:
            total_cost = metrics["tokens"].get("total_cost_usd")
            total_sessions = metrics.get("sessions", {}).get("total_sessions", 1)
            cost_per_session = (
                total_cost / total_sessions
                if total_cost is not None and total_sessions > 0
                else None
            )

            if cost_per_session is not None and cost_per_session < 0.50:
                strengths.append(
                    {
                        "category": "cost_efficiency",
                        "title": f"Excellent cost efficiency: ${cost_per_session:.2f}/session",
                        "description": (
                            f"At ${cost_per_session:.2f} per session (${total_cost:.2f} total across {total_sessions} sessions), "
                            f"token costs are well-controlled. This suggests efficient prompt design and appropriate model selection."
                        ),
                        "impact": "medium",
                        "evidence": {
                            "cost_per_session": cost_per_session,
                            "total_cost": total_cost,
                        },
                    }
                )

        return sorted(
            strengths,
            key=lambda x: {"high": 3, "medium": 2, "low": 1}.get(x["impact"], 0),
            reverse=True,
        )

    def _identify_issues(
        self, metrics: dict[str, Any], analysis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Identify problems and underperformance"""
        issues = []

        # Underperforming skills
        if "performance" in analysis and "underperformers" in analysis["performance"]:
            underperformers = analysis["performance"]["underperformers"]
            if underperformers:
                top_under = ", ".join(underperformers[:3])
                remaining = len(underperformers) - 3
                skill_list = f"{top_under} and {remaining} more" if remaining > 0 else top_under
                issues.append(
                    {
                        "category": "skill_performance",
                        "title": f"{len(underperformers)} underperforming skills",
                        "description": (
                            f"{skill_list} have success rates below 70%. "
                            f"These skills may have unclear prompts, missing context, or hit edge cases that need handling."
                        ),
                        "severity": "high",
                        "evidence": {"skills": underperformers},
                        "recommended_action": "Review error patterns in these skills' session logs and refine their instructions",
                    }
                )

        # Anomalies detected
        if "anomalies" in analysis:
            anomaly_data = analysis["anomalies"]
            anomaly_count = anomaly_data.get("anomaly_count", 0)
            if anomaly_data.get("overall_health") == "critical":
                issues.append(
                    {
                        "category": "anomalies",
                        "title": f"Critical anomalies detected ({anomaly_count})",
                        "description": (
                            f"{anomaly_count} data points fall significantly outside normal ranges. "
                            f"This may indicate broken workflows, misconfigured skills, or unusual usage spikes that need investigation."
                        ),
                        "severity": "critical",
                        "evidence": anomaly_data,
                        "recommended_action": "Investigate root causes of outliers and trend breaks",
                    }
                )
            elif anomaly_data.get("overall_health") == "warning":
                issues.append(
                    {
                        "category": "anomalies",
                        "title": f"Anomalies detected ({anomaly_count})",
                        "description": (
                            f"{anomaly_count} unusual patterns found. These aren't critical yet but could indicate "
                            f"emerging issues worth monitoring before they escalate."
                        ),
                        "severity": "medium",
                        "evidence": anomaly_data,
                        "recommended_action": "Monitor for recurring patterns in the next few sessions",
                    }
                )

        # Negative trends
        if "trends" in analysis:
            for metric_name, trend_data in analysis["trends"].items():
                if trend_data.get("trend") == "decreasing" and trend_data.get("slope", 0) < -1:
                    slope = trend_data.get("slope", 0)
                    readable_name = metric_name.replace("_", " ")
                    issues.append(
                        {
                            "category": "decline",
                            "title": f"{metric_name.capitalize()} declining",
                            "description": (
                                f"{readable_name.capitalize()} is dropping at {slope:.2f} per period. "
                                f"If this trend continues, it could signal reduced effectiveness or disengagement."
                            ),
                            "severity": "medium",
                            "evidence": trend_data,
                            "recommended_action": f"Review recent changes that may have caused the {readable_name} decline",
                        }
                    )

        # Low success rate
        if "sessions" in metrics:
            total = metrics["sessions"].get("total_sessions", 0)
            success_rate = metrics["sessions"].get("success_rate", 0) * 100
            completed = metrics["sessions"].get("outcomes", {}).get("completed", 0)
            failed = total - completed if total > 0 else 0

            if success_rate < 70 and total > 10:
                issues.append(
                    {
                        "category": "quality",
                        "title": f"Low success rate: {success_rate:.1f}%",
                        "description": (
                            f"Only {completed} of {total} sessions completed successfully ({failed} did not complete). "
                            f"This suggests sessions are being abandoned, timing out, or hitting errors before finishing."
                        ),
                        "severity": "high",
                        "evidence": {
                            "success_rate": success_rate,
                            "completed": completed,
                            "total": total,
                        },
                        "recommended_action": "Review incomplete session logs to identify common failure points",
                    }
                )

        return sorted(
            issues,
            key=lambda x: {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(x["severity"], 0),
            reverse=True,
        )
