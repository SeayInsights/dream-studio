"""PerformanceAnalyzer - Analyzes performance metrics from collector data"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta


class PerformanceAnalyzer:
    """Analyzes performance metrics from session, skill, and model data"""

    def __init__(self):
        """Initialize PerformanceAnalyzer"""
        pass

    def analyze_skill_performance(self, skill_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze skill performance and identify trends

        Args:
            skill_metrics: Output from SkillCollector.collect()

        Returns:
            Dict containing:
                - high_performers: List[str] - Skills with >90% success rate
                - underperformers: List[str] - Skills with <70% success rate
                - efficiency_score: Dict[skill -> score]
                - improvement_opportunities: List[Dict]
        """
        high_performers = []
        underperformers = []
        efficiency_scores = {}
        opportunities = []

        by_skill = skill_metrics.get("by_skill", {})

        for skill, data in by_skill.items():
            success_rate = data.get("success_rate", 0)
            count = data.get("count", 0)
            avg_exec_time = data.get("avg_exec_time_s", 0)

            # Categorize performers
            if success_rate >= 90 and count >= 5:
                high_performers.append(skill)
            elif success_rate < 70 and count >= 3:
                underperformers.append(skill)

            # Efficiency score: success_rate * (1/exec_time) * usage_weight
            if avg_exec_time > 0:
                usage_weight = min(count / 10, 1.0)  # Cap at 10 uses
                efficiency = (success_rate / 100) * (1 / avg_exec_time) * usage_weight
                efficiency_scores[skill] = round(efficiency, 4)

            # Identify improvement opportunities
            if success_rate < 80 and count >= 5:
                opportunities.append({
                    "skill": skill,
                    "success_rate": success_rate,
                    "count": count,
                    "recommendation": f"Review {skill} - {100 - success_rate:.1f}% failure rate across {count} uses"
                })

        # Sort opportunities by impact (count * failure_rate)
        opportunities.sort(key=lambda x: x["count"] * (100 - x["success_rate"]), reverse=True)

        return {
            "high_performers": sorted(high_performers),
            "underperformers": sorted(underperformers),
            "efficiency_scores": efficiency_scores,
            "improvement_opportunities": opportunities
        }

    def analyze_model_efficiency(self, model_metrics: Dict[str, Any], token_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze model efficiency combining performance and cost

        Args:
            model_metrics: Output from ModelCollector.collect()
            token_metrics: Output from TokenCollector.collect()

        Returns:
            Dict containing:
                - cost_per_invocation: Dict[model -> cost]
                - tokens_per_dollar: Dict[model -> tokens]
                - roi_score: Dict[model -> score]
                - recommendations: List[str]
        """
        cost_per_invocation = {}
        tokens_per_dollar = {}
        roi_scores = {}
        recommendations = []

        by_model = model_metrics.get("by_model", {})
        token_by_model = token_metrics.get("by_model", {})

        for model, data in by_model.items():
            invocations = data.get("invocations", 0)
            success_rate = data.get("success_rate", 0)

            # Get cost data
            if model in token_by_model:
                cost_data = token_by_model[model]
                total_cost = cost_data.get("cost_usd", 0)
                total_tokens = cost_data.get("total_tokens", 0)

                # Cost per invocation
                if invocations > 0:
                    cpi = total_cost / invocations
                    cost_per_invocation[model] = round(cpi, 4)

                # Tokens per dollar
                if total_cost > 0:
                    tpd = total_tokens / total_cost
                    tokens_per_dollar[model] = round(tpd, 0)

                # ROI score: (success_rate * tokens_per_dollar) / cost_per_invocation
                if invocations > 0 and total_cost > 0:
                    roi = (success_rate / 100) * (total_tokens / total_cost) / (total_cost / invocations)
                    roi_scores[model] = round(roi, 2)

        # Generate recommendations
        if roi_scores:
            best_roi = max(roi_scores.items(), key=lambda x: x[1])
            recommendations.append(f"Best ROI: {best_roi[0]} (score: {best_roi[1]})")

            worst_roi = min(roi_scores.items(), key=lambda x: x[1])
            if worst_roi[1] < best_roi[1] * 0.5:  # If worst is <50% of best
                recommendations.append(f"Consider reducing {worst_roi[0]} usage - ROI is {worst_roi[1]} vs {best_roi[1]} for {best_roi[0]}")

        return {
            "cost_per_invocation": cost_per_invocation,
            "tokens_per_dollar": tokens_per_dollar,
            "roi_scores": roi_scores,
            "recommendations": recommendations
        }

    def analyze_session_health(self, session_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze session health and productivity

        Args:
            session_metrics: Output from SessionCollector.collect()

        Returns:
            Dict containing:
                - productivity_score: float (0-100)
                - avg_sessions_per_day: float
                - health_status: str (healthy, warning, critical)
                - recommendations: List[str]
        """
        total_sessions = session_metrics.get("total_sessions", 0)
        outcomes = session_metrics.get("outcomes", {})
        avg_duration = session_metrics.get("avg_duration_minutes", 0)
        by_project = session_metrics.get("by_project", {})

        # Calculate success rate
        success_count = outcomes.get("success", 0)
        success_rate = (success_count / total_sessions * 100) if total_sessions > 0 else 0

        # Productivity score: success_rate * usage_frequency * duration_efficiency
        # Duration efficiency: penalize very short (<5min) and very long (>120min) sessions
        duration_efficiency = 1.0
        if avg_duration < 5:
            duration_efficiency = 0.5
        elif avg_duration > 120:
            duration_efficiency = 0.7

        # Assuming 90 days of data
        sessions_per_day = total_sessions / 90
        frequency_score = min(sessions_per_day / 3, 1.0)  # Target: 3 sessions/day

        productivity_score = (success_rate / 100) * frequency_score * duration_efficiency * 100

        # Determine health status
        if productivity_score >= 70:
            health_status = "healthy"
        elif productivity_score >= 50:
            health_status = "warning"
        else:
            health_status = "critical"

        # Generate recommendations
        recommendations = []
        if success_rate < 80:
            recommendations.append(f"Success rate at {success_rate:.1f}% - review failure patterns")
        if avg_duration < 5:
            recommendations.append("Very short sessions - consider longer focused work periods")
        elif avg_duration > 120:
            recommendations.append("Long sessions detected - consider breaking work into smaller chunks")
        if sessions_per_day < 1:
            recommendations.append("Low session frequency - increase regular usage for better insights")

        # Project concentration analysis
        if by_project:
            top_project_pct = max(by_project.values()) / total_sessions * 100 if total_sessions > 0 else 0
            if top_project_pct > 80:
                recommendations.append(f"Highly concentrated on one project ({top_project_pct:.0f}%) - consider diversifying or this may indicate focused sprint")

        return {
            "productivity_score": round(productivity_score, 1),
            "avg_sessions_per_day": round(sessions_per_day, 2),
            "health_status": health_status,
            "recommendations": recommendations
        }

    def compare_periods(self, current_metrics: Dict[str, Any], previous_metrics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare two time periods to identify trends

        Args:
            current_metrics: Recent period metrics
            previous_metrics: Previous period metrics

        Returns:
            Dict containing period-over-period changes
        """
        changes = {}

        # Compare totals
        for key in ["total_sessions", "total_invocations", "total_tokens"]:
            current_val = current_metrics.get(key, 0)
            previous_val = previous_metrics.get(key, 0)

            if previous_val > 0:
                pct_change = ((current_val - previous_val) / previous_val) * 100
                changes[f"{key}_change_pct"] = round(pct_change, 1)

        return changes
