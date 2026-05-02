"""
Time series forecasting models for dream-studio analytics.

Provides forecasting for:
- Token usage
- Skill usage
- Session counts

Supports ARIMA/exponential smoothing when statsmodels is available,
with simple moving average fallback.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Union
import warnings

from .base import BaseModel, PANDAS_AVAILABLE, NUMPY_AVAILABLE

# Try to import statsmodels for advanced forecasting
try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    from statsmodels.tsa.arima.model import ARIMA
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    warnings.warn(
        "statsmodels not available. Forecasting will use simple moving average fallback. "
        "Install with: pip install statsmodels"
    )

if PANDAS_AVAILABLE:
    import pandas as pd

if NUMPY_AVAILABLE:
    import numpy as np


class TimeSeriesForecaster(BaseModel):
    """
    Time series forecasting model for dream-studio analytics.

    Forecasts token usage, skill usage, and session counts using ARIMA or
    exponential smoothing when statsmodels is available, falling back to
    simple moving average otherwise.

    Attributes:
        fitted: Whether the model has been trained
        model: The underlying forecasting model
        data: Historical time series data
        method: Forecasting method used ('arima', 'exponential', or 'moving_average')
    """

    def __init__(self, method: str = 'auto'):
        """
        Initialize the time series forecaster.

        Args:
            method: Forecasting method to use. Options:
                - 'auto': Select best available method automatically
                - 'arima': Use ARIMA model (requires statsmodels)
                - 'exponential': Use exponential smoothing (requires statsmodels)
                - 'moving_average': Use simple moving average (always available)
        """
        super().__init__()
        self.method = method
        self.model = None
        self.data = None
        self._history_length = 0

    def fit(self, data: "pd.DataFrame") -> None:
        """
        Train the forecasting model on historical data.

        Args:
            data: DataFrame with DatetimeIndex and single value column

        Raises:
            ValueError: If data has insufficient history (< 14 days)
        """
        if not PANDAS_AVAILABLE or not NUMPY_AVAILABLE:
            raise ValueError("pandas and numpy are required for forecasting")

        if len(data) < 14:
            raise ValueError(
                f"Insufficient data for forecasting. Need at least 14 days of history, "
                f"got {len(data)} days."
            )

        self.data = data.copy()
        self._history_length = len(data)

        # Select method if auto
        if self.method == 'auto':
            if STATSMODELS_AVAILABLE:
                # Use exponential smoothing for general time series
                self.method = 'exponential'
            else:
                self.method = 'moving_average'

        # Fit the selected model
        if self.method == 'arima' and STATSMODELS_AVAILABLE:
            self._fit_arima()
        elif self.method == 'exponential' and STATSMODELS_AVAILABLE:
            self._fit_exponential()
        elif self.method == 'moving_average':
            self._fit_moving_average()
        else:
            raise ValueError(
                f"Method '{self.method}' not available. "
                f"statsmodels available: {STATSMODELS_AVAILABLE}"
            )

        self.fitted = True

    def _fit_arima(self) -> None:
        """Fit ARIMA model."""
        # Use simple ARIMA(1,1,1) as default
        # In production, you'd want to tune p,d,q parameters
        values = self.data.iloc[:, 0].values
        self.model = ARIMA(values, order=(1, 1, 1))
        self.model = self.model.fit()

    def _fit_exponential(self) -> None:
        """Fit exponential smoothing model."""
        values = self.data.iloc[:, 0].values

        # Use simple exponential smoothing (no trend/seasonal)
        # For more complex patterns, could use trend='add' or seasonal='add'
        try:
            self.model = ExponentialSmoothing(
                values,
                trend=None,
                seasonal=None
            )
            self.model = self.model.fit()
        except Exception as e:
            warnings.warn(f"Exponential smoothing failed: {e}. Falling back to moving average.")
            self.method = 'moving_average'
            self._fit_moving_average()

    def _fit_moving_average(self) -> None:
        """Fit simple moving average model (no actual fitting needed)."""
        # Moving average doesn't require fitting, just storing data
        self.model = 'fitted'  # Marker that we're ready

    def predict(self, data: "pd.DataFrame") -> "np.ndarray":
        """
        Make predictions (not used for forecasting, use forecast() instead).

        Args:
            data: Input data (not used for time series forecasting)

        Returns:
            Empty array (use forecast() for time series predictions)
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before prediction")

        # For time series, use forecast() instead
        return np.array([])

    def evaluate(self, data: "pd.DataFrame", target: "np.ndarray") -> dict:
        """
        Evaluate forecasting model (basic implementation).

        Args:
            data: Test data with DatetimeIndex
            target: True values

        Returns:
            Dictionary with evaluation metrics (MAE, RMSE)
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before evaluation")

        if not NUMPY_AVAILABLE:
            return {"error": "numpy not available"}

        # Simple evaluation on test data
        predictions = self.forecast(len(target))['predictions']

        mae = np.mean(np.abs(predictions - target))
        rmse = np.sqrt(np.mean((predictions - target) ** 2))

        return {
            "mae": float(mae),
            "rmse": float(rmse),
            "method": self.method
        }

    def forecast(
        self,
        periods: int,
        confidence_levels: List[float] = [0.80, 0.95]
    ) -> Dict[str, List[float]]:
        """
        Generate forecast for the specified number of periods.

        Args:
            periods: Number of periods to forecast (e.g., 7 for 7 days)
            confidence_levels: Confidence levels for intervals (default: [0.80, 0.95])

        Returns:
            Dictionary with:
                - dates: List of forecast dates (as ISO strings)
                - predictions: Point predictions
                - lower_80: Lower bound of 80% confidence interval
                - upper_80: Upper bound of 80% confidence interval
                - lower_95: Lower bound of 95% confidence interval
                - upper_95: Upper bound of 95% confidence interval

        Raises:
            RuntimeError: If model has not been fitted
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before forecasting")

        if not PANDAS_AVAILABLE or not NUMPY_AVAILABLE:
            raise ValueError("pandas and numpy are required for forecasting")

        # Generate forecast dates
        last_date = self.data.index[-1]
        forecast_dates = [
            (last_date + timedelta(days=i+1)).isoformat()
            for i in range(periods)
        ]

        # Generate predictions based on method
        if self.method == 'arima' and STATSMODELS_AVAILABLE:
            result = self._forecast_arima(periods)
        elif self.method == 'exponential' and STATSMODELS_AVAILABLE:
            result = self._forecast_exponential(periods)
        else:
            result = self._forecast_moving_average(periods)

        # Add dates to result
        result['dates'] = forecast_dates

        return result

    def _forecast_arima(self, periods: int) -> Dict[str, List[float]]:
        """Generate ARIMA forecast with confidence intervals."""
        forecast_result = self.model.forecast(steps=periods, alpha=0.05)
        predictions = forecast_result.tolist()

        # Get prediction intervals
        pred_int = self.model.get_forecast(steps=periods)

        # 95% confidence interval
        ci_95 = pred_int.conf_int(alpha=0.05)
        lower_95 = ci_95.iloc[:, 0].tolist()
        upper_95 = ci_95.iloc[:, 1].tolist()

        # 80% confidence interval
        ci_80 = pred_int.conf_int(alpha=0.20)
        lower_80 = ci_80.iloc[:, 0].tolist()
        upper_80 = ci_80.iloc[:, 1].tolist()

        return {
            'predictions': predictions,
            'lower_80': lower_80,
            'upper_80': upper_80,
            'lower_95': lower_95,
            'upper_95': upper_95
        }

    def _forecast_exponential(self, periods: int) -> Dict[str, List[float]]:
        """Generate exponential smoothing forecast with confidence intervals."""
        forecast_result = self.model.forecast(steps=periods)
        predictions = forecast_result.tolist()

        # Exponential smoothing prediction intervals
        # Using simulation-based intervals
        pred_int = self.model.get_prediction(
            start=len(self.data),
            end=len(self.data) + periods - 1
        )

        # 95% confidence interval
        ci_95 = pred_int.conf_int(alpha=0.05)
        lower_95 = ci_95.iloc[:, 0].tolist()
        upper_95 = ci_95.iloc[:, 1].tolist()

        # 80% confidence interval
        ci_80 = pred_int.conf_int(alpha=0.20)
        lower_80 = ci_80.iloc[:, 0].tolist()
        upper_80 = ci_80.iloc[:, 1].tolist()

        return {
            'predictions': predictions,
            'lower_80': lower_80,
            'upper_80': upper_80,
            'lower_95': lower_95,
            'upper_95': upper_95
        }

    def _forecast_moving_average(self, periods: int) -> Dict[str, List[float]]:
        """
        Generate simple moving average forecast with estimated confidence intervals.

        Uses the mean of recent values as prediction and standard deviation
        to estimate confidence intervals.
        """
        values = self.data.iloc[:, 0].values

        # Use last 7 days for moving average (or all data if less)
        window = min(7, len(values))
        recent_values = values[-window:]

        # Prediction is the mean of recent values
        prediction = np.mean(recent_values)
        predictions = [float(prediction)] * periods

        # Estimate confidence intervals using standard deviation
        std = np.std(recent_values)

        # 80% confidence interval (z = 1.28)
        margin_80 = 1.28 * std
        lower_80 = [float(prediction - margin_80)] * periods
        upper_80 = [float(prediction + margin_80)] * periods

        # 95% confidence interval (z = 1.96)
        margin_95 = 1.96 * std
        lower_95 = [float(prediction - margin_95)] * periods
        upper_95 = [float(prediction + margin_95)] * periods

        return {
            'predictions': predictions,
            'lower_80': lower_80,
            'upper_80': upper_80,
            'lower_95': lower_95,
            'upper_95': upper_95
        }


