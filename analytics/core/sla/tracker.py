"""SLATracker - Track and monitor SLA compliance for dream-studio metrics"""
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SLATracker:
    """
    Tracks Service Level Agreement (SLA) compliance for analytics metrics.

    Supports four SLA types:
    - Response time: Average response time below threshold (lower is better)
    - Error rate: Error percentage below threshold (lower is better)
    - Success rate: Success percentage above threshold (higher is better)
    - Availability: Uptime percentage above threshold (higher is better)

    SLA definitions are stored in the database and evaluated against
    historical metric data from the metric streamer.
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize SLATracker and create SLA table if needed.

        Args:
            db_path: Path to studio.db. If None, uses default ~/.dream-studio/state/studio.db
        """
        if db_path is None:
            self.db_path = str(Path.home() / ".dream-studio" / "state" / "studio.db")
        else:
            self.db_path = db_path

        # Create SLA table on initialization
        self._create_sla_table()
        logger.info(f"SLATracker initialized with database: {self.db_path}")

    def _create_sla_table(self) -> None:
        """
        Create sla_definitions table if it doesn't exist.

        Schema:
            - sla_id: Unique identifier (TEXT PRIMARY KEY)
            - name: Human-readable SLA name
            - metric: Metric to track (e.g., 'sessions_avg_duration', 'skills_success_rate')
            - target: Target value (float)
            - window: Time window in hours for evaluation (int)
            - sla_type: Type of SLA ('response_time', 'error_rate', 'availability')
            - created_at: When SLA was defined
            - updated_at: Last update timestamp
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sla_definitions (
                    sla_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    metric TEXT NOT NULL,
                    target REAL NOT NULL,
                    window INTEGER NOT NULL,
                    sla_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            # Create index on metric for faster lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sla_metric
                ON sla_definitions(metric)
            """)

            conn.commit()
            conn.close()
            logger.debug("SLA table created/verified")

        except sqlite3.Error as e:
            logger.error(f"Error creating SLA table: {e}", exc_info=True)
            raise

    def define_sla(
        self,
        name: str,
        metric: str,
        target: float,
        window: int,
        sla_type: Optional[str] = None
    ) -> str:
        """
        Define a new SLA or update existing one.

        Args:
            name: Human-readable SLA name
            metric: Metric to track (must match metric_streamer output keys)
            target: Target value (interpretation depends on sla_type)
            window: Time window in hours for evaluation
            sla_type: Type of SLA. If None, auto-infer from metric name.
                     Options: 'response_time', 'error_rate', 'availability'

        Returns:
            sla_id: Unique identifier for this SLA

        Raises:
            ValueError: If sla_type is invalid or cannot be inferred
            sqlite3.Error: On database errors
        """
        # Auto-infer SLA type if not provided
        if sla_type is None:
            sla_type = self._infer_sla_type(metric)

        # Validate SLA type
        valid_types = ['response_time', 'error_rate', 'success_rate', 'availability']
        if sla_type not in valid_types:
            raise ValueError(
                f"Invalid sla_type '{sla_type}'. Must be one of: {valid_types}"
            )

        # Generate SLA ID from name (lowercase, replace spaces with underscores)
        sla_id = name.lower().replace(" ", "_").replace("-", "_")

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            now = datetime.now(timezone.utc).isoformat()

            # Upsert SLA definition
            cursor.execute("""
                INSERT INTO sla_definitions
                (sla_id, name, metric, target, window, sla_type, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(sla_id) DO UPDATE SET
                    name = excluded.name,
                    metric = excluded.metric,
                    target = excluded.target,
                    window = excluded.window,
                    sla_type = excluded.sla_type,
                    updated_at = excluded.updated_at
            """, (sla_id, name, metric, target, window, sla_type, now, now))

            conn.commit()
            conn.close()

            logger.info(
                f"SLA defined: {sla_id} ({sla_type}) - {metric} target {target} "
                f"over {window}h window"
            )

            return sla_id

        except sqlite3.Error as e:
            logger.error(f"Error defining SLA: {e}", exc_info=True)
            raise

    def _infer_sla_type(self, metric: str) -> str:
        """
        Infer SLA type from metric name.

        Args:
            metric: Metric name (e.g., 'sessions_avg_duration')

        Returns:
            Inferred SLA type

        Raises:
            ValueError: If type cannot be inferred
        """
        metric_lower = metric.lower()

        # Check most specific patterns first to avoid false matches

        # Availability indicators (check before "time" to avoid uptime->response_time)
        if any(keyword in metric_lower for keyword in
               ['availability', 'uptime', 'downtime']):
            return 'availability'

        # Success rate indicators (higher is better)
        if any(keyword in metric_lower for keyword in
               ['success_rate', 'success', 'completion']):
            return 'success_rate'

        # Error/failure indicators (lower is better)
        if any(keyword in metric_lower for keyword in
               ['error', 'failure', 'failed']):
            return 'error_rate'

        # Response time indicators (check last to avoid false positives)
        if any(keyword in metric_lower for keyword in
               ['duration', 'time', 'latency', 'response']):
            return 'response_time'

        raise ValueError(
            f"Cannot infer SLA type from metric '{metric}'. "
            f"Please specify sla_type explicitly."
        )

    def check_compliance(self) -> Dict[str, Any]:
        """
        Check compliance status for all defined SLAs.

        Evaluates each SLA against recent metric history and determines
        if targets are being met. Uses the metric streamer's output format.

        Returns:
            Dict with structure:
                {
                    "timestamp": ISO timestamp of check,
                    "slas": {
                        "<sla_id>": {
                            "name": str,
                            "metric": str,
                            "target": float,
                            "current_value": float,
                            "compliant": bool,
                            "window_hours": int,
                            "sla_type": str,
                            "breach_percentage": float  # How far from target
                        },
                        ...
                    },
                    "summary": {
                        "total_slas": int,
                        "compliant_count": int,
                        "breached_count": int,
                        "compliance_percentage": float
                    }
                }

        Raises:
            sqlite3.Error: On database errors
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Get all SLA definitions
            cursor.execute("SELECT * FROM sla_definitions")
            slas = cursor.fetchall()

            results = {}
            compliant_count = 0

            for sla in slas:
                sla_id = sla["sla_id"]
                metric = sla["metric"]
                target = sla["target"]
                window = sla["window"]
                sla_type = sla["sla_type"]

                # Calculate current value from metric history
                current_value = self._calculate_metric_value(
                    cursor, metric, window, sla_type
                )

                # Determine compliance
                compliant = self._is_compliant(current_value, target, sla_type)

                # Calculate breach percentage
                breach_pct = self._calculate_breach_percentage(
                    current_value, target, sla_type
                )

                if compliant:
                    compliant_count += 1

                results[sla_id] = {
                    "name": sla["name"],
                    "metric": metric,
                    "target": target,
                    "current_value": current_value,
                    "compliant": compliant,
                    "window_hours": window,
                    "sla_type": sla_type,
                    "breach_percentage": breach_pct
                }

            conn.close()

            total = len(slas)
            compliance_pct = (compliant_count / total * 100) if total > 0 else 0.0

            return {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "slas": results,
                "summary": {
                    "total_slas": total,
                    "compliant_count": compliant_count,
                    "breached_count": total - compliant_count,
                    "compliance_percentage": round(compliance_pct, 2)
                }
            }

        except sqlite3.Error as e:
            logger.error(f"Error checking SLA compliance: {e}", exc_info=True)
            raise

    def _calculate_metric_value(
        self,
        cursor: sqlite3.Cursor,
        metric: str,
        window_hours: int,
        sla_type: str
    ) -> float:
        """
        Calculate current metric value from historical data.

        This is a simplified implementation that queries the raw data tables.
        In production, you'd want to query a metrics history table populated
        by the metric streamer.

        Args:
            cursor: Database cursor
            metric: Metric name
            window_hours: Time window in hours
            sla_type: Type of SLA

        Returns:
            Current metric value (averaged over window)
        """
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        cutoff_str = cutoff.strftime("%Y-%m-%d %H:%M:%S")

        # Map metric names to queries
        # This is simplified - in production, query from a metrics_history table

        try:
            if metric == "sessions_avg_duration":
                # Average session duration in minutes
                cursor.execute("""
                    SELECT AVG(
                        (julianday(ended_at) - julianday(started_at)) * 24 * 60
                    ) as avg_duration
                    FROM raw_sessions
                    WHERE started_at >= ?
                    AND ended_at IS NOT NULL
                    AND ended_at > started_at
                """, (cutoff_str,))
                result = cursor.fetchone()
                return result["avg_duration"] if result["avg_duration"] else 0.0

            elif metric == "skills_success_rate":
                # Success rate as percentage
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(success) as successes
                    FROM raw_skill_telemetry
                    WHERE invoked_at >= ?
                """, (cutoff_str,))
                result = cursor.fetchone()
                total = result["total"]
                if total == 0:
                    return 100.0  # No data = assume compliant
                return (result["successes"] / total * 100.0)

            elif metric == "workflows_success_rate":
                # Workflow success rate as percentage
                cursor.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successes
                    FROM raw_workflow_runs
                    WHERE started_at >= ?
                """, (cutoff_str,))
                result = cursor.fetchone()
                total = result["total"]
                if total == 0:
                    return 100.0
                return (result["successes"] / total * 100.0)

            else:
                # Unknown metric - return 0 and log warning
                logger.warning(
                    f"Unknown metric '{metric}' - cannot calculate value. Returning 0."
                )
                return 0.0

        except sqlite3.OperationalError as e:
            # Handle missing tables gracefully (e.g., in test environments)
            logger.warning(
                f"Database error calculating metric '{metric}': {e}. "
                f"Returning default value 0.0"
            )
            return 0.0

    def _is_compliant(
        self,
        current_value: float,
        target: float,
        sla_type: str
    ) -> bool:
        """
        Determine if current value meets SLA target.

        For response_time and error_rate: current_value should be <= target (lower is better)
        For availability and success_rate: current_value should be >= target (higher is better)

        Args:
            current_value: Current metric value
            target: Target value
            sla_type: Type of SLA

        Returns:
            True if compliant, False if breached
        """
        if sla_type in ["response_time", "error_rate"]:
            # Target is maximum - lower is better
            return current_value <= target

        elif sla_type in ["availability", "success_rate"]:
            # Target is minimum - higher is better
            return current_value >= target

        else:
            logger.warning(f"Unknown SLA type '{sla_type}' - assuming non-compliant")
            return False

    def _calculate_breach_percentage(
        self,
        current_value: float,
        target: float,
        sla_type: str
    ) -> float:
        """
        Calculate how far the current value is from target (as percentage).

        Positive values indicate breach, negative values indicate margin.

        Args:
            current_value: Current metric value
            target: Target value
            sla_type: Type of SLA

        Returns:
            Breach percentage (positive = breach, negative = margin)
        """
        if target == 0:
            return 0.0

        if sla_type in ["response_time", "error_rate"]:
            # Lower is better - calculate how much over target
            return ((current_value - target) / target) * 100.0

        elif sla_type in ["availability", "success_rate"]:
            # Higher is better - calculate how much under target
            return ((target - current_value) / target) * 100.0

        else:
            return 0.0

    def get_sla_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive SLA report with historical trends.

        Returns:
            Dict with structure:
                {
                    "generated_at": ISO timestamp,
                    "slas": [
                        {
                            "sla_id": str,
                            "name": str,
                            "metric": str,
                            "target": float,
                            "current_value": float,
                            "compliant": bool,
                            "sla_type": str,
                            "window_hours": int,
                            "breach_percentage": float,
                            "created_at": ISO timestamp,
                            "updated_at": ISO timestamp
                        },
                        ...
                    ],
                    "summary": {
                        "total_slas": int,
                        "compliant_count": int,
                        "breached_count": int,
                        "compliance_percentage": float,
                        "critical_breaches": [
                            {
                                "sla_id": str,
                                "name": str,
                                "breach_percentage": float
                            },
                            ...
                        ]
                    }
                }

        Raises:
            sqlite3.Error: On database errors
        """
        try:
            # Get compliance status
            compliance = self.check_compliance()

            # Get full SLA details from database
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT * FROM sla_definitions ORDER BY name")
            sla_rows = cursor.fetchall()

            conn.close()

            # Build detailed SLA list
            slas = []
            for row in sla_rows:
                sla_id = row["sla_id"]
                compliance_data = compliance["slas"].get(sla_id, {})

                slas.append({
                    "sla_id": sla_id,
                    "name": row["name"],
                    "metric": row["metric"],
                    "target": row["target"],
                    "current_value": compliance_data.get("current_value", 0.0),
                    "compliant": compliance_data.get("compliant", False),
                    "sla_type": row["sla_type"],
                    "window_hours": row["window"],
                    "breach_percentage": compliance_data.get("breach_percentage", 0.0),
                    "created_at": row["created_at"],
                    "updated_at": row["updated_at"]
                })

            # Identify critical breaches (>20% over target)
            critical_breaches = [
                {
                    "sla_id": sla["sla_id"],
                    "name": sla["name"],
                    "breach_percentage": sla["breach_percentage"]
                }
                for sla in slas
                if not sla["compliant"] and sla["breach_percentage"] > 20.0
            ]

            # Sort critical breaches by severity
            critical_breaches.sort(key=lambda x: x["breach_percentage"], reverse=True)

            return {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "slas": slas,
                "summary": {
                    **compliance["summary"],
                    "critical_breaches": critical_breaches
                }
            }

        except sqlite3.Error as e:
            logger.error(f"Error generating SLA report: {e}", exc_info=True)
            raise
