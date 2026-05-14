"""Enhanced Wave execution framework integrated with execution graph.

This is the Phase 5 enhanced version that:
- Creates execution graph nodes for waves and tasks
- Links events to graph nodes
- Provides compiled context to tasks (70-85% token savings)
- Tracks outputs in execution graph

Created: 2026-05-07 (Phase 5 integration)
"""

from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional
import logging

from core.config.database import transaction, get_connection
from core.events.emitter import emit_event
from core.events.types import EventType
from core.execution.workflow_integration import WorkflowGraphIntegration

logger = logging.getLogger(__name__)


class WaveExecutorEnhanced:
    """Execute waves of tasks with execution graph integration."""

    def __init__(self, wave_id: str, project_node_id: Optional[str] = None) -> None:
        """Initialize wave executor.

        Args:
            wave_id: The wave_id to execute
            project_node_id: Optional project node in execution graph
        """
        self.wave_id = wave_id
        self.project_node_id = project_node_id

        # Initialize execution graph integration
        self.integration = WorkflowGraphIntegration()

        # Load wave metadata
        with get_connection() as conn:
            wave_row = conn.execute(
                "SELECT * FROM pi_waves WHERE wave_id = ?",
                (wave_id,),
            ).fetchone()

            if not wave_row:
                raise ValueError(f"Wave {wave_id} not found")

            self.wave = dict(wave_row)

            # Load tasks for this wave
            task_rows = conn.execute(
                "SELECT * FROM pi_wave_tasks WHERE wave_id = ? ORDER BY parallel_group, task_number",
                (wave_id,),
            ).fetchall()

            self.tasks = [dict(row) for row in task_rows]

        # Create wave node in execution graph
        self.wave_node_id = self._create_wave_node()

    def _create_wave_node(self) -> str:
        """Create wave node in execution graph."""
        if not self.project_node_id:
            # Auto-create project node if not provided
            self.project_node_id = self.integration.create_project_node(
                project_title=f"Project for wave {self.wave_id}", metadata={"auto_created": True}
            )
            logger.info(f"Auto-created project node: {self.project_node_id}")

        wave_node_id = self.integration.create_wave_node(
            wave_id=self.wave_id,
            wave_title=self.wave.get("description", f"Wave {self.wave_id}"),
            project_node_id=self.project_node_id,
            metadata={
                "analysis_run_id": self.wave.get("analysis_run_id"),
                "parallel_groups": len(set(t["parallel_group"] for t in self.tasks)),
            },
        )

        logger.info(f"Created wave node: {wave_node_id}")
        return wave_node_id

    def execute_wave(self) -> dict[str, Any]:
        """Execute all tasks in the wave, grouped by parallel_group.

        Returns:
            dict: Wave execution summary with keys:
                - wave_id: str
                - status: str ('completed' or 'failed')
                - tasks_completed: int
                - tasks_failed: int
                - duration_seconds: float
                - wave_node_id: str (execution graph node)
        """
        # Update wave status to 'running'
        started_at = datetime.now(timezone.utc).isoformat()

        # Emit event and link to wave node
        event_id = emit_event(
            event_type=EventType.WAVE_STARTED,
            payload={
                "wave_id": self.wave_id,
                "wave_node_id": self.wave_node_id,
                "started_at": started_at,
            },
            severity="info",
            source_type="wave_executor_enhanced",
        )

        # Link event to wave node
        if event_id:
            self.integration.link_event_to_node(event_id, self.wave_node_id)

        # Update wave status in database
        with transaction() as conn:
            conn.execute(
                "UPDATE pi_waves SET status = 'running', started_at = ? WHERE wave_id = ?",
                (started_at, self.wave_id),
            )

        # Update wave node status in execution graph
        self.integration.start_node_execution(self.wave_node_id)

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
        task_outputs = []

        try:
            for group_num in sorted(groups.keys()):
                group_tasks = groups[group_num]

                # Create task nodes for this group
                for task in group_tasks:
                    task_node_id = self.integration.create_task_node(
                        task_title=task["task_name"],
                        wave_node_id=self.wave_node_id,
                        task_description=task.get("task_description"),
                        metadata={
                            "task_number": task["task_number"],
                            "parallel_group": task["parallel_group"],
                            "skill_name": task.get("skill_name"),
                            "estimated_tokens": task.get("estimated_tokens"),
                        },
                    )
                    task["node_id"] = task_node_id

                # Spawn agents for all tasks in this group
                agent_ids = []
                for task in group_tasks:
                    # Get compiled context for this task (THE KEY INTEGRATION)
                    compiled_context = self.integration.get_compiled_context_for_task(
                        task["node_id"]
                    )

                    logger.info(
                        f"Task {task['task_name']}: Using compiled context "
                        f"({compiled_context.get('_metadata', {}).get('total_tokens', 'N/A')} tokens, "
                        f"{compiled_context.get('_metadata', {}).get('savings_pct', 'N/A')}% savings)"
                    )

                    # Spawn task agent with compiled context
                    agent_id = self._spawn_task_agent(task, compiled_context)
                    agent_ids.append(agent_id)

                    # Mark task as active
                    self.integration.start_node_execution(task["node_id"])

                # Wait for all agents in this group to complete
                results = self._wait_for_group(agent_ids)

                # Update task statuses based on results
                for i, result in enumerate(results):
                    task = group_tasks[i]
                    task_node_id = task["node_id"]

                    if result["status"] == "completed":
                        tasks_completed += 1

                        # Store task output in execution graph
                        self.integration.complete_node_execution(
                            node_id=task_node_id,
                            duration_seconds=result.get("duration_seconds"),
                            outputs=[
                                {
                                    "type": "result",
                                    "summary": result.get("summary", "Task completed"),
                                    "data": result.get("output_data"),
                                    "file_paths": result.get("file_paths"),
                                    "tokens_produced": result.get("tokens_produced"),
                                }
                            ],
                        )

                        task_outputs.append(
                            {
                                "task_name": task["task_name"],
                                "task_node_id": task_node_id,
                                "output": result.get("output_data"),
                            }
                        )

                    else:
                        tasks_failed += 1

                        # Mark task as failed in execution graph
                        self.integration.fail_node_execution(
                            node_id=task_node_id,
                            duration_seconds=result.get("duration_seconds"),
                            error=result.get("error", "Task failed"),
                        )

            # Calculate final metrics
            completed_at = datetime.now(timezone.utc).isoformat()
            duration_seconds = (
                datetime.fromisoformat(completed_at) - datetime.fromisoformat(started_at)
            ).total_seconds()

            success_rate = self._calculate_success_rate()

            # Determine final wave status
            final_status = "completed" if tasks_failed == 0 else "failed"

            # Emit completion event and link to wave node
            event_id = emit_event(
                event_type=EventType.WAVE_COMPLETED,
                payload={
                    "wave_id": self.wave_id,
                    "wave_node_id": self.wave_node_id,
                    "completed_at": completed_at,
                    "duration_seconds": duration_seconds,
                    "tasks_completed": tasks_completed,
                    "tasks_failed": tasks_failed,
                    "success_rate": success_rate,
                },
                severity="info",
                source_type="wave_executor_enhanced",
            )

            if event_id:
                self.integration.link_event_to_node(event_id, self.wave_node_id)

            # Update wave with final status in database
            with transaction() as conn:
                conn.execute(
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

            # Update wave node in execution graph
            if final_status == "completed":
                self.integration.complete_node_execution(
                    node_id=self.wave_node_id,
                    duration_seconds=duration_seconds,
                    outputs=[
                        {
                            "type": "result",
                            "summary": f"Wave completed: {tasks_completed} tasks",
                            "data": {
                                "tasks_completed": tasks_completed,
                                "tasks_failed": tasks_failed,
                                "success_rate": success_rate,
                                "task_outputs": task_outputs,
                            },
                        }
                    ],
                )
            else:
                self.integration.fail_node_execution(
                    node_id=self.wave_node_id,
                    duration_seconds=duration_seconds,
                    error=f"{tasks_failed} tasks failed",
                )

            return {
                "wave_id": self.wave_id,
                "wave_node_id": self.wave_node_id,
                "status": final_status,
                "tasks_completed": tasks_completed,
                "tasks_failed": tasks_failed,
                "duration_seconds": duration_seconds,
                "success_rate": success_rate,
            }
        except Exception:
            logger.exception("Wave execution failed: %s", self.wave_id)
            raise

    def _spawn_task_agent(self, task: dict, compiled_context: Optional[dict] = None) -> str:
        """Spawn task agent with compiled context.

        Args:
            task: Task dict with metadata
            compiled_context: Compiled context from ContextCompiler

        Returns:
            str: Agent ID
        """
        # Placeholder implementation
        # In production, this would spawn actual agent with compiled_context
        import uuid

        agent_id = str(uuid.uuid4())

        logger.info(
            f"[PLACEHOLDER] Spawned agent {agent_id} for task {task['task_name']} "
            f"with context tokens: {compiled_context.get('_metadata', {}).get('total_tokens', 'N/A') if compiled_context else 'None'}"
        )

        return agent_id

    def _wait_for_group(self, agent_ids: list[str]) -> list[dict]:
        """Wait for all agents in group to complete.

        Args:
            agent_ids: List of agent IDs

        Returns:
            List of result dicts
        """
        # Placeholder implementation
        # In production, this would wait for actual agent completion
        results = []
        for agent_id in agent_ids:
            results.append(
                {
                    "agent_id": agent_id,
                    "status": "completed",
                    "duration_seconds": 10.0,
                    "summary": f"Agent {agent_id} completed",
                    "output_data": {"result": "success"},
                    "tokens_produced": 500,
                }
            )

        return results

    def _calculate_success_rate(self) -> float:
        """Calculate wave success rate."""
        total_tasks = len(self.tasks)
        if total_tasks == 0:
            return 0.0

        with get_connection() as conn:
            completed_tasks = sum(
                1
                for task in self.tasks
                if conn.execute(
                    "SELECT status FROM pi_wave_tasks WHERE wave_id = ? AND task_number = ?",
                    (self.wave_id, task["task_number"]),
                ).fetchone()[0]
                == "completed"
            )

        return (completed_tasks / total_tasks) * 100.0