def forecast_token_usage(
    db_path: str,
    periods: int = 7,
    method: str = 'auto'
) -> Dict[str, List[float]]:
    """
    Forecast token usage for the next N days.

    Args:
        db_path: Path to dream-studio SQLite database
        periods: Number of days to forecast (default: 7)
        method: Forecasting method ('auto', 'arima', 'exponential', 'moving_average')

    Returns:
        Forecast dictionary with dates, predictions, and confidence intervals

    Raises:
        ValueError: If insufficient historical data
    """
    if not PANDAS_AVAILABLE:
        raise ValueError("pandas is required for forecasting")

    import sqlite3

    # Load historical token usage
    conn = sqlite3.connect(db_path)
    query = """
        SELECT DATE(timestamp) as date, SUM(tokens) as total_tokens
        FROM token_usage
        GROUP BY DATE(timestamp)
        ORDER BY date
    """
    df = pd.read_sql_query(query, conn, parse_dates=['date'], index_col='date')
    conn.close()

    # Fit and forecast
    forecaster = TimeSeriesForecaster(method=method)
    forecaster.fit(df)
    return forecaster.forecast(periods)


def forecast_skill_usage(
    db_path: str,
    periods: int = 7,
    method: str = 'auto'
) -> Dict[str, List[float]]:
    """
    Forecast skill usage (total invocations) for the next N days.

    Args:
        db_path: Path to dream-studio SQLite database
        periods: Number of days to forecast (default: 7)
        method: Forecasting method ('auto', 'arima', 'exponential', 'moving_average')

    Returns:
        Forecast dictionary with dates, predictions, and confidence intervals

    Raises:
        ValueError: If insufficient historical data
    """
    if not PANDAS_AVAILABLE:
        raise ValueError("pandas is required for forecasting")

    import sqlite3

    # Load historical skill usage
    conn = sqlite3.connect(db_path)
    query = """
        SELECT DATE(timestamp) as date, COUNT(*) as total_invocations
        FROM skill_usage
        GROUP BY DATE(timestamp)
        ORDER BY date
    """
    df = pd.read_sql_query(query, conn, parse_dates=['date'], index_col='date')
    conn.close()

    # Fit and forecast
    forecaster = TimeSeriesForecaster(method=method)
    forecaster.fit(df)
    return forecaster.forecast(periods)


