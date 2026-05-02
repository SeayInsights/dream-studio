"""RootCause - Root cause analysis for issues and anomalies"""
from typing import Dict, List, Any, Optional, Tuple


class RootCauseAnalyzer:
    """Analyzes issues to identify root causes through metric correlation"""

    def __init__(self):
        """Initialize RootCauseAnalyzer"""
        # Common root cause patterns
        self.patterns = {
            "high_failure_rate": ["skill_bugs", "api_timeouts", "data_quality", "configuration"],
            "performance_degradation": ["resource_contention", "data_volume", "network_latency", "algorithm_complexity"],
            "cost_spike": ["model_misuse", "token_waste", "inefficient_prompts", "excessive_retries"],
            "usage_decline": ["user_satisfaction", "feature_gaps", "competition", "seasonal"]
        }

    def analyze_issue(self, issue: Dict[str, Any], metrics: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Perform root cause analysis for a specific issue

        Args:
            issue: Issue dict from InsightEngine
            metrics: Raw metrics from collectors
            analysis: Analysis results from analyzers

        Returns:
            Dict containing:
                - issue: Original issue
                - probable_causes: List[Dict] - Ranked probable causes
                - correlations: Dict - Metric correlations
                - confidence: float - Analysis confidence (0-1)
                - recommendations: List[str] - Next steps
        """
        issue_category = issue.get("category", "unknown")

        # Dispatch to specialized analysis
        if issue_category == "skill_performance":
            probable_causes = self._analyze_skill_performance_issue(issue, metrics, analysis)
        elif issue_category == "quality":
            probable_causes = self._analyze_quality_issue(issue, metrics, analysis)
        elif issue_category == "anomalies":
            probable_causes = self._analyze_anomaly_issue(issue, metrics, analysis)
        elif issue_category == "decline":
            probable_causes = self._analyze_decline_issue(issue, metrics, analysis)
        else:
            probable_causes = self._generic_analysis(issue, metrics, analysis)

        # Calculate correlations
        correlations = self._calculate_correlations(issue, metrics, analysis)

        # Determine confidence
        confidence = self._calculate_confidence(probable_causes, correlations)

        # Generate recommendations
        recommendations = self._generate_recommendations(probable_causes, issue)

        return {
            "issue": issue,
            "probable_causes": probable_causes,
            "correlations": correlations,
            "confidence": confidence,
            "recommendations": recommendations
        }

    def _analyze_skill_performance_issue(self, issue: Dict[str, Any], metrics: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze skill performance issues"""
        causes = []
        evidence = issue.get("evidence", {})
        skills = evidence.get("skills", [])

        # Check if it's a specific skill or many
        if len(skills) == 1:
            # Single skill issue - likely skill-specific problem
            causes.append({
                "cause": "Skill-specific bug or logic error",
                "likelihood": "high",
                "evidence": f"Only {skills[0]} underperforming",
                "investigation_steps": [
                    f"Review error logs for {skills[0]}",
                    "Check recent changes to skill implementation",
                    "Validate input/output contracts"
                ]
            })
        elif len(skills) > 5:
            # Many skills failing - likely systemic issue
            causes.append({
                "cause": "Systemic infrastructure or configuration issue",
                "likelihood": "high",
                "evidence": f"{len(skills)} skills affected simultaneously",
                "investigation_steps": [
                    "Check API availability and response times",
                    "Review system configuration changes",
                    "Validate environment variables and secrets"
                ]
            })

        # Check for correlation with model performance
        if "models" in metrics:
            for model, model_data in metrics["models"].get("by_model", {}).items():
                if model_data.get("success_rate", 100) < 80:
                    causes.append({
                        "cause": f"{model.capitalize()} model degradation",
                        "likelihood": "medium",
                        "evidence": f"{model} success rate: {model_data.get('success_rate', 0):.1f}%",
                        "investigation_steps": [
                            f"Check {model} API status",
                            "Review prompt quality for model compatibility"
                        ]
                    })

        return sorted(causes, key=lambda x: {"high": 3, "medium": 2, "low": 1}.get(x["likelihood"], 0), reverse=True)

    def _analyze_quality_issue(self, issue: Dict[str, Any], metrics: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze quality/success rate issues"""
        causes = []
        evidence = issue.get("evidence", {})
        success_rate = evidence.get("success_rate", 100)

        # Very low success rate suggests fundamental issues
        if success_rate < 50:
            causes.append({
                "cause": "Critical system failure or misconfiguration",
                "likelihood": "high",
                "evidence": f"Only {success_rate:.1f}% success rate",
                "investigation_steps": [
                    "Check for recent deployments or config changes",
                    "Review error logs for common failure patterns",
                    "Validate database connectivity and schema"
                ]
            })

        # Check for temporal correlation (recent decline)
        if "trends" in analysis:
            session_trend = analysis["trends"].get("sessions", {})
            if session_trend.get("trend") == "decreasing":
                causes.append({
                    "cause": "Recent degradation or regression",
                    "likelihood": "high",
                    "evidence": "Sessions declining alongside quality drop",
                    "investigation_steps": [
                        "Review recent commits and deploys",
                        "Compare error patterns before/after decline",
                        "Check for infrastructure changes"
                    ]
                })

        # Check for token/cost correlation (indicates retries or inefficiency)
        if "tokens" in metrics:
            sessions = metrics.get("sessions", {}).get("total_sessions", 1)
            tokens_per_session = metrics["tokens"].get("total_tokens", 0) / sessions
            if tokens_per_session > 10000:  # High token usage
                causes.append({
                    "cause": "Excessive retries or inefficient error handling",
                    "likelihood": "medium",
                    "evidence": f"{tokens_per_session:.0f} tokens/session (high)",
                    "investigation_steps": [
                        "Review retry logic and backoff strategies",
                        "Check for infinite loops or recursive errors",
                        "Optimize error recovery flows"
                    ]
                })

        return sorted(causes, key=lambda x: {"high": 3, "medium": 2, "low": 1}.get(x["likelihood"], 0), reverse=True)

    def _analyze_anomaly_issue(self, issue: Dict[str, Any], metrics: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze anomaly detection issues"""
        causes = []
        evidence = issue.get("evidence", {})
        outliers = evidence.get("outliers", [])
        trend_breaks = evidence.get("trend_breaks", [])

        # Spike anomalies
        if outliers:
            high_outliers = [o for o in outliers if o.get("direction") == "high"]
            if high_outliers:
                causes.append({
                    "cause": "Unusual spike in activity or resource usage",
                    "likelihood": "high",
                    "evidence": f"{len(high_outliers)} high outliers detected",
                    "investigation_steps": [
                        "Identify dates/times of spikes",
                        "Correlate with external events (deployments, campaigns)",
                        "Check for automated processes or batch jobs"
                    ]
                })

        # Trend breaks suggest external changes
        if trend_breaks:
            causes.append({
                "cause": "External change or intervention",
                "likelihood": "medium",
                "evidence": f"{len(trend_breaks)} trend breaks",
                "investigation_steps": [
                    "Review change log around break dates",
                    "Check for A/B tests or feature flags",
                    "Correlate with user behavior changes"
                ]
            })

        return causes

    def _analyze_decline_issue(self, issue: Dict[str, Any], metrics: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Analyze metric decline issues"""
        causes = []
        evidence = issue.get("evidence", {})

        # Gradual decline suggests attrition or degrading experience
        slope = evidence.get("slope", 0)
        if -5 < slope < -1:  # Moderate decline
            causes.append({
                "cause": "Gradual user attrition or engagement decline",
                "likelihood": "medium",
                "evidence": f"Steady decline: {slope:.2f} per period",
                "investigation_steps": [
                    "Survey users for feedback",
                    "Analyze feature usage patterns",
                    "Review competitive landscape"
                ]
            })
        elif slope <= -5:  # Steep decline
            causes.append({
                "cause": "Critical issue driving users away",
                "likelihood": "high",
                "evidence": f"Rapid decline: {slope:.2f} per period",
                "investigation_steps": [
                    "Urgent: check for service outages or critical bugs",
                    "Review recent negative feedback or support tickets",
                    "Verify API availability and performance"
                ]
            })

        return causes

    def _generic_analysis(self, issue: Dict[str, Any], metrics: Dict[str, Any], analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generic analysis for uncategorized issues"""
        return [{
            "cause": "Insufficient data for specific root cause analysis",
            "likelihood": "unknown",
            "evidence": f"Issue category: {issue.get('category', 'unknown')}",
            "investigation_steps": [
                "Gather more detailed metrics",
                "Review logs and error messages",
                "Consult domain experts"
            ]
        }]

    def _calculate_correlations(self, issue: Dict[str, Any], metrics: Dict[str, Any], analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate correlations between issue and other metrics

        Returns:
            Dict of metric_name -> correlation_strength
        """
        correlations = {}

        # This is a simplified correlation - in production would use actual statistical correlation
        # For now, we'll do pattern matching

        issue_category = issue.get("category", "")

        if issue_category == "skill_performance":
            # Correlate with model performance
            if "models" in metrics:
                correlations["model_performance"] = "strong"

        elif issue_category == "quality":
            # Correlate with tokens (might indicate retries)
            if "tokens" in metrics:
                correlations["token_usage"] = "moderate"

        elif issue_category == "anomalies":
            # Correlate with timeline patterns
            correlations["temporal_patterns"] = "strong"

        return correlations

    def _calculate_confidence(self, probable_causes: List[Dict[str, Any]], correlations: Dict[str, Any]) -> float:
        """Calculate confidence in root cause analysis"""
        if not probable_causes:
            return 0.0

        # Base confidence on likelihood of top cause
        top_likelihood = probable_causes[0].get("likelihood", "unknown")
        confidence_map = {"high": 0.85, "medium": 0.65, "low": 0.45, "unknown": 0.3}
        confidence = confidence_map.get(top_likelihood, 0.5)

        # Boost if strong correlations found
        if correlations:
            strong_corr = sum(1 for c in correlations.values() if c == "strong")
            confidence += (strong_corr * 0.1)

        return min(round(confidence, 2), 1.0)

    def _generate_recommendations(self, probable_causes: List[Dict[str, Any]], issue: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations"""
        recommendations = []

        if not probable_causes:
            return ["Gather more data to identify root cause"]

        # Take steps from top 2 causes
        for cause in probable_causes[:2]:
            steps = cause.get("investigation_steps", [])
            recommendations.extend(steps[:2])  # Top 2 steps per cause

        # Add general recommendation based on issue severity
        severity = issue.get("severity", "low")
        if severity in ["critical", "high"]:
            recommendations.insert(0, "URGENT: Prioritize investigation and resolution")

        return recommendations[:5]  # Max 5 recommendations
