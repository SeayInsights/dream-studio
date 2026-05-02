"""RuleManager - Manages alert rules for real-time monitoring"""
import sqlite3
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any


class RuleManager:
    """Manages alert rules in the alert_rules table"""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize RuleManager

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

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
        required_fields = ['rule_name', 'metric_path', 'condition', 'threshold']
        missing_fields = [field for field in required_fields if field not in rule_def]
        if missing_fields:
            raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")

        # Validate condition
        valid_conditions = ['gt', 'lt', 'eq', 'gte', 'lte']
        if rule_def['condition'] not in valid_conditions:
            raise ValueError(f"Invalid condition: {rule_def['condition']}. Must be one of: {', '.join(valid_conditions)}")

        # Generate unique rule_id
        rule_id = str(uuid.uuid4())

        # Extract optional fields
        severity = rule_def.get('severity', 'warning')
        enabled = rule_def.get('enabled', True)

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO alert_rules (
                    rule_id, rule_name, metric_path, condition,
                    threshold, severity, enabled
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                rule_id,
                rule_def['rule_name'],
                rule_def['metric_path'],
                rule_def['condition'],
                float(rule_def['threshold']),
                severity,
                1 if enabled else 0
            ))
            conn.commit()
            return rule_id

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to create alert rule: {str(e)}")

        finally:
            conn.close()

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
        allowed_fields = ['rule_name', 'metric_path', 'condition', 'threshold', 'severity', 'enabled']
        invalid_fields = [field for field in updates.keys() if field not in allowed_fields]
        if invalid_fields:
            raise ValueError(f"Invalid fields: {', '.join(invalid_fields)}")

        if not updates:
            return False

        # Validate condition if provided
        if 'condition' in updates:
            valid_conditions = ['gt', 'lt', 'eq', 'gte', 'lte']
            if updates['condition'] not in valid_conditions:
                raise ValueError(f"Invalid condition: {updates['condition']}. Must be one of: {', '.join(valid_conditions)}")

        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            # Build UPDATE query dynamically
            set_clauses = []
            values = []

            for field, value in updates.items():
                set_clauses.append(f"{field} = ?")
                if field == 'enabled':
                    values.append(1 if value else 0)
                elif field == 'threshold':
                    values.append(float(value))
                else:
                    values.append(value)

            values.append(rule_id)

            query = f"""
                UPDATE alert_rules
                SET {', '.join(set_clauses)}
                WHERE rule_id = ?
            """

            cursor.execute(query, values)
            conn.commit()

            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to update alert rule: {str(e)}")

        finally:
            conn.close()

    def delete_rule(self, rule_id: str) -> bool:
        """
        Delete an alert rule

        Args:
            rule_id: ID of the rule to delete

        Returns:
            bool: True if rule was deleted, False if rule not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        try:
            cursor.execute("DELETE FROM alert_rules WHERE rule_id = ?", (rule_id,))
            conn.commit()
            return cursor.rowcount > 0

        except Exception as e:
            conn.rollback()
            raise RuntimeError(f"Failed to delete alert rule: {str(e)}")

        finally:
            conn.close()

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
                rules.append({
                    'rule_id': row['rule_id'],
                    'rule_name': row['rule_name'],
                    'metric_path': row['metric_path'],
                    'condition': row['condition'],
                    'threshold': row['threshold'],
                    'severity': row['severity'],
                    'enabled': bool(row['enabled'])
                })

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
        return self.update_rule(rule_id, {'enabled': True})

    def disable_rule(self, rule_id: str) -> bool:
        """
        Disable an alert rule

        Args:
            rule_id: ID of the rule to disable

        Returns:
            bool: True if rule was disabled, False if rule not found
        """
        return self.update_rule(rule_id, {'enabled': False})
