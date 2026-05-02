"""Schedule persistence module for report scheduler

Manages SQLite storage of scheduled report configurations with full CRUD operations.

Example:
    >>> from analytics.core.scheduler.storage import ScheduleStorage
    >>> storage = ScheduleStorage("~/.dream-studio/schedules.db")
    >>> job_id = storage.save_schedule({
    ...     "name": "Weekly Report",
    ...     "report_type": "summary",
    ...     "schedule": "0 9 * * MON",
    ...     "recipients": ["user@example.com"],
    ...     "format": "pdf"
    ... })
    >>> schedules = storage.load_schedules()
"""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional


class ScheduleStorage:
    """SQLite-based storage for scheduled report configurations"""

    def __init__(self, db_path: str):
        """
        Initialize schedule storage

        Args:
            db_path: Path to SQLite database file (will be created if doesn't exist)
        """
        # Expand home directory if present
        self.db_path = Path(db_path).expanduser()

        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()

    def _init_database(self) -> None:
        """Create database schema if it doesn't exist"""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scheduled_reports (
                    job_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    report_type TEXT NOT NULL,
                    schedule TEXT NOT NULL,
                    recipients TEXT NOT NULL,
                    format TEXT DEFAULT 'pdf',
                    config TEXT,
                    enabled BOOLEAN DEFAULT 1,
                    timezone TEXT DEFAULT 'UTC',
                    created_at TEXT NOT NULL,
                    last_run TEXT,
                    next_run TEXT
                )
            """)
            conn.commit()

    def save_schedule(self, schedule: Dict[str, Any]) -> str:
        """
        Save or update a schedule

        Args:
            schedule: Schedule configuration with keys:
                - job_id: str (optional, will be generated if not provided)
                - name: str (required)
                - report_type: str (required)
                - schedule: str (required, cron expression)
                - recipients: list[str] (required)
                - format: str (default: "pdf")
                - config: dict (optional, additional report config)
                - enabled: bool (default: True)
                - timezone: str (default: "UTC")
                - next_run: str (optional, ISO timestamp)

        Returns:
            str: job_id of saved schedule

        Raises:
            ValueError: If required fields are missing
        """
        # Validate required fields
        required_fields = ["name", "report_type", "schedule", "recipients"]
        for field in required_fields:
            if field not in schedule:
                raise ValueError(f"Missing required field: {field}")

        # Generate job_id if not provided
        job_id = schedule.get("job_id", str(uuid.uuid4()))

        # Serialize recipients and config
        recipients_json = json.dumps(schedule["recipients"])
        config_json = json.dumps(schedule.get("config", {}))

        # Extract fields with defaults
        name = schedule["name"]
        report_type = schedule["report_type"]
        schedule_expr = schedule["schedule"]
        format_type = schedule.get("format", "pdf")
        enabled = 1 if schedule.get("enabled", True) else 0
        timezone = schedule.get("timezone", "UTC")
        next_run = schedule.get("next_run")

        # Timestamps
        created_at = datetime.now().isoformat()

        with sqlite3.connect(str(self.db_path)) as conn:
            # Check if job exists
            existing = conn.execute(
                "SELECT job_id FROM scheduled_reports WHERE job_id = ?",
                (job_id,)
            ).fetchone()

            if existing:
                # Update existing
                conn.execute("""
                    UPDATE scheduled_reports
                    SET name = ?, report_type = ?, schedule = ?, recipients = ?,
                        format = ?, config = ?, enabled = ?, timezone = ?, next_run = ?
                    WHERE job_id = ?
                """, (
                    name, report_type, schedule_expr, recipients_json,
                    format_type, config_json, enabled, timezone, next_run, job_id
                ))
            else:
                # Insert new
                conn.execute("""
                    INSERT INTO scheduled_reports (
                        job_id, name, report_type, schedule, recipients,
                        format, config, enabled, timezone, created_at, next_run
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id, name, report_type, schedule_expr, recipients_json,
                    format_type, config_json, enabled, timezone, created_at, next_run
                ))

            conn.commit()

        return job_id

    def load_schedules(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        """
        Load all schedules from database

        Args:
            enabled_only: If True, only return enabled schedules

        Returns:
            List of schedule dictionaries
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row

            if enabled_only:
                cursor = conn.execute(
                    "SELECT * FROM scheduled_reports WHERE enabled = 1"
                )
            else:
                cursor = conn.execute("SELECT * FROM scheduled_reports")

            schedules = []
            for row in cursor.fetchall():
                schedule = dict(row)

                # Deserialize JSON fields
                schedule["recipients"] = json.loads(schedule["recipients"])
                schedule["config"] = json.loads(schedule["config"] or "{}")
                schedule["enabled"] = bool(schedule["enabled"])

                schedules.append(schedule)

        return schedules

    def get_schedule(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single schedule by job_id

        Args:
            job_id: Job identifier

        Returns:
            Schedule dict or None if not found
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row

            cursor = conn.execute(
                "SELECT * FROM scheduled_reports WHERE job_id = ?",
                (job_id,)
            )

            row = cursor.fetchone()
            if not row:
                return None

            schedule = dict(row)

            # Deserialize JSON fields
            schedule["recipients"] = json.loads(schedule["recipients"])
            schedule["config"] = json.loads(schedule["config"] or "{}")
            schedule["enabled"] = bool(schedule["enabled"])

            return schedule

    def delete_schedule(self, job_id: str) -> bool:
        """
        Delete a schedule from database

        Args:
            job_id: Job identifier

        Returns:
            True if deleted, False if not found
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "DELETE FROM scheduled_reports WHERE job_id = ?",
                (job_id,)
            )
            conn.commit()

            return cursor.rowcount > 0

    def update_last_run(self, job_id: str, timestamp: datetime, next_run: Optional[str] = None) -> None:
        """
        Update the last_run and optionally next_run timestamps

        Args:
            job_id: Job identifier
            timestamp: Last run datetime
            next_run: Optional next run ISO timestamp
        """
        last_run_iso = timestamp.isoformat()

        with sqlite3.connect(str(self.db_path)) as conn:
            if next_run:
                conn.execute("""
                    UPDATE scheduled_reports
                    SET last_run = ?, next_run = ?
                    WHERE job_id = ?
                """, (last_run_iso, next_run, job_id))
            else:
                conn.execute("""
                    UPDATE scheduled_reports
                    SET last_run = ?
                    WHERE job_id = ?
                """, (last_run_iso, job_id))

            conn.commit()

    def set_enabled(self, job_id: str, enabled: bool) -> bool:
        """
        Enable or disable a schedule

        Args:
            job_id: Job identifier
            enabled: True to enable, False to disable

        Returns:
            True if updated, False if job not found
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute(
                "UPDATE scheduled_reports SET enabled = ? WHERE job_id = ?",
                (1 if enabled else 0, job_id)
            )
            conn.commit()

            return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about stored schedules

        Returns:
            Dict with total, enabled, disabled counts
        """
        with sqlite3.connect(str(self.db_path)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM scheduled_reports").fetchone()[0]
            enabled = conn.execute("SELECT COUNT(*) FROM scheduled_reports WHERE enabled = 1").fetchone()[0]

            # Get schedules by format
            by_format = {}
            cursor = conn.execute("SELECT format, COUNT(*) as count FROM scheduled_reports GROUP BY format")
            for row in cursor.fetchall():
                by_format[row[0]] = row[1]

            # Get schedules by report type
            by_type = {}
            cursor = conn.execute("SELECT report_type, COUNT(*) as count FROM scheduled_reports GROUP BY report_type")
            for row in cursor.fetchall():
                by_type[row[0]] = row[1]

        return {
            "total": total,
            "enabled": enabled,
            "disabled": total - enabled,
            "by_format": by_format,
            "by_report_type": by_type
        }
