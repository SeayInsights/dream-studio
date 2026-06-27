"""Execution Graph Manager - Persistent DAG for all execution.

execution_nodes, execution_dependencies, and execution_outputs were dropped
in migration 131. ExecutionGraphManager write methods are removed.
Dataclasses and lifecycle constants are kept for downstream imports.
"""

import json
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

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
    """Execution graph manager stub.

    execution_nodes, execution_dependencies, and execution_outputs were
    dropped in migration 131. All write methods raise NotImplementedError.
    Read methods return empty results to avoid hard failures in callers.
    """

    def __init__(self) -> None:
        pass

    def create_node(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError(
            "execution_nodes dropped migration 131; ExecutionGraphManager.create_node unavailable"
        )

    def get_node(self, node_id: str) -> Optional[ExecutionNode]:
        return None

    def update_status(self, node_id: str, status: str, **kwargs: Any) -> bool:
        raise NotImplementedError(
            "execution_nodes dropped migration 131; ExecutionGraphManager.update_status unavailable"
        )

    def add_dependency(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError(
            "execution_dependencies dropped migration 131; ExecutionGraphManager.add_dependency unavailable"
        )

    def add_output(self, *args: Any, **kwargs: Any) -> str:
        raise NotImplementedError(
            "execution_outputs dropped migration 131; ExecutionGraphManager.add_output unavailable"
        )

    def get_children(self, node_id: str) -> List[ExecutionNode]:
        return []

    def get_dependencies(self, node_id: str) -> List[ExecutionDependency]:
        return []

    def get_outputs(self, node_id: str) -> List[ExecutionOutput]:
        return []
