"""Execution Graph Manager - Persistent DAG for all execution.

Manages the execution graph: a persistent DAG representing the full execution
tree from project → prd → plan → phase → wave → task.

Part of Phase 3: Execution Graph Layer.

Created: 2026-05-07
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from uuid import uuid4
import hashlib
import json
import logging

from core.config.database import get_connection, DatabaseContext
from core.ontology.lifecycles import LIFECYCLE_CATALOG, ExecutionLifecycle, to_db_value

logger = logging.getLogger(__name__)

_PENDING = to_db_value(ExecutionLifecycle.PENDING)
_ACTIVE = to_db_value(ExecutionLifecycle.ACTIVE)
_TERMINAL_STATES = (
    to_db_value(ExecutionLifecycle.COMPLETED),
    to_db_value(ExecutionLifecycle.FAILED),
    to_db_value(ExecutionLifecycle.SKIPPED),
)


@dataclass
class ExecutionNode:
    """Represents a node in the execution graph."""

    node_id: str
    node_type: str  # project, prd, plan, phase, wave, task
    parent_id: Optional[str]
    title: str
    description: Optional[str]
    status: str  # pending, active, blocked, completed, failed, skipped
    context_hash: Optional[str]
    context_tokens: Optional[int]
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class ExecutionDependency:
    """Represents a dependency edge between nodes."""

    dependency_id: str
    source_node_id: str
    target_node_id: str
    dependency_type: str  # blocks, informs, follows
    reason: Optional[str]


@dataclass
class ExecutionOutput:
    """Represents output produced by a node."""

    output_id: str
    node_id: str
    output_type: str  # code, document, decision, artifact, result
    output_hash: Optional[str]
    output_summary: Optional[str]
    output_data: Optional[Dict[str, Any]]
    file_paths: Optional[List[str]]
    tokens_produced: Optional[int]


class ExecutionGraphManager:
    """Manages execution graph operations."""

    def __init__(self):
        """Initialize graph manager."""
        pass

    def create_node(
        self,
        node_type: str,
        title: str,
        description: Optional[str] = None,
        parent_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        priority: int = 0,
    ) -> str:
        """
        Create a new execution node.

        Args:
            node_type: Type of node (project, prd, plan, phase, wave, task)
            title: Node title
            description: Optional description
            parent_id: Parent node ID (None for root nodes)
            context: Context given to this node
            metadata: Additional metadata
            priority: Node priority (higher = more urgent)

        Returns:
            str: Created node_id
        """
        node_id = str(uuid4())

        # Compute context hash if context provided
        context_hash = None
        context_tokens = None
        if context:
            context_json = json.dumps(context, sort_keys=True)
            context_hash = hashlib.sha256(context_json.encode()).hexdigest()
            # Rough token estimate: ~4 chars per token
            context_tokens = len(context_json) // 4

        # Determine hierarchy IDs from parent
        project_id = None
        prd_id = None
        plan_id = None
        phase_id = None
        wave_id = None

        if parent_id:
            parent = self.get_node(parent_id)
            if parent:
                # Inherit hierarchy from parent
                if parent.node_type == "project":
                    project_id = parent_id
                elif parent.node_type == "prd":
                    project_id = parent.parent_id
                    prd_id = parent_id
                elif parent.node_type == "plan":
                    # Get project/prd from parent
                    with get_connection(read_only=True) as conn:
                        cursor = conn.execute(
                            "SELECT project_id, prd_id FROM execution_nodes WHERE node_id = ?",
                            (parent_id,),
                        )
                        row = cursor.fetchone()
                        if row:
                            project_id, prd_id = row[0], row[1]
                    plan_id = parent_id
                elif parent.node_type == "phase":
                    with get_connection(read_only=True) as conn:
                        cursor = conn.execute(
                            "SELECT project_id, prd_id, plan_id FROM execution_nodes WHERE node_id = ?",
                            (parent_id,),
                        )
                        row = cursor.fetchone()
                        if row:
                            project_id, prd_id, plan_id = row[0], row[1], row[2]
                    phase_id = parent_id
                elif parent.node_type == "wave":
                    with get_connection(read_only=True) as conn:
                        cursor = conn.execute(
                            "SELECT project_id, prd_id, plan_id, phase_id FROM execution_nodes WHERE node_id = ?",
                            (parent_id,),
                        )
                        row = cursor.fetchone()
                        if row:
                            project_id, prd_id, plan_id, phase_id = row[0], row[1], row[2], row[3]
                    wave_id = parent_id

        # If this is a project node, set project_id to itself
        if node_type == "project":
            project_id = node_id

        # Insert node
        with DatabaseContext() as conn:
            conn.execute(
                """
                INSERT INTO execution_nodes (
                    node_id, node_type, parent_id, title, description,
                    project_id, prd_id, plan_id, phase_id, wave_id,
                    context_hash, context_tokens, metadata, priority, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    node_id,
                    node_type,
                    parent_id,
                    title,
                    description,
                    project_id,
                    prd_id,
                    plan_id,
                    phase_id,
                    wave_id,
                    context_hash,
                    context_tokens,
                    json.dumps(metadata) if metadata else None,
                    priority,
                    _PENDING,
                ),
            )

        logger.info(f"Created {node_type} node: {node_id} - {title}")
        return node_id

    def get_node(self, node_id: str) -> Optional[ExecutionNode]:
        """
        Get node by ID.

        Args:
            node_id: Node ID

        Returns:
            ExecutionNode or None if not found
        """
        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                """
                SELECT node_id, node_type, parent_id, title, description,
                       status, context_hash, context_tokens,
                       created_at, started_at, completed_at, metadata
                FROM execution_nodes
                WHERE node_id = ?
                """,
                (node_id,),
            )
            row = cursor.fetchone()

            if not row:
                return None

            return ExecutionNode(
                node_id=row[0],
                node_type=row[1],
                parent_id=row[2],
                title=row[3],
                description=row[4],
                status=row[5],
                context_hash=row[6],
                context_tokens=row[7],
                created_at=row[8],
                started_at=row[9],
                completed_at=row[10],
                metadata=json.loads(row[11]) if row[11] else None,
            )

    def update_status(
        self, node_id: str, status: str, duration_seconds: Optional[float] = None
    ) -> bool:
        """
        Update node status.

        Args:
            node_id: Node ID
            status: New status
            duration_seconds: Optional duration for completed/failed nodes

        Returns:
            bool: True if updated
        """
        now = datetime.now(timezone.utc).isoformat()

        if not LIFECYCLE_CATALOG.validate_state("workflow", status):
            logger.warning("Unrecognized execution status: %s", status)

        if status == _ACTIVE:
            started_at = now
            completed_at = None
        elif status in _TERMINAL_STATES:
            started_at = None
            completed_at = now
        else:
            started_at = None
            completed_at = None

        with DatabaseContext() as conn:
            if status == _ACTIVE:
                conn.execute(
                    "UPDATE execution_nodes SET status = ?, started_at = ? WHERE node_id = ?",
                    (status, started_at, node_id),
                )
            elif status in _TERMINAL_STATES:
                conn.execute(
                    """
                    UPDATE execution_nodes
                    SET status = ?, completed_at = ?, duration_seconds = ?
                    WHERE node_id = ?
                    """,
                    (status, completed_at, duration_seconds, node_id),
                )
            else:
                conn.execute(
                    "UPDATE execution_nodes SET status = ? WHERE node_id = ?", (status, node_id)
                )

        logger.info(f"Updated node {node_id} status: {status}")
        return True

    def add_dependency(
        self,
        source_node_id: str,
        target_node_id: str,
        dependency_type: str,
        reason: Optional[str] = None,
    ) -> str:
        """
        Add dependency between nodes.

        Args:
            source_node_id: Node that depends (will be blocked)
            target_node_id: Node that is depended on (must complete first)
            dependency_type: 'blocks', 'informs', or 'follows'
            reason: Optional reason for dependency

        Returns:
            str: Created dependency_id
        """
        dependency_id = str(uuid4())

        with DatabaseContext() as conn:
            conn.execute(
                """
                INSERT INTO execution_dependencies (
                    dependency_id, source_node_id, target_node_id,
                    dependency_type, reason
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (dependency_id, source_node_id, target_node_id, dependency_type, reason),
            )

        logger.info(f"Added dependency: {source_node_id} {dependency_type} {target_node_id}")
        return dependency_id

    def add_output(
        self,
        node_id: str,
        output_type: str,
        output_summary: Optional[str] = None,
        output_data: Optional[Dict[str, Any]] = None,
        file_paths: Optional[List[str]] = None,
        tokens_produced: Optional[int] = None,
    ) -> str:
        """
        Add output produced by a node.

        Args:
            node_id: Node that produced output
            output_type: Type of output
            output_summary: Human-readable summary
            output_data: Structured output data
            file_paths: List of file paths created
            tokens_produced: Token count of output

        Returns:
            str: Created output_id
        """
        output_id = str(uuid4())

        # Compute output hash
        output_hash = None
        if output_data:
            output_json = json.dumps(output_data, sort_keys=True)
            output_hash = hashlib.sha256(output_json.encode()).hexdigest()

        file_paths_str = "\n".join(file_paths) if file_paths else None

        with DatabaseContext() as conn:
            conn.execute(
                """
                INSERT INTO execution_outputs (
                    output_id, node_id, output_type, output_hash,
                    output_summary, output_data, file_paths, tokens_produced
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    output_id,
                    node_id,
                    output_type,
                    output_hash,
                    output_summary,
                    json.dumps(output_data) if output_data else None,
                    file_paths_str,
                    tokens_produced,
                ),
            )

        logger.info(f"Added output for node {node_id}: {output_type}")
        return output_id

    def get_children(self, node_id: str) -> List[ExecutionNode]:
        """
        Get all child nodes of a node.

        Args:
            node_id: Parent node ID

        Returns:
            List of ExecutionNode objects
        """
        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                """
                SELECT node_id, node_type, parent_id, title, description,
                       status, context_hash, context_tokens,
                       created_at, started_at, completed_at, metadata
                FROM execution_nodes
                WHERE parent_id = ?
                ORDER BY created_at ASC
                """,
                (node_id,),
            )

            nodes = []
            for row in cursor.fetchall():
                nodes.append(
                    ExecutionNode(
                        node_id=row[0],
                        node_type=row[1],
                        parent_id=row[2],
                        title=row[3],
                        description=row[4],
                        status=row[5],
                        context_hash=row[6],
                        context_tokens=row[7],
                        created_at=row[8],
                        started_at=row[9],
                        completed_at=row[10],
                        metadata=json.loads(row[11]) if row[11] else None,
                    )
                )

            return nodes

    def get_dependencies(self, node_id: str) -> List[ExecutionDependency]:
        """
        Get all dependencies for a node (what this node depends on).

        Args:
            node_id: Node ID

        Returns:
            List of ExecutionDependency objects
        """
        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                """
                SELECT dependency_id, source_node_id, target_node_id,
                       dependency_type, reason
                FROM execution_dependencies
                WHERE source_node_id = ?
                """,
                (node_id,),
            )

            deps = []
            for row in cursor.fetchall():
                deps.append(
                    ExecutionDependency(
                        dependency_id=row[0],
                        source_node_id=row[1],
                        target_node_id=row[2],
                        dependency_type=row[3],
                        reason=row[4],
                    )
                )

            return deps

    def get_outputs(self, node_id: str) -> List[ExecutionOutput]:
        """
        Get all outputs produced by a node.

        Args:
            node_id: Node ID

        Returns:
            List of ExecutionOutput objects
        """
        with get_connection(read_only=True) as conn:
            cursor = conn.execute(
                """
                SELECT output_id, node_id, output_type, output_hash,
                       output_summary, output_data, file_paths, tokens_produced
                FROM execution_outputs
                WHERE node_id = ?
                ORDER BY created_at ASC
                """,
                (node_id,),
            )

            outputs = []
            for row in cursor.fetchall():
                file_paths = row[6].split("\n") if row[6] else None
                outputs.append(
                    ExecutionOutput(
                        output_id=row[0],
                        node_id=row[1],
                        output_type=row[2],
                        output_hash=row[3],
                        output_summary=row[4],
                        output_data=json.loads(row[5]) if row[5] else None,
                        file_paths=file_paths,
                        tokens_produced=row[7],
                    )
                )

            return outputs
