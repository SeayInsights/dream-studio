"""Validation failure monitoring and alerting.

Tracks validation failures and raises alerts when failure rates exceed thresholds.
Part of Phase 2: State Trustworthiness.

Created: 2026-05-07
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import logging

from core.config.database import get_connection

logger = logging.getLogger(__name__)


@dataclass
class ValidationMetrics:
    """Validation failure metrics for a time window."""

    total_failures: int
    unique_event_types: int
    most_common_failure: Optional[str]
    failure_rate: float  # failures per minute
    time_window_minutes: int


@dataclass
class ValidationAlert:
    """Alert for validation failure threshold breach."""

    alert_level: str  # 'warning', 'critical'
    message: str
    metrics: ValidationMetrics
    timestamp: datetime


class ValidationMonitor:
    """Monitor validation failures and generate alerts."""

    # Alert thresholds
    WARNING_THRESHOLD = 10  # failures per minute
    CRITICAL_THRESHOLD = 50  # failures per minute

    def __init__(self):
        """Initialize validation monitor."""
        self.conn = get_connection(read_only=True)

    def get_metrics(self, minutes: int = 60) -> ValidationMetrics:
        """
        Get validation failure metrics for the past N minutes.

        Args:
            minutes: Time window in minutes (default: 60)

        Returns:
            ValidationMetrics object
        """
        cursor = self.conn.execute(
            """
            SELECT
                COUNT(*) as total_failures,
                COUNT(DISTINCT event_type) as unique_types,
                event_type as most_common
            FROM validation_failures
            WHERE attempted_at > datetime('now', ? || ' minutes')
            GROUP BY event_type
            ORDER BY COUNT(*) DESC
            LIMIT 1
            """,
            (f"-{minutes}",),
        )

        row = cursor.fetchone()

        if row and row[0] > 0:
            total = row[0]
            unique = row[1]
            most_common = row[2]
            rate = total / minutes
        else:
            total = 0
            unique = 0
            most_common = None
            rate = 0.0

        return ValidationMetrics(
            total_failures=total,
            unique_event_types=unique,
            most_common_failure=most_common,
            failure_rate=rate,
            time_window_minutes=minutes,
        )

    def check_thresholds(self, metrics: ValidationMetrics) -> Optional[ValidationAlert]:
        """
        Check if metrics breach alert thresholds.

        Args:
            metrics: ValidationMetrics to check

        Returns:
            ValidationAlert if threshold breached, None otherwise
        """
        if metrics.failure_rate >= self.CRITICAL_THRESHOLD:
            return ValidationAlert(
                alert_level="critical",
                message=(
                    f"CRITICAL: Validation failure rate {metrics.failure_rate:.1f}/min "
                    f"exceeds threshold {self.CRITICAL_THRESHOLD}/min"
                ),
                metrics=metrics,
                timestamp=datetime.now(timezone.utc),
            )
        elif metrics.failure_rate >= self.WARNING_THRESHOLD:
            return ValidationAlert(
                alert_level="warning",
                message=(
                    f"WARNING: Validation failure rate {metrics.failure_rate:.1f}/min "
                    f"exceeds threshold {self.WARNING_THRESHOLD}/min"
                ),
                metrics=metrics,
                timestamp=datetime.now(timezone.utc),
            )

        return None

    def get_failure_breakdown(self, minutes: int = 60) -> List[Tuple[str, int]]:
        """
        Get breakdown of failures by event type.

        Args:
            minutes: Time window in minutes

        Returns:
            List of (event_type, count) tuples, ordered by count DESC
        """
        cursor = self.conn.execute(
            """
            SELECT event_type, COUNT(*) as count
            FROM validation_failures
            WHERE attempted_at > datetime('now', ? || ' minutes')
            GROUP BY event_type
            ORDER BY count DESC
            """,
            (f"-{minutes}",),
        )

        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_error_patterns(self, minutes: int = 60) -> Dict[str, int]:
        """
        Identify common error patterns in validation failures.

        Args:
            minutes: Time window in minutes

        Returns:
            Dict mapping error pattern to count
        """
        cursor = self.conn.execute(
            """
            SELECT errors
            FROM validation_failures
            WHERE attempted_at > datetime('now', ? || ' minutes')
            """,
            (f"-{minutes}",),
        )

        # Parse error patterns
        patterns = {}
        for (errors_json,) in cursor.fetchall():
            # Extract first error message as pattern
            if errors_json and errors_json.startswith("["):
                # Simple pattern: check for common substrings
                if "Schema validation failed" in errors_json:
                    patterns["schema_validation"] = patterns.get("schema_validation", 0) + 1
                if "Invalid event_type format" in errors_json:
                    patterns["event_type_format"] = patterns.get("event_type_format", 0) + 1
                if "Trace must contain" in errors_json:
                    patterns["missing_trace_id"] = patterns.get("missing_trace_id", 0) + 1
                if "Invalid severity" in errors_json:
                    patterns["invalid_severity"] = patterns.get("invalid_severity", 0) + 1

        return patterns

    def monitor_and_alert(self, minutes: int = 60) -> Optional[ValidationAlert]:
        """
        Check validation failures and return alert if threshold breached.

        Args:
            minutes: Time window to check

        Returns:
            ValidationAlert if alert should be raised, None otherwise
        """
        metrics = self.get_metrics(minutes)
        alert = self.check_thresholds(metrics)

        if alert:
            logger.warning(
                f"Validation alert triggered: {alert.message} "
                f"({metrics.total_failures} failures in {minutes}min)"
            )

            # Log breakdown
            breakdown = self.get_failure_breakdown(minutes)
            if breakdown:
                logger.warning(f"Top failing event types:")
                for event_type, count in breakdown[:5]:
                    logger.warning(f"  - {event_type}: {count}")

            # Log error patterns
            patterns = self.get_error_patterns(minutes)
            if patterns:
                logger.warning(f"Error patterns:")
                for pattern, count in sorted(patterns.items(), key=lambda x: x[1], reverse=True):
                    logger.warning(f"  - {pattern}: {count}")

        return alert

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
        return False
