"""Predictor - Time series forecasting for analytics metrics"""
from typing import Dict, List, Any, Tuple
from datetime import datetime, timedelta
import statistics


class Predictor:
    """Time series forecasting with confidence intervals"""

    def __init__(self):
        """Initialize Predictor"""
        pass

    def forecast_linear(self, timeline: List[Dict[str, Any]], metric_key: str = "count", steps_ahead: int = 7) -> Dict[str, Any]:
        """
        Generate linear forecast for future values

        Args:
            timeline: Historical timeline data
            metric_key: Key to forecast
            steps_ahead: Number of periods to forecast

        Returns:
            Dict containing:
                - forecast: List[Dict] with date and predicted value
                - slope: float (trend slope)
                - confidence_level: str
                - lower_bound: List[float]
                - upper_bound: List[float]
        """
        if not timeline or len(timeline) < 3:
            return {
                "forecast": [],
                "slope": 0.0,
                "confidence_level": "low",
                "lower_bound": [],
                "upper_bound": [],
                "error": "Insufficient historical data"
            }

        values = [entry.get(metric_key, 0) for entry in timeline]
        dates = [entry.get("date") for entry in timeline]

        # Calculate linear trend
        n = len(values)
        x = list(range(n))
        slope, intercept = self._calculate_linear_regression(x, values)

        # Calculate prediction error (standard error of estimate)
        predictions = [slope * i + intercept for i in x]
        residuals = [(values[i] - predictions[i]) ** 2 for i in range(n)]
        mse = statistics.mean(residuals) if residuals else 0
        std_error = mse ** 0.5

        # Generate forecast
        forecast = []
        lower_bound = []
        upper_bound = []

        # Parse last date to increment
        try:
            last_date_str = dates[-1] if dates[-1] else datetime.now().isoformat()
            last_date = datetime.fromisoformat(last_date_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            last_date = datetime.now()

        for step in range(1, steps_ahead + 1):
            x_future = n + step - 1
            predicted_value = slope * x_future + intercept

            # Confidence interval (±2 std errors = ~95% confidence)
            # Widen interval for further predictions
            interval_width = 2 * std_error * (1 + step * 0.1)
            lower = max(0, predicted_value - interval_width)  # Can't be negative
            upper = predicted_value + interval_width

            # Increment date
            future_date = last_date + timedelta(days=step)

            forecast.append({
                "date": future_date.strftime("%Y-%m-%d"),
                "predicted_value": round(predicted_value, 2),
                "confidence_lower": round(lower, 2),
                "confidence_upper": round(upper, 2)
            })

            lower_bound.append(round(lower, 2))
            upper_bound.append(round(upper, 2))

        # Determine confidence level based on data quality
        if n >= 14:
            confidence_level = "high"
        elif n >= 7:
            confidence_level = "medium"
        else:
            confidence_level = "low"

        return {
            "forecast": forecast,
            "slope": round(slope, 4),
            "confidence_level": confidence_level,
            "lower_bound": lower_bound,
            "upper_bound": upper_bound,
            "historical_std_error": round(std_error, 2)
        }

    def predict_next_value(self, timeline: List[Dict[str, Any]], metric_key: str = "count") -> Dict[str, Any]:
        """
        Predict the next single value with confidence interval

        Args:
            timeline: Historical timeline data
            metric_key: Key to predict

        Returns:
            Dict containing:
                - predicted_value: float
                - confidence_interval: Tuple[float, float]
                - trend_direction: str (increasing, decreasing, stable)
                - confidence_score: float (0-1)
        """
        forecast = self.forecast_linear(timeline, metric_key, steps_ahead=1)

        if not forecast.get("forecast"):
            return {
                "predicted_value": 0.0,
                "confidence_interval": (0.0, 0.0),
                "trend_direction": "unknown",
                "confidence_score": 0.0,
                "error": "Insufficient data"
            }

        next_pred = forecast["forecast"][0]
        slope = forecast["slope"]

        # Determine trend
        if abs(slope) < 0.1:
            trend_direction = "stable"
        elif slope > 0:
            trend_direction = "increasing"
        else:
            trend_direction = "decreasing"

        # Confidence score based on data quality and std error
        confidence_map = {"high": 0.85, "medium": 0.65, "low": 0.45}
        confidence_score = confidence_map.get(forecast["confidence_level"], 0.5)

        return {
            "predicted_value": next_pred["predicted_value"],
            "confidence_interval": (next_pred["confidence_lower"], next_pred["confidence_upper"]),
            "trend_direction": trend_direction,
            "confidence_score": confidence_score
        }

    def forecast_with_seasonality(self, timeline: List[Dict[str, Any]], metric_key: str = "count", steps_ahead: int = 7) -> Dict[str, Any]:
        """
        Forecast with basic seasonality adjustment (weekly patterns)

        Args:
            timeline: Historical timeline data
            metric_key: Key to forecast
            steps_ahead: Number of periods to forecast

        Returns:
            Dict with seasonal-adjusted forecast
        """
        if not timeline or len(timeline) < 14:  # Need at least 2 weeks
            return self.forecast_linear(timeline, metric_key, steps_ahead)

        # Detect day-of-week pattern
        dow_pattern = self._calculate_dow_pattern(timeline, metric_key)

        # Get base linear forecast
        linear_forecast = self.forecast_linear(timeline, metric_key, steps_ahead)

        if not linear_forecast.get("forecast"):
            return linear_forecast

        # Apply seasonal adjustment
        seasonal_forecast = []
        for i, pred in enumerate(linear_forecast["forecast"]):
            try:
                pred_date = datetime.fromisoformat(pred["date"])
                dow = pred_date.weekday()  # 0=Monday, 6=Sunday

                # Get seasonal multiplier for this day
                seasonal_multiplier = dow_pattern.get(dow, 1.0)

                # Adjust prediction
                adjusted_value = pred["predicted_value"] * seasonal_multiplier
                adjusted_lower = pred["confidence_lower"] * seasonal_multiplier
                adjusted_upper = pred["confidence_upper"] * seasonal_multiplier

                seasonal_forecast.append({
                    "date": pred["date"],
                    "predicted_value": round(adjusted_value, 2),
                    "confidence_lower": round(adjusted_lower, 2),
                    "confidence_upper": round(adjusted_upper, 2),
                    "seasonal_adjustment": round(seasonal_multiplier, 2)
                })
            except (ValueError, AttributeError):
                # If date parsing fails, use unadjusted forecast
                seasonal_forecast.append(pred)

        return {
            "forecast": seasonal_forecast,
            "slope": linear_forecast["slope"],
            "confidence_level": linear_forecast["confidence_level"],
            "seasonality_detected": any(abs(m - 1.0) > 0.1 for m in dow_pattern.values()),
            "day_of_week_pattern": dow_pattern
        }

    def calculate_forecast_accuracy(self, timeline: List[Dict[str, Any]], metric_key: str = "count", validation_window: int = 7) -> Dict[str, Any]:
        """
        Backtest forecast accuracy using recent data

        Args:
            timeline: Full timeline including validation period
            metric_key: Key to test
            validation_window: How many recent points to validate against

        Returns:
            Dict containing:
                - mae: Mean Absolute Error
                - mape: Mean Absolute Percentage Error
                - accuracy_score: float (0-1)
        """
        if not timeline or len(timeline) < validation_window + 7:
            return {
                "mae": 0.0,
                "mape": 0.0,
                "accuracy_score": 0.0,
                "error": "Insufficient data for validation"
            }

        # Split into train and validation
        train_data = timeline[:-validation_window]
        validation_data = timeline[-validation_window:]

        # Generate forecast
        forecast = self.forecast_linear(train_data, metric_key, steps_ahead=validation_window)

        if not forecast.get("forecast"):
            return {
                "mae": 0.0,
                "mape": 0.0,
                "accuracy_score": 0.0,
                "error": "Forecast generation failed"
            }

        # Calculate errors
        errors = []
        pct_errors = []

        for i, (pred, actual) in enumerate(zip(forecast["forecast"], validation_data)):
            actual_value = actual.get(metric_key, 0)
            predicted_value = pred["predicted_value"]

            error = abs(actual_value - predicted_value)
            errors.append(error)

            if actual_value > 0:
                pct_error = (error / actual_value) * 100
                pct_errors.append(pct_error)

        mae = statistics.mean(errors) if errors else 0
        mape = statistics.mean(pct_errors) if pct_errors else 0

        # Accuracy score: 1 - (MAPE/100), capped at 0
        accuracy_score = max(0, 1 - (mape / 100))

        return {
            "mae": round(mae, 2),
            "mape": round(mape, 2),
            "accuracy_score": round(accuracy_score, 2),
            "validation_points": validation_window
        }

    def _calculate_linear_regression(self, x: List[int], y: List[float]) -> Tuple[float, float]:
        """
        Calculate linear regression slope and intercept

        Returns:
            (slope, intercept)
        """
        if not x or not y or len(x) != len(y):
            return 0.0, 0.0

        n = len(x)
        x_mean = statistics.mean(x)
        y_mean = statistics.mean(y)

        numerator = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0.0
        intercept = y_mean - slope * x_mean

        return slope, intercept

    def _calculate_dow_pattern(self, timeline: List[Dict[str, Any]], metric_key: str = "count") -> Dict[int, float]:
        """
        Calculate day-of-week seasonal pattern

        Returns:
            Dict mapping weekday (0-6) to multiplier (1.0 = average)
        """
        from collections import defaultdict

        dow_values = defaultdict(list)

        for entry in timeline:
            date_str = entry.get("date")
            value = entry.get(metric_key, 0)

            if date_str:
                try:
                    dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    dow = dt.weekday()
                    dow_values[dow].append(value)
                except (ValueError, AttributeError):
                    continue

        # Calculate average for each day
        dow_avgs = {}
        for dow in range(7):
            if dow in dow_values and dow_values[dow]:
                dow_avgs[dow] = statistics.mean(dow_values[dow])

        # Calculate overall average
        if dow_avgs:
            overall_avg = statistics.mean(dow_avgs.values())

            # Convert to multipliers (1.0 = average day)
            return {
                dow: (avg / overall_avg if overall_avg > 0 else 1.0)
                for dow, avg in dow_avgs.items()
            }

        # Default: no pattern
        return {i: 1.0 for i in range(7)}
