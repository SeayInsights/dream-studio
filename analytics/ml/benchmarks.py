"""
Comparative benchmarking system for dream-studio analytics.

Provides benchmarking capabilities for:
- Current vs historical metrics comparison
- Percentile rankings (e.g., "better than 75% of historical periods")
- Trend analysis (improving, stable, declining)
- Baseline comparison (configurable thresholds)

Metrics benchmarked:
- Session count
- Skill usage
- Token usage
- Success rate

Example usage:
    >>> from analytics.ml.benchmarks import BenchmarkEngine, run_benchmark_suite
    >>> import pandas as pd
    >>>
    >>> # Run full benchmark suite from database
    >>> results = run_benchmark_suite('~/.dream-studio/state/studio.db')
    >>> for result in results:
    ...     print(f"{result['metric']}: {result['status']} (percentile: {result['percentile']:.1%})")
    >>>
    >>> # Or use the engine directly with custom baselines
    >>> engine = BenchmarkEngine(baselines={'session_count': 10.0})
    >>> engine.fit(historical_df)
    >>> benchmark = engine.benchmark_metric('session_count', current_value=15.0)
    >>> print(f"Trend: {benchmark['trend']}, Status: {benchmark['status']}")
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Literal
import warnings

from .base import BaseModel, PANDAS_AVAILABLE, NUMPY_AVAILABLE

if PANDAS_AVAILABLE:
    import pandas as pd

if NUMPY_AVAILABLE:
    import numpy as np


TrendType = Literal["improving", "stable", "declining"]
StatusType = Literal["above_baseline", "at_baseline", "below_baseline"]


class BenchmarkEngine(BaseModel):
    """
    Comparative benchmarking engine for dream-studio analytics.

    Compares current performance metrics against historical baselines and
    calculates percentile rankings, trend directions, and baseline status.

    Attributes:
        fitted: Whether the model has been trained
        baselines: Dictionary of metric name → baseline threshold values
        historical_stats: Historical statistics for each metric
        data: Training data (historical metrics)
    """

    def __init__(self, baselines: Optional[Dict[str, float]] = None):
        """
        Initialize the benchmark engine.

        Args:
            baselines: Optional dict of metric name → baseline threshold.
                      Example: {'session_count': 10.0, 'token_usage': 50000.0}
                      If not provided, uses historical mean as baseline.
        """
        super().__init__()
        self.baselines = baselines or {}
        self.historical_stats: Dict[str, Dict[str, float]] = {}
        self.data: Optional["pd.DataFrame"] = None
        self._min_history_days = 14

    def fit(self, data: "pd.DataFrame") -> None:
        """
        Train the benchmark engine on historical metrics data.

        Expected DataFrame structure:
        - Index: DatetimeIndex (date of measurement)
        - Columns: One or more metric columns (session_count, skill_usage, token_usage, success_rate)

        Args:
            data: Historical metrics as a pandas DataFrame with DatetimeIndex

        Raises:
            ValueError: If insufficient history (< 14 days) or pandas/numpy not available
        """
        if not PANDAS_AVAILABLE or not NUMPY_AVAILABLE:
            raise ValueError("pandas and numpy are required for benchmarking")

        if len(data) < self._min_history_days:
            raise ValueError(
                f"Insufficient data for benchmarking. Need at least {self._min_history_days} days "
                f"of history, got {len(data)} days."
            )

        if not isinstance(data.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have a DatetimeIndex")

        self.data = data.copy()

        # Calculate historical statistics for each metric
        for metric_col in data.columns:
            values = data[metric_col].dropna()

            if len(values) < self._min_history_days:
                warnings.warn(
                    f"Metric '{metric_col}' has only {len(values)} non-null values "
                    f"(minimum {self._min_history_days} recommended)"
                )
                continue

            self.historical_stats[metric_col] = {
                'mean': float(values.mean()),
                'median': float(values.median()),
                'std': float(values.std()),
                'min': float(values.min()),
                'max': float(values.max()),
                'p25': float(values.quantile(0.25)),
                'p50': float(values.quantile(0.50)),
                'p75': float(values.quantile(0.75)),
                'p90': float(values.quantile(0.90)),
                'p95': float(values.quantile(0.95)),
                'count': int(len(values)),
            }

        self.fitted = True

    def predict(self, data: "pd.DataFrame") -> "np.ndarray":
        """
        Not used for benchmarking. Use benchmark_metric() instead.

        Args:
            data: Input data (not used)

        Returns:
            Empty array
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before prediction")

        return np.array([])

    def evaluate(self, data: "pd.DataFrame", target: "np.ndarray") -> dict:
        """
        Evaluate benchmarking model (basic implementation).

        Args:
            data: Test data
            target: True values

        Returns:
            Dictionary with evaluation metrics
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before evaluation")

        # For benchmarking, evaluation is about accuracy of trend detection
        # This is a simplified implementation
        return {
            "metrics_available": list(self.historical_stats.keys()),
            "history_days": len(self.data) if self.data is not None else 0,
        }

    def benchmark_metric(
        self,
        metric_name: str,
        current_value: float,
        current_period_days: int = 7,
    ) -> Dict:
        """
        Benchmark a single metric against historical data.

        Args:
            metric_name: Name of the metric to benchmark (must match column in training data)
            current_value: Current metric value to benchmark
            current_period_days: Number of days the current value represents (default: 7)

        Returns:
            Dictionary with benchmark results:
            {
                'metric': str,          # Metric name
                'current': float,       # Current value
                'baseline': float,      # Baseline threshold (from config or historical mean)
                'percentile': float,    # Percentile rank (0.0 to 1.0)
                'trend': str,           # 'improving', 'stable', or 'declining'
                'status': str,          # 'above_baseline', 'at_baseline', or 'below_baseline'
                'comparison': {         # Additional comparison stats
                    'vs_mean': float,       # % difference from historical mean
                    'vs_median': float,     # % difference from historical median
                    'vs_p90': float,        # % difference from 90th percentile
                },
                'historical': {         # Historical statistics for context
                    'mean': float,
                    'median': float,
                    'std': float,
                    'min': float,
                    'max': float,
                }
            }

        Raises:
            RuntimeError: If model has not been fitted
            ValueError: If metric_name not found in historical data
        """
        if not self.fitted:
            raise RuntimeError("Model must be fitted before benchmarking")

        if metric_name not in self.historical_stats:
            raise ValueError(
                f"Metric '{metric_name}' not found in historical data. "
                f"Available metrics: {list(self.historical_stats.keys())}"
            )

        stats = self.historical_stats[metric_name]

        # Determine baseline (use configured baseline or historical mean)
        baseline = self.baselines.get(metric_name, stats['mean'])

        # Calculate percentile rank
        percentile = self._calculate_percentile(metric_name, current_value)

        # Determine trend (using recent historical data if available)
        trend = self._calculate_trend(metric_name, current_value, current_period_days)

        # Determine status vs baseline
        status = self._determine_status(current_value, baseline)

        # Calculate comparison percentages
        comparison = {
            'vs_mean': self._percent_diff(current_value, stats['mean']),
            'vs_median': self._percent_diff(current_value, stats['median']),
            'vs_p90': self._percent_diff(current_value, stats['p90']),
        }

        return {
            'metric': metric_name,
            'current': float(current_value),
            'baseline': float(baseline),
            'percentile': float(percentile),
            'trend': trend,
            'status': status,
            'comparison': comparison,
            'historical': {
                'mean': stats['mean'],
                'median': stats['median'],
                'std': stats['std'],
                'min': stats['min'],
                'max': stats['max'],
            }
        }

    def _calculate_percentile(self, metric_name: str, value: float) -> float:
        """
        Calculate percentile rank of a value within historical data.

        Args:
            metric_name: Metric name
            value: Value to rank

        Returns:
            Percentile rank from 0.0 to 1.0 (e.g., 0.75 = better than 75% of history)
        """
        if self.data is None:
            return 0.5  # Default to median if no data

        historical_values = self.data[metric_name].dropna().values

        if len(historical_values) == 0:
            return 0.5

        # Count how many historical values are less than current value
        count_below = np.sum(historical_values < value)
        percentile = count_below / len(historical_values)

        return percentile

    def _calculate_trend(
        self,
        metric_name: str,
        current_value: float,
        current_period_days: int
    ) -> TrendType:
        """
        Determine trend direction by comparing current value to recent historical averages.

        Compares current value against averages from:
        - Last 30 days
        - Last 60 days
        - Last 90 days

        Args:
            metric_name: Metric name
            current_value: Current value
            current_period_days: Number of days current value represents

        Returns:
            'improving', 'stable', or 'declining'
        """
        if self.data is None or len(self.data) < 30:
            return 'stable'  # Not enough data for trend analysis

        # Get recent historical averages for comparison windows
        try:
            last_date = self.data.index[-1]

            # Calculate averages for 30, 60, 90 day windows
            avg_30d = self._get_historical_avg(metric_name, last_date, days=30)
            avg_60d = self._get_historical_avg(metric_name, last_date, days=60)
            avg_90d = self._get_historical_avg(metric_name, last_date, days=90)

            # Compare current to historical averages
            # Use weighted comparison (more weight to recent history)
            improvements = 0
            comparisons = 0

            if avg_30d is not None:
                if current_value > avg_30d * 1.05:  # 5% improvement threshold
                    improvements += 3  # Weight recent history more
                elif current_value < avg_30d * 0.95:  # 5% decline threshold
                    improvements -= 3
                comparisons += 3

            if avg_60d is not None:
                if current_value > avg_60d * 1.05:
                    improvements += 2
                elif current_value < avg_60d * 0.95:
                    improvements -= 2
                comparisons += 2

            if avg_90d is not None:
                if current_value > avg_90d * 1.05:
                    improvements += 1
                elif current_value < avg_90d * 0.95:
                    improvements -= 1
                comparisons += 1

            if comparisons == 0:
                return 'stable'

            # Calculate net trend score
            trend_score = improvements / comparisons

            if trend_score > 0.3:
                return 'improving'
            elif trend_score < -0.3:
                return 'declining'
            else:
                return 'stable'

        except Exception as e:
            warnings.warn(f"Error calculating trend: {e}")
            return 'stable'

    def _get_historical_avg(
        self,
        metric_name: str,
        end_date: datetime,
        days: int
    ) -> Optional[float]:
        """
        Get historical average for a metric over a specific window.

        Args:
            metric_name: Metric name
            end_date: End date of window (exclusive)
            days: Number of days to look back

        Returns:
            Average value or None if insufficient data
        """
        if self.data is None:
            return None

        start_date = end_date - timedelta(days=days)

        # Filter data for window (excluding end_date to avoid overlap with current)
        window_data = self.data.loc[
            (self.data.index >= start_date) & (self.data.index < end_date),
            metric_name
        ].dropna()

        if len(window_data) < min(7, days // 2):  # Need at least half the period or 7 days
            return None

        return float(window_data.mean())

    def _determine_status(self, current_value: float, baseline: float) -> StatusType:
        """
        Determine status of current value vs baseline.

        Uses a 2% tolerance band around baseline to determine 'at_baseline'.

        Args:
            current_value: Current metric value
            baseline: Baseline threshold

        Returns:
            'above_baseline', 'at_baseline', or 'below_baseline'
        """
        tolerance = 0.02  # 2% tolerance band

        if current_value > baseline * (1 + tolerance):
            return 'above_baseline'
        elif current_value < baseline * (1 - tolerance):
            return 'below_baseline'
        else:
            return 'at_baseline'

    def _percent_diff(self, current: float, reference: float) -> float:
        """
        Calculate percentage difference between current and reference.

        Args:
            current: Current value
            reference: Reference value

        Returns:
            Percentage difference (e.g., 0.25 = 25% higher, -0.10 = 10% lower)
        """
        if reference == 0:
            return 0.0 if current == 0 else float('inf')

        return (current - reference) / reference


def run_benchmark_suite(
    db_path: str,
    current_period_days: int = 7,
    baselines: Optional[Dict[str, float]] = None
) -> List[Dict]:
    """
    Run comprehensive benchmark suite for all metrics.

    Benchmarks:
    - Session count (per day)
    - Skill usage (invocations per day)
    - Token usage (tokens per day)
    - Success rate (% of successful sessions)

    Args:
        db_path: Path to dream-studio SQLite database
        current_period_days: Number of days for "current" period (default: 7)
        baselines: Optional dict of metric → baseline threshold

    Returns:
        List of benchmark result dictionaries (one per metric)

    Raises:
        ValueError: If insufficient historical data
    """
    if not PANDAS_AVAILABLE:
        raise ValueError("pandas is required for benchmarking")

    import sqlite3

    conn = sqlite3.connect(db_path)

    try:
        # Load historical metrics
        historical_df = _load_historical_metrics(conn)

        if len(historical_df) < 14:
            raise ValueError(
                f"Insufficient historical data for benchmarking. "
                f"Need at least 14 days, got {len(historical_df)} days."
            )

        # Calculate current metrics (last N days)
        current_metrics = _calculate_current_metrics(conn, current_period_days)

        # Initialize and fit benchmark engine
        engine = BenchmarkEngine(baselines=baselines)
        engine.fit(historical_df)

        # Benchmark each metric
        results = []
        for metric_name, current_value in current_metrics.items():
            if metric_name in historical_df.columns:
                benchmark = engine.benchmark_metric(
                    metric_name,
                    current_value,
                    current_period_days
                )
                results.append(benchmark)

        return results

    finally:
        conn.close()


def _load_historical_metrics(conn) -> "pd.DataFrame":
    """
    Load historical metrics from database.

    Args:
        conn: SQLite connection

    Returns:
        DataFrame with DatetimeIndex and metric columns
    """
    # Session counts per day
    sessions_query = """
        SELECT DATE(start_time) as date, COUNT(*) as session_count
        FROM sessions
        WHERE start_time IS NOT NULL
        GROUP BY DATE(start_time)
        ORDER BY date
    """
    sessions_df = pd.read_sql_query(sessions_query, conn, parse_dates=['date'], index_col='date')

    # Skill usage per day
    skills_query = """
        SELECT DATE(invoked_at) as date, COUNT(*) as skill_usage
        FROM skill_usage
        WHERE invoked_at IS NOT NULL
        GROUP BY DATE(invoked_at)
        ORDER BY date
    """
    skills_df = pd.read_sql_query(skills_query, conn, parse_dates=['date'], index_col='date')

    # Token usage per day
    tokens_query = """
        SELECT DATE(timestamp) as date, SUM(tokens) as token_usage
        FROM token_usage
        WHERE timestamp IS NOT NULL
        GROUP BY DATE(timestamp)
        ORDER BY date
    """
    tokens_df = pd.read_sql_query(tokens_query, conn, parse_dates=['date'], index_col='date')

    # Success rate per day (sessions with success=1 / total sessions)
    success_query = """
        SELECT
            DATE(start_time) as date,
            CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as success_rate
        FROM sessions
        WHERE start_time IS NOT NULL
        GROUP BY DATE(start_time)
        ORDER BY date
    """
    success_df = pd.read_sql_query(success_query, conn, parse_dates=['date'], index_col='date')

    # Merge all metrics into single DataFrame
    metrics_df = pd.concat([sessions_df, skills_df, tokens_df, success_df], axis=1)

    # Fill NaN values with 0 for counts (days with no activity)
    metrics_df['session_count'] = metrics_df['session_count'].fillna(0)
    metrics_df['skill_usage'] = metrics_df['skill_usage'].fillna(0)
    metrics_df['token_usage'] = metrics_df['token_usage'].fillna(0)
    # Success rate stays NaN if there were no sessions that day

    return metrics_df


def _calculate_current_metrics(conn, days: int) -> Dict[str, float]:
    """
    Calculate current period metrics.

    Args:
        conn: SQLite connection
        days: Number of days for current period

    Returns:
        Dictionary of metric name → current value
    """
    # Session count (last N days)
    sessions_query = f"""
        SELECT COUNT(*) as count
        FROM sessions
        WHERE start_time >= datetime('now', '-{days} days')
    """
    session_count = pd.read_sql_query(sessions_query, conn)['count'].iloc[0]

    # Skill usage (last N days)
    skills_query = f"""
        SELECT COUNT(*) as count
        FROM skill_usage
        WHERE invoked_at >= datetime('now', '-{days} days')
    """
    skill_usage = pd.read_sql_query(skills_query, conn)['count'].iloc[0]

    # Token usage (last N days)
    tokens_query = f"""
        SELECT SUM(tokens) as total
        FROM token_usage
        WHERE timestamp >= datetime('now', '-{days} days')
    """
    token_usage_result = pd.read_sql_query(tokens_query, conn)['total'].iloc[0]
    token_usage = token_usage_result if token_usage_result is not None else 0

    # Success rate (last N days)
    success_query = f"""
        SELECT
            CAST(SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS FLOAT) / COUNT(*) as rate
        FROM sessions
        WHERE start_time >= datetime('now', '-{days} days')
    """
    success_rate_result = pd.read_sql_query(success_query, conn)['rate'].iloc[0]
    success_rate = success_rate_result if success_rate_result is not None else 0.0

    # Convert to per-day averages
    return {
        'session_count': float(session_count) / days,
        'skill_usage': float(skill_usage) / days,
        'token_usage': float(token_usage) / days,
        'success_rate': float(success_rate),  # Already a rate, not a count
    }
