"""TrendAnalyzer - Analyzes trends and patterns in time series data"""
from typing import Dict, List, Any, Optional
from datetime import datetime
from collections import defaultdict
import statistics


class TrendAnalyzer:
    """Analyzes trends, seasonality, and patterns in timeline data"""

    def __init__(self):
        """Initialize TrendAnalyzer"""
        pass

    def analyze_timeline(self, timeline: List[Dict[str, Any]], metric_key: str = "count") -> Dict[str, Any]:
        """
        Analyze timeline data for trends

        Args:
            timeline: List of dicts with date and metric values
            metric_key: Key to analyze (default: "count")

        Returns:
            Dict containing:
                - trend: str (increasing, decreasing, stable)
                - slope: float
                - volatility: float
                - average: float
                - peak_date: str
                - trough_date: str
        """
        if not timeline or len(timeline) < 2:
            return {
                "trend": "insufficient_data",
                "slope": 0.0,
                "volatility": 0.0,
                "average": 0.0,
                "peak_date": None,
                "trough_date": None
            }

        # Extract values
        values = [entry.get(metric_key, 0) for entry in timeline]
        dates = [entry.get("date") for entry in timeline]

        # Calculate average
        avg = statistics.mean(values)

        # Calculate linear trend (simple slope)
        n = len(values)
        x = list(range(n))
        x_mean = statistics.mean(x)
        y_mean = avg

        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0.0

        # Determine trend direction
        if abs(slope) < avg * 0.05:  # Less than 5% change
            trend = "stable"
        elif slope > 0:
            trend = "increasing"
        else:
            trend = "decreasing"

        # Calculate volatility (coefficient of variation)
        if avg > 0:
            std_dev = statistics.stdev(values) if len(values) > 1 else 0
            volatility = (std_dev / avg) * 100
        else:
            volatility = 0.0

        # Find peak and trough
        max_idx = values.index(max(values))
        min_idx = values.index(min(values))

        return {
            "trend": trend,
            "slope": round(slope, 4),
            "volatility": round(volatility, 2),
            "average": round(avg, 2),
            "peak_date": dates[max_idx],
            "peak_value": max(values),
            "trough_date": dates[min_idx],
            "trough_value": min(values)
        }

    def detect_seasonality(self, timeline: List[Dict[str, Any]], metric_key: str = "count") -> Dict[str, Any]:
        """
        Detect weekly/monthly patterns

        Args:
            timeline: List of dicts with date and metric values
            metric_key: Key to analyze

        Returns:
            Dict containing:
                - has_weekly_pattern: bool
                - day_of_week_strength: Dict[weekday -> avg_value]
                - strongest_day: str
                - weakest_day: str
        """
        if not timeline:
            return {
                "has_weekly_pattern": False,
                "day_of_week_strength": {},
                "strongest_day": None,
                "weakest_day": None
            }

        # Group by day of week
        dow_values = defaultdict(list)
        weekdays = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        for entry in timeline:
            date_str = entry.get("date")
            value = entry.get(metric_key, 0)

            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    dow = weekdays[dt.weekday()]
                    dow_values[dow].append(value)
                except (ValueError, AttributeError):
                    continue

        # Calculate averages per day
        dow_strength = {}
        for day in weekdays:
            if day in dow_values and dow_values[day]:
                dow_strength[day] = round(statistics.mean(dow_values[day]), 2)

        # Detect pattern strength
        if len(dow_strength) >= 5:  # Need at least 5 days
            values = list(dow_strength.values())
            avg = statistics.mean(values)
            std = statistics.stdev(values) if len(values) > 1 else 0

            # Pattern exists if std dev > 20% of mean
            has_pattern = (std / avg) > 0.2 if avg > 0 else False

            strongest_day = max(dow_strength, key=dow_strength.get) if dow_strength else None
            weakest_day = min(dow_strength, key=dow_strength.get) if dow_strength else None
        else:
            has_pattern = False
            strongest_day = None
            weakest_day = None

        return {
            "has_weekly_pattern": has_pattern,
            "day_of_week_strength": dow_strength,
            "strongest_day": strongest_day,
            "weakest_day": weakest_day
        }

    def identify_growth_rate(self, timeline: List[Dict[str, Any]], metric_key: str = "count", window_days: int = 7) -> Dict[str, Any]:
        """
        Calculate growth rate using moving averages

        Args:
            timeline: List of dicts with date and metric values
            metric_key: Key to analyze
            window_days: Window for moving average

        Returns:
            Dict containing:
                - growth_rate_pct: float
                - acceleration: str (accelerating, decelerating, steady)
                - forecast_next_period: float
        """
        if not timeline or len(timeline) < window_days * 2:
            return {
                "growth_rate_pct": 0.0,
                "acceleration": "insufficient_data",
                "forecast_next_period": 0.0
            }

        values = [entry.get(metric_key, 0) for entry in timeline]

        # Calculate moving averages
        first_window_avg = statistics.mean(values[:window_days])
        last_window_avg = statistics.mean(values[-window_days:])

        # Growth rate
        if first_window_avg > 0:
            growth_rate = ((last_window_avg - first_window_avg) / first_window_avg) * 100
        else:
            growth_rate = 0.0

        # Check acceleration (compare first half vs second half growth)
        mid = len(values) // 2
        first_half_avg = statistics.mean(values[:mid])
        second_half_avg = statistics.mean(values[mid:])

        if first_half_avg > 0:
            first_half_growth = ((statistics.mean(values[mid//2:mid]) - first_half_avg) / first_half_avg) * 100
        else:
            first_half_growth = 0

        if second_half_avg > 0:
            second_half_growth = ((last_window_avg - second_half_avg) / second_half_avg) * 100
        else:
            second_half_growth = 0

        if abs(second_half_growth - first_half_growth) < 5:
            acceleration = "steady"
        elif second_half_growth > first_half_growth:
            acceleration = "accelerating"
        else:
            acceleration = "decelerating"

        # Simple forecast: project current trend forward
        forecast = last_window_avg * (1 + (growth_rate / 100))

        return {
            "growth_rate_pct": round(growth_rate, 2),
            "acceleration": acceleration,
            "forecast_next_period": round(forecast, 2)
        }

    def detect_anomalies_simple(self, timeline: List[Dict[str, Any]], metric_key: str = "count", threshold: float = 2.0) -> List[Dict[str, Any]]:
        """
        Detect statistical anomalies using standard deviation

        Args:
            timeline: List of dicts with date and metric values
            metric_key: Key to analyze
            threshold: Number of standard deviations to flag (default: 2.0)

        Returns:
            List of anomalies with date, value, and deviation
        """
        if not timeline or len(timeline) < 3:
            return []

        values = [entry.get(metric_key, 0) for entry in timeline]
        avg = statistics.mean(values)
        std = statistics.stdev(values) if len(values) > 1 else 0

        if std == 0:
            return []

        anomalies = []
        for entry in timeline:
            value = entry.get(metric_key, 0)
            deviation = abs(value - avg) / std

            if deviation >= threshold:
                anomalies.append({
                    "date": entry.get("date"),
                    "value": value,
                    "deviation": round(deviation, 2),
                    "direction": "high" if value > avg else "low"
                })

        return sorted(anomalies, key=lambda x: x["deviation"], reverse=True)
