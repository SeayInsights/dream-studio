"""InsightEngine mixin: opportunity and risk identification.

WO-GF-READINESS-INSIGHTS: split from ``projections/core/insights/insight_engine.py``.
Methods extracted verbatim onto a mixin; ``InsightEngine`` inherits it.
"""

from typing import Any


class _OpportunitiesRisksMixin:
    def _identify_opportunities(
        self, metrics: dict[str, Any], analysis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Identify growth and improvement opportunities"""
        opportunities = []

        # Improvement opportunities from performance analysis
        if "performance" in analysis and "improvement_opportunities" in analysis["performance"]:
            opps = analysis["performance"]["improvement_opportunities"]
            for opp in opps[:3]:  # Top 3
                opportunities.append(
                    {
                        "category": "optimization",
                        "title": f"Optimize {opp.get('skill', 'skill')}",
                        "description": opp.get("recommendation", "Review and improve"),
                        "potential_impact": "medium",
                        "evidence": opp,
                    }
                )

        # Underutilized models (if using expensive models rarely)
        if "models" in metrics:
            by_model = metrics["models"].get("by_model", {})
            if "opus" in by_model and by_model["opus"].get("invocations", 0) < 5:
                opportunities.append(
                    {
                        "category": "cost_optimization",
                        "title": "Low Opus utilization",
                        "description": "Opus model rarely used - consider for complex tasks to improve quality",
                        "potential_impact": "medium",
                        "evidence": {"opus_usage": by_model["opus"]},
                    }
                )

        # Seasonal patterns (for optimization)
        if "trends" in analysis:
            for metric_name, trend_data in analysis["trends"].items():
                if trend_data.get("seasonality_detected"):
                    opportunities.append(
                        {
                            "category": "planning",
                            "title": f"Seasonal pattern in {metric_name}",
                            "description": "Predictable patterns detected - optimize resource allocation",
                            "potential_impact": "low",
                            "evidence": trend_data,
                        }
                    )

        return opportunities

    def _identify_risks(
        self, metrics: dict[str, Any], analysis: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Identify potential risks and warning signs"""
        risks = []

        # High volatility
        if "trends" in analysis:
            for metric_name, trend_data in analysis["trends"].items():
                volatility = trend_data.get("volatility", 0)
                if volatility > 50:
                    readable_name = metric_name.replace("_", " ")
                    risks.append(
                        {
                            "category": "volatility",
                            "title": f"High volatility in {metric_name}",
                            "description": (
                                f"{readable_name.capitalize()} varies by {volatility:.1f}% between periods, "
                                f"making it difficult to predict capacity needs or spot real problems amid the noise."
                            ),
                            "risk_level": "medium",
                            "evidence": trend_data,
                            "mitigation": "Investigate what causes the swings — time of day, task type, or external factors",
                        }
                    )

        # Declining forecast
        if "forecast" in analysis:
            forecast_trend = analysis["forecast"].get("trend_direction", "")
            if forecast_trend == "decreasing":
                risks.append(
                    {
                        "category": "forecast",
                        "title": "Declining trend forecast",
                        "description": (
                            "Based on recent data, the predictive model projects continued decline. "
                            "Without intervention, key metrics may drop further in the coming periods."
                        ),
                        "risk_level": "high",
                        "evidence": analysis["forecast"],
                        "mitigation": "Identify and address the root causes driving the decline before it accelerates",
                    }
                )

        # Cost escalation
        if "tokens" in metrics:
            total_cost = metrics["tokens"].get("total_cost_usd")
            if total_cost is not None and total_cost > 100:
                risks.append(
                    {
                        "category": "cost",
                        "title": f"High total cost: ${total_cost:.2f}",
                        "description": (
                            f"Total token spend has reached ${total_cost:.2f}. While not critical, "
                            f"costs at this level warrant periodic review to ensure spend aligns with value delivered."
                        ),
                        "risk_level": "low",
                        "evidence": {"total_cost": total_cost},
                        "mitigation": "Check if expensive models are being used where cheaper ones would suffice",
                    }
                )

        return sorted(
            risks,
            key=lambda x: {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(x["risk_level"], 0),
            reverse=True,
        )
