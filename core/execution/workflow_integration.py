"""Workflow-to-Graph Integration Layer.

Bridges the existing workflow execution system with the new execution graph.
Creates execution nodes for workflows/waves/tasks and links events/outputs.

Part of Phase 5: Workflow Integration.

Created: 2026-05-07
"""

from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import logging

from core.execution.graph import ExecutionGraphManager
from core.execution.context_compiler import ContextCompiler
from core.config.database import get_connection, DatabaseContext
from core.ontology.lifecycles import ExecutionLifecycle, to_db_value

logger = logging.getLogger(__name__)


class WorkflowGraphIntegration:
    """Integrates workflow execution with execution graph."""

    def __init__(self):
        """Initialize workflow-graph integration."""
        self.graph = ExecutionGraphManager()
        self.compiler = ContextCompiler()

    def create_project_node(
        self,
        project_title: str,
        project_description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a project node in the execution graph.

        Args:
            project_title: Project title
            project_description: Project description
            metadata: Additional metadata

        Returns:
            str: Created project node_id
        """
        node_id = self.graph.create_node(
            node_type="project",
            title=project_title,
            description=project_description,
            metadata=metadata,
        )

        logger.info(f"Created project node: {node_id}")
        return node_id

    def create_wave_node(
        self,
        wave_id: str,
        wave_title: str,
        project_node_id: str,
        wave_description: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a wave node in the execution graph.

        Args:
            wave_id: Wave ID from pi_waves table
            wave_title: Wave title
            project_node_id: Parent project node
            wave_description: Wave description
            metadata: Additional metadata

        Returns:
            str: Created wave node_id
        """
        # Include wave_id in metadata for linking
        if metadata is None:
            metadata = {}
        metadata["pi_wave_id"] = wave_id

        node_id = self.graph.create_node(
            node_type="wave",
            title=wave_title,
            description=wave_description,
            parent_id=project_node_id,
            metadata=metadata,
        )

        logger.info(f"Created wave node: {node_id} (pi_wave_id: {wave_id})")
        return node_id

    def create_task_node(
        self,
        task_title: str,
        wave_node_id: str,
        task_description: Optional[str] = None,
        dependencies: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Create a task node in the execution graph.

        Args:
            task_title: Task title
            wave_node_id: Parent wave node
            task_description: Task description
            dependencies: List of task node_ids this task depends on
            metadata: Additional metadata

        Returns:
            str: Created task node_id
        """
        node_id = self.graph.create_node(
            node_type="task",
            title=task_title,
            description=task_description,
            parent_id=wave_node_id,
            metadata=metadata,
        )

        # Add dependencies if specified
        if dependencies:
            for dep_node_id in dependencies:
                self.graph.add_dependency(
                    source_node_id=node_id,
                    target_node_id=dep_node_id,
                    dependency_type="blocks",
                    reason="Task dependency",
                )

        logger.info(f"Created task node: {node_id}")
        return node_id

    def start_node_execution(self, node_id: str) -> bool:
        """
        Mark node as started (active).

        Args:
            node_id: Node to start

        Returns:
            bool: True if updated
        """
        return self.graph.update_status(node_id, to_db_value(ExecutionLifecycle.ACTIVE))

    def complete_node_execution(
        self,
        node_id: str,
        duration_seconds: Optional[float] = None,
        outputs: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        Mark node as completed and store outputs.

        Args:
            node_id: Node to complete
            duration_seconds: Execution duration
            outputs: List of output dicts with keys: type, summary, data, file_paths

        Returns:
            bool: True if updated
        """
        self.graph.update_status(
            node_id, to_db_value(ExecutionLifecycle.COMPLETED), duration_seconds
        )

        # Add outputs
        if outputs:
            for output in outputs:
                self.graph.add_output(
                    node_id=node_id,
                    output_type=output.get("type", "result"),
                    output_summary=output.get("summary"),
                    output_data=output.get("data"),
                    file_paths=output.get("file_paths"),
                    tokens_produced=output.get("tokens_produced"),
                )

        logger.info(f"Completed node: {node_id}")
        return True

    def fail_node_execution(
        self, node_id: str, duration_seconds: Optional[float] = None, error: Optional[str] = None
    ) -> bool:
        """
        Mark node as failed.

        Args:
            node_id: Node to fail
            duration_seconds: Execution duration
            error: Error message

        Returns:
            bool: True if updated
        """
        self.graph.update_status(node_id, to_db_value(ExecutionLifecycle.FAILED), duration_seconds)

        # Store error as output
        if error:
            self.graph.add_output(
                node_id=node_id,
                output_type="result",
                output_summary=f"Error: {error[:200]}",
                output_data={"error": error, "failed_at": datetime.now(timezone.utc).isoformat()},
            )

        logger.info(f"Failed node: {node_id}")
        return True

    def link_event_to_node(self, event_id: str, node_id: str) -> bool:
        """
        Link a canonical event to an execution node.

        Args:
            event_id: Event ID from canonical_events
            node_id: Node ID

        Returns:
            bool: True if linked
        """
        import uuid

        link_id = str(uuid.uuid4())

        with DatabaseContext() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO execution_event_links (link_id, node_id, event_id)
                VALUES (?, ?, ?)
                """,
                (link_id, node_id, event_id),
            )

        return True

    def get_compiled_context_for_task(self, task_node_id: str) -> Optional[Dict[str, Any]]:
        """
        Get compiled context for a task node.

        This is the key integration: replaces full context dumps with
        minimal compiled context.

        Args:
            task_node_id: Task node ID

        Returns:
            Dict with compiled context or None
        """
        compiled = self.compiler.compile_for_node(task_node_id)

        if not compiled:
            logger.error(f"Failed to compile context for task: {task_node_id}")
            return None

        # Export as dict for LLM consumption
        context = self.compiler.export_context(compiled)

        logger.info(
            f"Compiled context for {task_node_id}: "
            f"{compiled.total_tokens} tokens ({compiled.savings_pct:.1f}% savings)"
        )

        return context

    def get_execution_summary(self, project_node_id: str) -> Dict[str, Any]:
        """
        Get execution summary for a project.

        Args:
            project_node_id: Project node ID

        Returns:
            Dict with execution metrics
        """
        with get_connection(read_only=True) as conn:
            # Count nodes by type and status
            cursor = conn.execute(
                """
                SELECT node_type, status, COUNT(*) as count
                FROM execution_nodes
                WHERE project_id = ?
                GROUP BY node_type, status
                """,
                (project_node_id,),
            )

            metrics = {}
            for row in cursor.fetchall():
                node_type, status, count = row
                if node_type not in metrics:
                    metrics[node_type] = {}
                metrics[node_type][status] = count

            # Get token metrics
            cursor = conn.execute(
                """
                SELECT
                    AVG(context_tokens) as avg_context_tokens,
                    SUM(context_tokens) as total_context_tokens,
                    COUNT(*) as nodes_with_context
                FROM execution_nodes
                WHERE project_id = ? AND context_tokens IS NOT NULL
                """,
                (project_node_id,),
            )
            token_row = cursor.fetchone()

            return {
                "metrics": metrics,
                "token_stats": {
                    "avg_context_tokens": token_row[0] if token_row else 0,
                    "total_context_tokens": token_row[1] if token_row else 0,
                    "nodes_with_context": token_row[2] if token_row else 0,
                },
            }
