"""Workflow metrics projection consumer.

Consumes workflow events and projects them into aggregated KPI metrics:
  - Workflow success rate by type
  - Average workflow duration by type
  - Phase breakdown statistics
  - Failure analysis by phase

Created: 2026-05-08
"""

from typing import Any

from core.config.database import get_connection, transaction


class WorkflowMetricsProjection:
    """Projection consumer for workflow KPI metrics."""

    def __init__(self):
        """Initialize projection consumer and ensure tables exist."""
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure workflow metrics projection tables exist."""
        with transaction() as conn:
            # Workflow execution summary (one row per workflow)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_executions (
                    workflow_id TEXT PRIMARY KEY,
                    workflow_type TEXT NOT NULL,
                    triggered_by TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    duration_seconds REAL,
                    status TEXT NOT NULL,
                    phases_completed INTEGER DEFAULT 0,
                    tasks_completed INTEGER DEFAULT 0,
                    error_message TEXT,
                    phase_failed TEXT,
                    outcome_json TEXT,
                    CONSTRAINT chk_status CHECK (status IN ('running', 'completed', 'failed', 'cancelled'))
                )
            """)

            # Workflow phase tracking (many rows per workflow)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_phases (
                    phase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    workflow_id TEXT NOT NULL,
                    phase_name TEXT NOT NULL,
                    phase_duration_seconds REAL NOT NULL,
                    tasks_in_phase INTEGER NOT NULL,
                    outcome_json TEXT,
                    completed_at TEXT NOT NULL,
                    FOREIGN KEY (workflow_id) REFERENCES workflow_executions(workflow_id)
                )
            """)

            # Aggregated workflow KPIs (materialized view, updated on workflow completion)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_kpis (
                    workflow_type TEXT PRIMARY KEY,
                    total_executions INTEGER DEFAULT 0,
                    successful_executions INTEGER DEFAULT 0,
                    failed_executions INTEGER DEFAULT 0,
                    success_rate REAL DEFAULT 0.0,
                    avg_duration_seconds REAL DEFAULT 0.0,
                    avg_phases_per_workflow REAL DEFAULT 0.0,
                    avg_tasks_per_workflow REAL DEFAULT 0.0,
                    last_execution_at TEXT,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Phase performance metrics (aggregated by phase name)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS phase_kpis (
                    phase_name TEXT PRIMARY KEY,
                    total_executions INTEGER DEFAULT 0,
                    avg_duration_seconds REAL DEFAULT 0.0,
                    avg_tasks_per_phase REAL DEFAULT 0.0,
                    failure_count INTEGER DEFAULT 0,
                    last_execution_at TEXT,
                    last_updated TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_type ON workflow_executions(workflow_type)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_workflow_status ON workflow_executions(status)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_phase_workflow ON workflow_phases(workflow_id)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_phase_name ON workflow_phases(phase_name)")

    def consume_workflow_started(self, event: dict[str, Any]):
        """Consume workflow.started event.

        Args:
            event: Canonical event dict with payload containing:
                - workflow_id, workflow_type, triggered_by, started_at, context
        """
        payload = event["payload"]

        with transaction() as conn:
            conn.execute(
                """INSERT INTO workflow_executions
                   (workflow_id, workflow_type, triggered_by, started_at, status)
                   VALUES (?, ?, ?, ?, 'running')""",
                (
                    payload["workflow_id"],
                    payload["workflow_type"],
                    payload["triggered_by"],
                    payload["started_at"],
                ),
            )

    def consume_workflow_completed(self, event: dict[str, Any]):
        """Consume workflow.completed event.

        Args:
            event: Canonical event dict with payload containing:
                - workflow_id, workflow_type, duration_seconds, phases_completed,
                  tasks_completed, outcome, completed_at
        """
        payload = event["payload"]

        with transaction() as conn:
            # Update workflow execution record
            conn.execute(
                """UPDATE workflow_executions
                   SET status = 'completed',
                       completed_at = ?,
                       duration_seconds = ?,
                       phases_completed = ?,
                       tasks_completed = ?,
                       outcome_json = ?
                   WHERE workflow_id = ?""",
                (
                    payload["completed_at"],
                    payload["duration_seconds"],
                    payload["phases_completed"],
                    payload["tasks_completed"],
                    str(payload.get("outcome", {})),
                    payload["workflow_id"],
                ),
            )

            # Update KPIs for this workflow type
            self._update_workflow_kpis(payload["workflow_type"], conn)

    def consume_workflow_failed(self, event: dict[str, Any]):
        """Consume workflow.failed event.

        Args:
            event: Canonical event dict with payload containing:
                - workflow_id, workflow_type, duration_seconds, error_message,
                  phase_failed, tasks_completed, failed_at
        """
        payload = event["payload"]

        with transaction() as conn:
            # Update workflow execution record
            conn.execute(
                """UPDATE workflow_executions
                   SET status = 'failed',
                       completed_at = ?,
                       duration_seconds = ?,
                       tasks_completed = ?,
                       error_message = ?,
                       phase_failed = ?
                   WHERE workflow_id = ?""",
                (
                    payload["failed_at"],
                    payload["duration_seconds"],
                    payload.get("tasks_completed", 0),
                    payload["error_message"],
                    payload.get("phase_failed"),
                    payload["workflow_id"],
                ),
            )

            # Update KPIs for this workflow type
            self._update_workflow_kpis(payload["workflow_type"], conn)

            # Update phase failure stats if phase_failed is specified
            if payload.get("phase_failed"):
                self._update_phase_failure(payload["phase_failed"], conn)

    def consume_workflow_phase_completed(self, event: dict[str, Any]):
        """Consume workflow.phase_completed event.

        Args:
            event: Canonical event dict with payload containing:
                - workflow_id, phase_name, phase_duration_seconds,
                  tasks_in_phase, outcome, completed_at
        """
        payload = event["payload"]

        with transaction() as conn:
            # Insert phase record
            conn.execute(
                """INSERT INTO workflow_phases
                   (workflow_id, phase_name, phase_duration_seconds, tasks_in_phase,
                    outcome_json, completed_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    payload["workflow_id"],
                    payload["phase_name"],
                    payload["phase_duration_seconds"],
                    payload["tasks_in_phase"],
                    str(payload.get("outcome", {})),
                    payload["completed_at"],
                ),
            )

            # Update phase KPIs
            self._update_phase_kpis(payload["phase_name"], conn)

    def _update_workflow_kpis(self, workflow_type: str, conn):
        """Recalculate and update workflow KPIs for a given type.

        Args:
            workflow_type: Workflow type to update KPIs for
            conn: Database connection (within transaction)
        """
        # Get aggregated stats from workflow_executions
        stats = conn.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as successful,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                AVG(CASE WHEN status IN ('completed', 'failed') THEN duration_seconds END) as avg_duration,
                AVG(phases_completed) as avg_phases,
                AVG(tasks_completed) as avg_tasks,
                MAX(completed_at) as last_execution
               FROM workflow_executions
               WHERE workflow_type = ?""",
            (workflow_type,),
        ).fetchone()

        if not stats or stats["total"] == 0:
            return

        success_rate = (
            float(stats["successful"]) / float(stats["total"]) if stats["total"] > 0 else 0.0
        )

        # Upsert KPI record
        conn.execute(
            """INSERT INTO workflow_kpis
               (workflow_type, total_executions, successful_executions, failed_executions,
                success_rate, avg_duration_seconds, avg_phases_per_workflow,
                avg_tasks_per_workflow, last_execution_at, last_updated)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(workflow_type) DO UPDATE SET
                   total_executions = excluded.total_executions,
                   successful_executions = excluded.successful_executions,
                   failed_executions = excluded.failed_executions,
                   success_rate = excluded.success_rate,
                   avg_duration_seconds = excluded.avg_duration_seconds,
                   avg_phases_per_workflow = excluded.avg_phases_per_workflow,
                   avg_tasks_per_workflow = excluded.avg_tasks_per_workflow,
                   last_execution_at = excluded.last_execution_at,
                   last_updated = CURRENT_TIMESTAMP""",
            (
                workflow_type,
                stats["total"],
                stats["successful"] or 0,
                stats["failed"] or 0,
                success_rate,
                stats["avg_duration"] or 0.0,
                stats["avg_phases"] or 0.0,
                stats["avg_tasks"] or 0.0,
                stats["last_execution"],
            ),
        )

    def _update_phase_kpis(self, phase_name: str, conn):
        """Recalculate and update phase KPIs for a given phase name.

        Args:
            phase_name: Phase name to update KPIs for
            conn: Database connection (within transaction)
        """
        # Get aggregated stats from workflow_phases
        stats = conn.execute(
            """SELECT
                COUNT(*) as total,
                AVG(phase_duration_seconds) as avg_duration,
                AVG(tasks_in_phase) as avg_tasks,
                MAX(completed_at) as last_execution
               FROM workflow_phases
               WHERE phase_name = ?""",
            (phase_name,),
        ).fetchone()

        if not stats or stats["total"] == 0:
            return

        # Upsert phase KPI record
        conn.execute(
            """INSERT INTO phase_kpis
               (phase_name, total_executions, avg_duration_seconds, avg_tasks_per_phase,
                last_execution_at, last_updated)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(phase_name) DO UPDATE SET
                   total_executions = excluded.total_executions,
                   avg_duration_seconds = excluded.avg_duration_seconds,
                   avg_tasks_per_phase = excluded.avg_tasks_per_phase,
                   last_execution_at = excluded.last_execution_at,
                   last_updated = CURRENT_TIMESTAMP""",
            (
                phase_name,
                stats["total"],
                stats["avg_duration"] or 0.0,
                stats["avg_tasks"] or 0.0,
                stats["last_execution"],
            ),
        )

    def _update_phase_failure(self, phase_name: str, conn):
        """Increment failure count for a phase.

        Args:
            phase_name: Phase name that failed
            conn: Database connection (within transaction)
        """
        conn.execute(
            """UPDATE phase_kpis
               SET failure_count = failure_count + 1,
                   last_updated = CURRENT_TIMESTAMP
               WHERE phase_name = ?""",
            (phase_name,),
        )

    def get_workflow_kpis(self, workflow_type: str | None = None) -> list[dict[str, Any]]:
        """Query workflow KPIs.

        Args:
            workflow_type: Optional filter by workflow type

        Returns:
            List of KPI dicts
        """
        with get_connection(read_only=True) as conn:
            if workflow_type:
                cursor = conn.execute(
                    "SELECT * FROM workflow_kpis WHERE workflow_type = ?", (workflow_type,)
                )
            else:
                cursor = conn.execute("SELECT * FROM workflow_kpis ORDER BY total_executions DESC")

            return [dict(row) for row in cursor.fetchall()]

    def get_phase_kpis(self, phase_name: str | None = None) -> list[dict[str, Any]]:
        """Query phase KPIs.

        Args:
            phase_name: Optional filter by phase name

        Returns:
            List of phase KPI dicts
        """
        with get_connection(read_only=True) as conn:
            if phase_name:
                cursor = conn.execute(
                    "SELECT * FROM phase_kpis WHERE phase_name = ?", (phase_name,)
                )
            else:
                cursor = conn.execute("SELECT * FROM phase_kpis ORDER BY total_executions DESC")

            return [dict(row) for row in cursor.fetchall()]

    def get_recent_workflows(
        self, workflow_type: str | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Get recent workflow executions.

        Args:
            workflow_type: Optional filter by workflow type
            limit: Max number of records to return

        Returns:
            List of workflow execution dicts
        """
        with get_connection(read_only=True) as conn:
            if workflow_type:
                cursor = conn.execute(
                    """SELECT * FROM workflow_executions
                       WHERE workflow_type = ?
                       ORDER BY started_at DESC
                       LIMIT ?""",
                    (workflow_type, limit),
                )
            else:
                cursor = conn.execute(
                    """SELECT * FROM workflow_executions
                       ORDER BY started_at DESC
                       LIMIT ?""",
                    (limit,),
                )

            return [dict(row) for row in cursor.fetchall()]
