"""Recommendations - Strategic recommendations based on insights and analysis"""
from typing import Dict, List, Any


class RecommendationEngine:
    """Generates strategic recommendations from insights and root cause analysis"""

    def __init__(self):
        """Initialize RecommendationEngine"""
        self.priority_levels = ["critical", "high", "medium", "low"]

    def generate_recommendations(self, insights: Dict[str, Any], root_causes: List[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
        """
        Generate strategic recommendations

        Args:
            insights: Insights from InsightEngine
            root_causes: Optional root cause analyses

        Returns:
            List of recommendations sorted by priority
        """
        recommendations = []

        # Recommendations from issues
        for issue in insights.get("issues", []):
            rec = self._recommendation_from_issue(issue)
            if rec:
                recommendations.append(rec)

        # Recommendations from opportunities
        for opp in insights.get("opportunities", []):
            rec = self._recommendation_from_opportunity(opp)
            if rec:
                recommendations.append(rec)

        # Recommendations from risks
        for risk in insights.get("risks", []):
            rec = self._recommendation_from_risk(risk)
            if rec:
                recommendations.append(rec)

        # Add root cause recommendations if provided
        if root_causes:
            for rc in root_causes:
                rec_items = rc.get("recommendations", [])
                for item in rec_items[:2]:  # Top 2 from each root cause
                    recommendations.append({
                        "title": item,
                        "category": "investigation",
                        "priority": "high",
                        "impact": "Resolves root cause",
                        "effort": "medium",
                        "source": "root_cause_analysis"
                    })

        # Deduplicate and sort by priority
        recommendations = self._deduplicate(recommendations)
        recommendations = sorted(
            recommendations,
            key=lambda x: (
                self.priority_levels.index(x.get("priority", "low")),
                -self._estimate_roi(x)
            )
        )

        return recommendations

    def _recommendation_from_issue(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        """Convert issue to recommendation"""
        category = issue.get("category", "unknown")
        severity = issue.get("severity", "medium")

        # Map severity to priority
        priority_map = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}
        priority = priority_map.get(severity, "medium")

        # Get recommended action if available
        action = issue.get("recommended_action", "")

        if not action:
            # Generate generic action
            if category == "skill_performance":
                action = "Review and optimize underperforming skills"
            elif category == "quality":
                action = "Improve error handling and success rates"
            elif category == "anomalies":
                action = "Investigate and resolve anomalies"
            elif category == "decline":
                action = "Address declining trends"
            else:
                action = "Address detected issue"

        return {
            "title": action,
            "category": "fix",
            "priority": priority,
            "impact": f"Resolves {severity} severity issue",
            "effort": self._estimate_effort(issue),
            "source": "issue_detection",
            "details": issue.get("description", "")
        }

    def _recommendation_from_opportunity(self, opportunity: Dict[str, Any]) -> Dict[str, Any]:
        """Convert opportunity to recommendation"""
        title = opportunity.get("title", "Optimization opportunity")
        description = opportunity.get("description", "")
        potential_impact = opportunity.get("potential_impact", "medium")

        # Opportunities are generally medium priority (unless high impact)
        if potential_impact == "high":
            priority = "high"
        else:
            priority = "medium"

        return {
            "title": title,
            "category": "optimize",
            "priority": priority,
            "impact": f"Potential {potential_impact} impact improvement",
            "effort": "low",  # Optimizations are typically lower effort than fixes
            "source": "opportunity_analysis",
            "details": description
        }

    def _recommendation_from_risk(self, risk: Dict[str, Any]) -> Dict[str, Any]:
        """Convert risk to recommendation"""
        mitigation = risk.get("mitigation", "Monitor and mitigate risk")
        risk_level = risk.get("risk_level", "medium")

        # Map risk level to priority
        priority_map = {"critical": "critical", "high": "high", "medium": "medium", "low": "low"}
        priority = priority_map.get(risk_level, "medium")

        return {
            "title": mitigation,
            "category": "mitigate",
            "priority": priority,
            "impact": f"Reduces {risk_level} risk",
            "effort": "medium",
            "source": "risk_analysis",
            "details": risk.get("description", "")
        }

    def _estimate_effort(self, issue: Dict[str, Any]) -> str:
        """Estimate implementation effort"""
        category = issue.get("category", "unknown")
        severity = issue.get("severity", "medium")

        # Critical issues might need more effort
        if severity == "critical":
            return "high"

        # Some categories are typically easier
        if category in ["cost_efficiency", "planning"]:
            return "low"

        return "medium"

    def _estimate_roi(self, recommendation: Dict[str, Any]) -> float:
        """
        Estimate ROI (impact vs effort) for prioritization

        Returns:
            float: ROI score (higher is better)
        """
        # Impact scoring
        impact_scores = {
            "Resolves critical severity issue": 10,
            "Resolves high severity issue": 8,
            "Resolves medium severity issue": 5,
            "Resolves low severity issue": 3,
            "Reduces critical risk": 9,
            "Reduces high risk": 7,
            "Reduces medium risk": 4,
            "Reduces low risk": 2,
            "Potential high impact improvement": 6,
            "Potential medium impact improvement": 4,
            "Potential low impact improvement": 2
        }

        # Effort scoring (inverse - lower effort is better)
        effort_scores = {"low": 1, "medium": 2, "high": 3}

        impact = recommendation.get("impact", "")
        effort = recommendation.get("effort", "medium")

        impact_score = impact_scores.get(impact, 3)
        effort_score = effort_scores.get(effort, 2)

        # ROI = impact / effort (higher is better)
        roi = impact_score / effort_score

        return roi

    def _deduplicate(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Remove duplicate recommendations"""
        seen = set()
        unique = []

        for rec in recommendations:
            title = rec.get("title", "")
            if title and title not in seen:
                seen.add(title)
                unique.append(rec)

        return unique

    def get_quick_wins(self, recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Filter for quick wins (high impact, low effort)

        Returns:
            List of high-ROI, low-effort recommendations
        """
        quick_wins = []

        for rec in recommendations:
            effort = rec.get("effort", "medium")
            roi = self._estimate_roi(rec)

            if effort == "low" and roi >= 3:  # High ROI threshold
                quick_wins.append(rec)

        return sorted(quick_wins, key=lambda x: self._estimate_roi(x), reverse=True)

    def format_for_executive(self, recommendations: List[Dict[str, Any]], limit: int = 5) -> str:
        """
        Format recommendations for executive summary

        Args:
            recommendations: Full list of recommendations
            limit: Max recommendations to include

        Returns:
            Formatted string
        """
        if not recommendations:
            return "No actionable recommendations at this time."

        output = f"Top {min(limit, len(recommendations))} Recommendations:\n\n"

        for i, rec in enumerate(recommendations[:limit], 1):
            priority = rec.get("priority", "medium").upper()
            title = rec.get("title", "Unknown")
            impact = rec.get("impact", "")
            effort = rec.get("effort", "medium")

            output += f"{i}. [{priority}] {title}\n"
            output += f"   Impact: {impact} | Effort: {effort.capitalize()}\n"

            details = rec.get("details", "")
            if details:
                output += f"   {details}\n"

            output += "\n"

        return output.strip()

    def group_by_category(self, recommendations: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """Group recommendations by category"""
        grouped = {
            "fix": [],
            "optimize": [],
            "mitigate": [],
            "investigate": []
        }

        for rec in recommendations:
            category = rec.get("category", "investigate")
            if category in grouped:
                grouped[category].append(rec)
            else:
                grouped["investigate"].append(rec)

        return grouped