def forecast_session_counts(
    db_path: str,
    periods: int = 7,
    method: str = 'auto'
) -> Dict[str, List[float]]:
    """
    Forecast session counts for the next N days.

    Args:
        db_path: Path to dream-studio SQLite database
        periods: Number of days to forecast (default: 7)
        method: Forecasting method ('auto', 'arima', 'exponential', 'moving_average')

    Returns:
        Forecast dictionary with dates, predictions, and confidence intervals

    Raises:
        ValueError: If insufficient historical data
    """
    if not PANDAS_AVAILABLE:
        raise ValueError("pandas is required for forecasting")

    import sqlite3

    # Load historical session counts
    conn = sqlite3.connect(db_path)
    query = """
        SELECT DATE(start_time) as date, COUNT(*) as total_sessions
        FROM sessions
        GROUP BY DATE(start_time)
        ORDER BY date
    """
    df = pd.read_sql_query(query, conn, parse_dates=['date'], index_col='date')
    conn.close()

    # Fit and forecast
    forecaster = TimeSeriesForecaster(method=method)
    forecaster.fit(df)
    return forecaster.forecast(periods)


def generate_forecast_report(
    db_path: str,
    periods_short: int = 7,
    periods_long: int = 30
) -> Dict[str, Dict[str, List[float]]]:
    """
    Generate comprehensive forecast report for all metrics.

    Forecasts token usage, skill usage, and session counts for both
    short-term (7 days) and long-term (30 days) horizons.

    Args:
        db_path: Path to dream-studio SQLite database
        periods_short: Short-term forecast period (default: 7 days)
        periods_long: Long-term forecast period (default: 30 days)

    Returns:
        Dictionary with forecasts for each metric and time horizon:
        {
            'tokens_7d': {...},
            'tokens_30d': {...},
            'skills_7d': {...},
            'skills_30d': {...},
            'sessions_7d': {...},
            'sessions_30d': {...}
        }
    """
    report = {}

    try:
        report['tokens_7d'] = forecast_token_usage(db_path, periods_short)
        report['tokens_30d'] = forecast_token_usage(db_path, periods_long)
    except ValueError as e:
        report['tokens_error'] = str(e)

    try:
        report['skills_7d'] = forecast_skill_usage(db_path, periods_short)
        report['skills_30d'] = forecast_skill_usage(db_path, periods_long)
    except ValueError as e:
        report['skills_error'] = str(e)

    try:
        report['sessions_7d'] = forecast_session_counts(db_path, periods_short)
        report['sessions_30d'] = forecast_session_counts(db_path, periods_long)
    except ValueError as e:
        report['sessions_error'] = str(e)

    return report
