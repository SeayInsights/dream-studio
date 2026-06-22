"""RuleManager - Manages alert rules for real-time monitoring"""

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional, Any
from core.config.database import get_connection, transaction
from core.event_store import studio_db


def _default_db_path() -> Path:
    # Delegate to the canonical resolver in core.config.database so the
    # DREAM_STUDIO_DB_PATH env-var override is honored uniformly. Local
    # function preserved for backward-compat with existing callers below.
    from core.config.database import _default_db_path as _canonical_default_db_path

    return _canonical_default_db_path()


class RuleManager:
    """Manages alert rules in the alert_rules table"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize RuleManager

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

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = (
            studio_db._connect(self._explicit_db_path)
            if self._explicit_db_path is not None
            else get_connection()
        )
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def _transaction(self):
        """Write through the configured database authority."""
        if self._explicit_db_path is not None:
            with studio_db._db_transaction(self._explicit_db_path) as conn:
                yield conn
        else:
            with transaction() as conn:
                yield conn

    def create_rule(self, rule_def: dict) -> str:
        """
        Create a new alert rule

        Args:
            rule_def: Rule definition dictionary with required fields:
                - rule_name: str - Name of the rule
                - metric_path: str - Path to metric (e.g., 'skill.success_rate')
                - condition: str - Comparison operator ('gt', 'lt', 'eq', 'gte', 'lte')
                - threshold: float - Threshold value to trigger alert
                - severity: str (optional) - Alert severity ('info', 'warning', 'critical')
                - enabled: bool (optional) - Whether rule is active (default: True)

        Returns:
            str: Generated rule_id

        Raises:
            ValueError: If required fields are missing or invalid
        """
        # Validate required fields
        required_fields = ["rule_name", "metric_path", "condition", "threshold"]
        missing_fields = [field for field in required_fields if field not in rule_def]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        # Validate condition
        valid_conditions = ["gt", "lt", "eq", "gte", "lte"]
        if rule_def["condition"] not in valid_conditions:
            raise ValueError(
                f"Invalid condition: {rule_def['condition']}. Must be one of: {', '.join(valid_conditions)}"
            )

        # Generate unique rule_id
        rule_id = str(uuid.uuid4())

        # Extract optional fields
        severity = rule_def.get("severity", "warning")
        enabled = rule_def.get("enabled", True)

        try:
            with self._transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO alert_rules (
                        rule_id, rule_name, metric_path, condition,
                        threshold, severity, enabled
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        rule_id,
                        rule_def["rule_name"],
                        rule_def["metric_path"],
                        rule_def["condition"],
                        float(rule_def["threshold"]),
                        severity,
                        1 if enabled else 0,
                    ),
                )
            return rule_id

        except Exception as e:
            raise RuntimeError(f"Failed to create alert rule: {str(e)}")

    def update_rule(self, rule_id: str, updates: dict) -> bool:
        """
        Update an existing alert rule

        Args:
            rule_id: ID of the rule to update
            updates: Dictionary of fields to update (can include: rule_name,
                    metric_path, condition, threshold, severity, enabled)

        Returns:
            bool: True if rule was updated, False if rule not found

        Raises:
            ValueError: If invalid fields or values are provided
        """
        # Validate allowed fields
        allowed_fields = [
            "rule_name",
            "metric_path",
            "condition",
            "threshold",
            "severity",
            "enabled",
        ]
        invalid_fields = [field for field in updates if field not in allowed_fields]
        if invalid_fields:
            raise ValueError(f"Invalid fields: {', '.join(invalid_fields)}")

        if not updates:
            return False

        # Validate condition if provided
        if "condition" in updates:
            valid_conditions = ["gt", "lt", "eq", "gte", "lte"]
            if updates["condition"] not in valid_conditions:
                raise ValueError(
                    f"Invalid condition: {updates['condition']}. Must be one of: {', '.join(valid_conditions)}"
                )

        try:
            # Build UPDATE query dynamically
            set_clauses = []
            values = []

            for field, value in updates.items():
                set_clauses.append(f"{field} = ?")
                if field == "enabled":
                    values.append(1 if value else 0)
                elif field == "threshold":
                    values.append(float(value))
                else:
                    values.append(value)

            values.append(rule_id)

            query = f"""
                UPDATE alert_rules
                SET {', '.join(set_clauses)}
                WHERE rule_id = ?
            """

            with self._transaction() as conn:
                cursor = conn.execute(query, values)
                return cursor.rowcount > 0

        except Exception as e:
            raise RuntimeError(f"Failed to update alert rule: {str(e)}")

    def delete_rule(self, rule_id: str) -> bool:
        """
        Delete an alert rule

        Args:
            rule_id: ID of the rule to delete

        Returns:
            bool: True if rule was deleted, False if rule not found
        """
        try:
            with self._transaction() as conn:
                cursor = conn.execute("DELETE FROM alert_rules WHERE rule_id = ?", (rule_id,))
                return cursor.rowcount > 0

        except Exception as e:
            raise RuntimeError(f"Failed to delete alert rule: {str(e)}")

    def get_active_rules(self) -> List[Dict[str, Any]]:
        """
        Get all enabled alert rules

        Returns:
            List[Dict]: List of active rules, each as a dictionary with fields:
                rule_id, rule_name, metric_path, condition, threshold, severity, enabled
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                SELECT
                    rule_id,
                    rule_name,
                    metric_path,
                    condition,
                    threshold,
                    severity,
                    enabled
                FROM alert_rules
                WHERE enabled = 1
                ORDER BY severity DESC, rule_name ASC
            """)

            rules = []
            for row in cursor.fetchall():
                rules.append(
                    {
                        "rule_id": row["rule_id"],
                        "rule_name": row["rule_name"],
                        "metric_path": row["metric_path"],
                        "condition": row["condition"],
                        "threshold": row["threshold"],
                        "severity": row["severity"],
                        "enabled": bool(row["enabled"]),
                    }
                )

            return rules

        finally:
            conn.close()

    def enable_rule(self, rule_id: str) -> bool:
        """
        Enable an alert rule

        Args:
            rule_id: ID of the rule to enable

        Returns:
            bool: True if rule was enabled, False if rule not found
        """
        return self.update_rule(rule_id, {"enabled": True})

    def disable_rule(self, rule_id: str) -> bool:
        """
        Disable an alert rule

        Args:
            rule_id: ID of the rule to disable

        Returns:
            bool: True if rule was disabled, False if rule not found
        """
        return self.update_rule(rule_id, {"enabled": False})
