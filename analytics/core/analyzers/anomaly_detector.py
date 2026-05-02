"""AnomalyDetector - Advanced anomaly detection for analytics data"""
from typing import Dict, List, Any
import statistics


class AnomalyDetector:
    """Advanced anomaly detection with multiple detection methods"""

    def __init__(self, sensitivity: str = "medium"):
        """
        Initialize AnomalyDetector

        Args:
            sensitivity: Detection sensitivity ("low", "medium", "high")
                low: 3.0 std dev threshold
                medium: 2.0 std dev threshold (default)
                high: 1.5 std dev threshold
        """
        self.thresholds = {
            "low": 3.0,
            "medium": 2.0,
            "high": 1.5
        }
        self.sensitivity = sensitivity
        self.threshold = self.thresholds.get(sensitivity, 2.0)

    def detect_outliers_zscore(self, timeline: List[Dict[str, Any]], metric_key: str = "count") -> List[Dict[str, Any]]:
        """
        Detect outliers using z-score method

        Args:
            timeline: List of dicts with date and metric values
            metric_key: Key to analyze

        Returns:
            List of outliers with:
                - date: str
                - value: float
                - z_score: float
                - severity: str (mild, moderate, severe)
                - direction: str (high, low)
        """
        if not timeline or len(timeline) < 3:
            return []

        values = [entry.get(metric_key, 0) for entry in timeline]
        avg = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 0

        if std == 0:
            return []

        outliers = []
        for entry in timeline:
            value = entry.get(metric_key, 0)
            z_score = (value - avg) / std

            if abs(z_score) >= self.threshold:
                # Classify severity
                if abs(z_score) >= 3.0:
                    severity = "severe"
                elif abs(z_score) >= 2.0:
                    severity = "moderate"
                else:
                    severity = "mild"

                outliers.append({
                    "date": entry.get("date"),
                    "value": value,
                    "z_score": round(z_score, 2),
                    "severity": severity,
                    "direction": "high" if value > avg else "low",
                    "expected_range": f"{round(avg - 2*std, 2)} - {round(avg + 2*std, 2)}"
                })

        return sorted(outliers, key=lambda x: abs(x["z_score"]), reverse=True)

    def detect_trend_breaks(self, timeline: List[Dict[str, Any]], metric_key: str = "count", window: int = 5) -> List[Dict[str, Any]]:
        """
        Detect sudden changes in trend direction

        Args:
            timeline: List of dicts with date and metric values
            metric_key: Key to analyze
            window: Window size for trend calculation

        Returns:
            List of trend breaks with:
                - date: str
                - break_type: str (reversal, acceleration, deceleration)
                - before_slope: float
                - after_slope: float
                - magnitude: float
        """
        if not timeline or len(timeline) < window * 2:
            return []

        values = [entry.get(metric_key, 0) for entry in timeline]
        dates = [entry.get("date") for entry in timeline]
        breaks = []

        # Slide a window through the timeline
        for i in range(window, len(values) - window):
            # Calculate slope before and after this point
            before = values[i-window:i]
            after = values[i:i+window]

            before_slope = self._calculate_slope(before)
            after_slope = self._calculate_slope(after)

            # Detect significant slope changes
            slope_diff = after_slope - before_slope

            # Threshold for detecting break (change > 50% of value range)
            value_range = max(values) - min(values)
            threshold = value_range * 0.1 if value_range > 0 else 0

            if abs(slope_diff) > threshold:
                # Classify break type
                if before_slope > 0 and after_slope < 0:
                    break_type = "reversal_downward"
                elif before_slope < 0 and after_slope > 0:
                    break_type = "reversal_upward"
                elif after_slope > before_slope and after_slope > 0:
                    break_type = "acceleration"
                elif after_slope < before_slope and after_slope < 0:
                    break_type = "deceleration"
                else:
                    continue

                breaks.append({
                    "date": dates[i],
                    "break_type": break_type,
                    "before_slope": round(before_slope, 4),
                    "after_slope": round(after_slope, 4),
                    "magnitude": round(abs(slope_diff), 4)
                })

        return sorted(breaks, key=lambda x: x["magnitude"], reverse=True)

    def detect_pattern_deviation(self, current_data: List[Dict[str, Any]], historical_data: List[Dict[str, Any]], metric_key: str = "count") -> Dict[str, Any]:
        """
        Compare current pattern to historical baseline

        Args:
            current_data: Recent timeline data
            historical_data: Historical baseline data
            metric_key: Key to analyze

        Returns:
            Dict containing:
                - is_deviant: bool
                - current_avg: float
                - historical_avg: float
                - deviation_pct: float
                - recommendation: str
        """
        if not current_data or not historical_data:
            return {
                "is_deviant": False,
                "current_avg": 0.0,
                "historical_avg": 0.0,
                "deviation_pct": 0.0,
                "recommendation": "Insufficient data"
            }

        current_values = [entry.get(metric_key, 0) for entry in current_data]
        historical_values = [entry.get(metric_key, 0) for entry in historical_data]

        current_avg = statistics.mean(current_values)
        historical_avg = statistics.mean(historical_values)
        historical_std = statistics.stdev(historical_values) if len(historical_values) > 1 else 0

        # Calculate deviation percentage
        if historical_avg > 0:
            deviation_pct = ((current_avg - historical_avg) / historical_avg) * 100
        else:
            deviation_pct = 0.0

        # Check if deviation is significant (beyond 2 std dev)
        if historical_std > 0:
            is_deviant = abs(current_avg - historical_avg) > (2 * historical_std)
        else:
            is_deviant = abs(deviation_pct) > 50  # 50% change if no std dev

        # Generate recommendation
        if is_deviant:
            if deviation_pct > 0:
                recommendation = f"Current metrics {deviation_pct:.1f}% above historical baseline - investigate cause"
            else:
                recommendation = f"Current metrics {abs(deviation_pct):.1f}% below historical baseline - potential issue"
        else:
            recommendation = "Metrics within normal range"

        return {
            "is_deviant": is_deviant,
            "current_avg": round(current_avg, 2),
            "historical_avg": round(historical_avg, 2),
            "deviation_pct": round(deviation_pct, 2),
            "recommendation": recommendation
        }

    def comprehensive_anomaly_scan(self, timeline: List[Dict[str, Any]], metric_key: str = "count") -> Dict[str, Any]:
        """
        Run all anomaly detection methods and aggregate results

        Args:
            timeline: List of dicts with date and metric values
            metric_key: Key to analyze

        Returns:
            Dict containing:
                - outliers: List from z-score detection
                - trend_breaks: List from trend break detection
                - overall_health: str (healthy, warning, critical)
                - anomaly_count: int
                - recommendations: List[str]
        """
        if not timeline:
            return {
                "outliers": [],
                "trend_breaks": [],
                "overall_health": "unknown",
                "anomaly_count": 0,
                "recommendations": ["Insufficient data for analysis"]
            }

        # Run all detection methods
        outliers = self.detect_outliers_zscore(timeline, metric_key)
        trend_breaks = self.detect_trend_breaks(timeline, metric_key)

        anomaly_count = len(outliers) + len(trend_breaks)
        total_points = len(timeline)

        # Calculate health status
        if total_points > 0:
            anomaly_rate = anomaly_count / total_points
            if anomaly_rate < 0.1:
                overall_health = "healthy"
            elif anomaly_rate < 0.25:
                overall_health = "warning"
            else:
                overall_health = "critical"
        else:
            overall_health = "unknown"

        # Generate recommendations
        recommendations = []

        severe_outliers = [o for o in outliers if o.get("severity") == "severe"]
        if severe_outliers:
            recommendations.append(f"Found {len(severe_outliers)} severe outliers - immediate investigation needed")

        if len(trend_breaks) > 0:
            recommendations.append(f"Detected {len(trend_breaks)} trend breaks - review for root causes")

        if overall_health == "healthy" and not recommendations:
            recommendations.append("No significant anomalies detected - metrics stable")

        return {
            "outliers": outliers,
            "trend_breaks": trend_breaks,
            "overall_health": overall_health,
            "anomaly_count": anomaly_count,
            "anomaly_rate_pct": round((anomaly_count / total_points * 100) if total_points > 0 else 0, 2),
            "recommendations": recommendations
        }

    def _calculate_slope(self, values: List[float]) -> float:
        """Calculate linear slope of values"""
        if not values or len(values) < 2:
            return 0.0

        n = len(values)
        x = list(range(n))
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(values)

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        return numerator / denominator if denominator != 0 else 0.0
