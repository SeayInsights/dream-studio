"""AlertEvaluator - Evaluates alert rules and triggers alerts for real-time monitoring"""
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


class AlertEvaluator:
    """Evaluates alert rules against metrics and triggers alerts when thresholds are exceeded"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize AlertEvaluator

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

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
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Fetch all enabled alert rules
            cursor.execute("""
                SELECT rule_id, rule_name, metric_path, condition, threshold, severity
                FROM alert_rules
                WHERE enabled = 1
            """)

            rules = cursor.fetchall()

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
        finally:
            try:
                conn.close()
            except:
                pass

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
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO alert_history (alert_id, rule_id, triggered_at, metric_value, severity)
                VALUES (?, ?, ?, ?, ?)
            """, (
                alert_id,
                rule["rule_id"],
                triggered_at,
                value,
                rule["severity"]
            ))

            conn.commit()
            conn.close()

            return alert_data

        except sqlite3.Error as e:
            print(f"Failed to save alert to database: {e}")
            return None
