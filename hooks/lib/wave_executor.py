"""Wave execution framework for project-intelligence platform."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any

from hooks.lib.studio_db import _connect


class WaveExecutor:
    """Execute waves of tasks in parallel groups with status tracking."""

    def __init__(self, wave_id: str) -> None:
        """Initialize wave executor.

        Args:
            wave_id: The wave_id to execute
        """
        self.wave_id = wave_id
        self.conn = _connect()

        # Load wave metadata
        wave_row = self.conn.execute(
            "SELECT * FROM pi_waves WHERE wave_id = ?",
            (wave_id,),
        ).fetchone()

        if not wave_row:
            self.conn.close()
            raise ValueError(f"Wave {wave_id} not found")

        self.wave = dict(wave_row)

        # Load tasks for this wave
        task_rows = self.conn.execute(
            "SELECT * FROM pi_wave_tasks WHERE wave_id = ? ORDER BY parallel_group, task_number",
            (wave_id,),
        ).fetchall()

        self.tasks = [dict(row) for row in task_rows]

    def execute_wave(self) -> dict[str, Any]:
        """Execute all tasks in the wave, grouped by parallel_group.

        Returns:
            dict: Wave execution summary with keys:
                - wave_id: str
                - status: str ('completed' or 'failed')
                - tasks_completed: int
                - tasks_failed: int
                - duration_seconds: float
        """
        # Update wave status to 'running'
        started_at = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE pi_waves SET status = 'running', started_at = ? WHERE wave_id = ?",
            (started_at, self.wave_id),
        )
        self.conn.commit()

        # Group tasks by parallel_group
        groups: dict[int, list[dict]] = {}
        for task in self.tasks:
            group_num = task["parallel_group"]
            if group_num not in groups:
                groups[group_num] = []
            groups[group_num].append(task)

        # Execute each group sequentially
        tasks_completed = 0
        tasks_failed = 0

        try:
            for group_num in sorted(groups.keys()):
                group_tasks = groups[group_num]

                # Spawn agents for all tasks in this group (placeholder for MVP)
                agent_ids = []
                for task in group_tasks:
                    agent_id = self._spawn_task_agent(task)
                    agent_ids.append(agent_id)

                # Wait for all agents in this group to complete
                results = self._wait_for_group(agent_ids)

                # Update task statuses based on results
                for result in results:
                    if result["status"] == "completed":
                        tasks_completed += 1
                    else:
                        tasks_failed += 1

            # Calculate final metrics
            completed_at = datetime.now(timezone.utc).isoformat()
            duration_seconds = (
                datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)
            ).total_seconds()

            success_rate = self._calculate_success_rate()

            # Determine final wave status
            final_status = "completed" if tasks_failed == 0 else "failed"

            # Update wave with final status
            self.conn.execute(
                """UPDATE pi_waves SET
                    status = ?,
                    completed_at = ?,
                    duration_seconds = ?,
                    tasks_completed = ?,
                    tasks_failed = ?,
                    success_rate = ?
                   WHERE wave_id = ?""",
                (
                    final_status,
                    completed_at,
                    duration_seconds,
                    tasks_completed,
                    tasks_failed,
                    success_rate,
                    self.wave_id,
                ),
            )
            self.conn.commit()

            return {
                "wave_id": self.wave_id,
                "status": final_status,
                "tasks_completed": tasks_completed,
                "tasks_failed": tasks_failed,
                "duration_seconds": duration_seconds,
            }

        except Exception:
            # Mark wave as failed on error
            completed_at = datetime.now(timezone.utc).isoformat()
            duration_seconds = (
                datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)
            ).total_seconds()

            self.conn.execute(
                """UPDATE pi_waves SET
                    status = 'failed',
                    completed_at = ?,
                    duration_seconds = ?,
                    tasks_completed = ?,
                    tasks_failed = ?
                   WHERE wave_id = ?""",
                (completed_at, duration_seconds, tasks_completed, tasks_failed, self.wave_id),
            )
            self.conn.commit()

            raise

        finally:
            self.conn.close()

    def _spawn_task_agent(self, task: dict) -> str:
        """Spawn a background agent for a single task (MVP placeholder).

        Args:
            task: Task dictionary with keys: wave_task_id, task_id, etc.

        Returns:
            str: Agent ID (mock for MVP)
        """
        # Update task status to 'running'
        started_at = datetime.now(timezone.utc).isoformat()
        self._update_task_status(
            task["wave_task_id"],
            "running",
            started_at=started_at,
        )

        # For MVP: return mock agent_id
        # In Wave 2, this will use Agent tool with run_in_background=True
        return f"agent_{task['wave_task_id']}"

    def _wait_for_group(self, agent_ids: list[str]) -> list[dict]:
        """Wait for all agents in a group to complete (MVP placeholder).

        Args:
            agent_ids: List of agent IDs to wait for

        Returns:
            list: List of result dicts with keys: task_id, status, duration
        """
        # For MVP: simulate immediate completion
        # In Wave 2, this will poll task statuses until all complete or timeout (10 minutes)

        results = []
        for agent_id in agent_ids:
            # Extract wave_task_id from agent_id (format: "agent_{wave_task_id}")
            wave_task_id = agent_id.replace("agent_", "")

            # Mark task as completed (for MVP, all tasks succeed)
            completed_at = datetime.now(timezone.utc).isoformat()
            self._update_task_status(
                wave_task_id,
                "completed",
                completed_at=completed_at,
            )

            # Get task info for duration calculation
            task_row = self.conn.execute(
                "SELECT started_at, completed_at FROM pi_wave_tasks WHERE wave_task_id = ?",
                (wave_task_id,),
            ).fetchone()

            if task_row:
                task = dict(task_row)
                duration = 0.0
                if task["started_at"] and task["completed_at"]:
                    duration = (
                        datetime.fromisoformat(task["completed_at"])
                        - datetime.fromisoformat(task["started_at"])
                    ).total_seconds()

                results.append({
                    "task_id": wave_task_id,
                    "status": "completed",
                    "duration": duration,
                })

        return results

    def _update_task_status(
        self,
        wave_task_id: str,
        status: str,
        started_at: str | None = None,
        completed_at: str | None = None,
    ) -> None:
        """Update task status in pi_wave_tasks table.

        Args:
            wave_task_id: Task ID to update
            status: New status ('pending', 'running', 'completed', 'failed')
            started_at: Optional start timestamp
            completed_at: Optional completion timestamp
        """
        # Build update query
        fields = ["status = ?"]
        params: list[Any] = [status]

        if started_at is not None:
            fields.append("started_at = ?")
            params.append(started_at)

        if completed_at is not None:
            fields.append("completed_at = ?")
            params.append(completed_at)

            # Calculate actual_hours if we have both started_at and completed_at
            task_row = self.conn.execute(
                "SELECT started_at, estimated_hours FROM pi_wave_tasks WHERE wave_task_id = ?",
                (wave_task_id,),
            ).fetchone()

            if task_row:
                task = dict(task_row)
                if task["started_at"]:
                    duration_seconds = (
                        datetime.fromisoformat(completed_at)
                        - datetime.fromisoformat(task["started_at"])
                    ).total_seconds()
                    actual_hours = duration_seconds / 3600.0
                    fields.append("actual_hours = ?")
                    params.append(actual_hours)

        params.append(wave_task_id)
        query = f"UPDATE pi_wave_tasks SET {', '.join(fields)} WHERE wave_task_id = ?"

        self.conn.execute(query, params)
        self.conn.commit()

    def _calculate_success_rate(self) -> float:
        """Calculate wave success rate from task completion stats.

        Returns:
            float: Success rate (0.0 to 1.0)
        """
        result = self.conn.execute(
            """SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed
               FROM pi_wave_tasks
               WHERE wave_id = ?""",
            (self.wave_id,),
        ).fetchone()

        if not result or result["total"] == 0:
            return 0.0

        return float(result["completed"]) / float(result["total"])
