"""AlertEvaluator - Evaluates alert rules and triggers alerts for real-time monitoring"""

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from core.config.database import get_connection, transaction
from core.event_store import studio_db


def _default_db_path() -> Path:
    return Path.home() / ".dream-studio" / "state" / "studio.db"


class AlertEvaluator:
    """Evaluates alert rules against metrics and triggers alerts when thresholds are exceeded"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize AlertEvaluator

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        requested_path = Path(db_path).expanduser() if db_path is not None else None
        default_path = _default_db_path()
        self._explicit_db_path = (
            requested_path
            if requested_path is not None and requested_path != default_path
            else None
        )
        self.db_path = str(requested_path or default_path)

    @contextmanager
    def _connection(self):
        """Open the configured database, honoring explicit test DB paths."""
        conn = (
            studio_db._connect(self._explicit_db_path)
            if self._explicit_db_path is not None
            else get_connection()
        )
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _transaction(self):
        """Write through the configured database authority."""
        if self._explicit_db_path is not None:
            with studio_db._db_transaction(self._explicit_db_path) as conn:
                yield conn
        else:
            with transaction() as conn:
                yield conn

    def evaluate_rules(self, metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Evaluate all active alert rules against current metrics

        Args:
            metrics: Dictionary of metric paths to values (e.g., {'skill.success_rate': 0.85})

        Returns:
            List of triggered alert dictionaries containing:
                - alert_id: str
                - rule_id: str
                - rule_name: str
                - metric_path: str
                - metric_value: float
                - threshold: float
                - severity: str
                - triggered_at: str (ISO format)
        """
        triggered_alerts = []

        try:
            with self._connection() as conn:
                conn.row_factory = sqlite3.Row

                # Fetch all enabled alert rules
                rules = conn.execute("""
                    SELECT rule_id, rule_name, metric_path, condition, threshold, severity
                    FROM alert_rules
                    WHERE enabled = 1
                """).fetchall()

                for rule in rules:
                    metric_path = rule["metric_path"]

                    # Check if this metric exists in the provided metrics
                    if metric_path not in metrics:
                        continue

                    metric_value = metrics[metric_path]

                    # Convert metric value to float if it's not already
                    try:
                        metric_value = float(metric_value)
                    except (TypeError, ValueError):
                        continue

                    # Check if threshold condition is met
                    threshold = rule["threshold"]
                    condition = rule["condition"]

                    if self.check_threshold(metric_value, condition, threshold):
                        # Trigger alert
                        alert = self.trigger_alert(dict(rule), metric_value)
                        if alert:
                            triggered_alerts.append(alert)

        except sqlite3.Error as e:
            # Log error but don't crash - return partial results
            print(f"Database error during rule evaluation: {e}")

        return triggered_alerts

    def check_threshold(self, value: float, condition: str, threshold: float) -> bool:
        """
        Check if a value meets the specified threshold condition

        Args:
            value: Current metric value
            condition: Comparison operator ('gt', 'lt', 'eq', 'gte', 'lte')
            threshold: Threshold value to compare against

        Returns:
            True if condition is met, False otherwise
        """
        if condition == "gt":
            return value > threshold
        elif condition == "gte":
            return value >= threshold
        elif condition == "lt":
            return value < threshold
        elif condition == "lte":
            return value <= threshold
        elif condition == "eq":
            return value == threshold
        else:
            # Unknown condition - return False to avoid false positives
            return False

    def trigger_alert(self, rule: Dict[str, Any], value: float) -> Optional[Dict[str, Any]]:
        """
        Create an alert record and save to alert_history table

        Args:
            rule: Alert rule dictionary containing rule_id, rule_name, severity, etc.
            value: Actual metric value that triggered the alert

        Returns:
            Alert data dictionary if successful, None if failed
        """
        alert_id = str(uuid.uuid4())
        triggered_at = datetime.now(timezone.utc).isoformat()

        alert_data = {
            "alert_id": alert_id,
            "rule_id": rule["rule_id"],
            "rule_name": rule["rule_name"],
            "metric_path": rule["metric_path"],
            "metric_value": value,
            "threshold": rule["threshold"],
            "severity": rule["severity"],
            "triggered_at": triggered_at,
        }

        try:
            with self._transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO alert_history (alert_id, rule_id, triggered_at, metric_value, severity)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (alert_id, rule["rule_id"], triggered_at, value, rule["severity"]),
                )

            return alert_data

        except sqlite3.Error as e:
            print(f"Failed to save alert to database: {e}")
            return None
