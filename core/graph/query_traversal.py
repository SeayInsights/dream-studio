"""Graph construction and BFS traversal (dependencies / dependents).

WO-GF-CORE-DATA-split: split from core/graph/query.py — see query_shared.py
for the module-level split rationale.
"""

from __future__ import annotations
from pathlib import Path

import networkx as nx

from .query_shared import Component, _cached_builder, _timed, _get_component_details, logger


@_timed
def build_graph(project_id: str, db_path: Path | None = None) -> nx.DiGraph:
    """Build NetworkX directed graph from pi_dependencies table.

    The graph represents component dependencies:
    - Nodes: component_id with attributes (name, file_path, type, lines, complexity_score)
    - Edges: source_component_id → target_component_id (dependency relationships)

    Results are cached with staleness detection for 5 minutes to improve performance.

    Cache strategy:
    - Key format: {project_id}_{max_updated_at} (detects component updates)
    - TTL: 5 minutes per entry
    - Hit performance: <50ms (returns cached copy)
    - Miss performance: Full graph build + cache store

    Args:
        project_id: Project identifier to build graph for
        db_path: Optional path to SQLite database (defaults to studio.db)

    Returns:
        NetworkX DiGraph with component nodes and dependency edges

    Raises:
        ValueError: If project_id is empty or invalid

    Example:
        >>> graph = build_graph("dream-studio")
        >>> print(f"Nodes: {graph.number_of_nodes()}, Edges: {graph.number_of_edges()}")
    """
    # Use the CachedGraphBuilder for intelligent caching with staleness detection
    return _cached_builder.build_graph_cached(project_id, db_path)


@_timed
def get_dependencies(
    component_id: str,
    depth: int = 1,
    project_id: str | None = None,
    graph: nx.DiGraph | None = None,
    db_path: Path | None = None,
) -> list[Component]:
    """Get N-hop forward dependencies (components this component depends on).

    Performs a breadth-first traversal of outgoing edges from the given component.

    Args:
        component_id: Starting component identifier
        depth: Number of hops to traverse (default: 1 for immediate dependencies)
        project_id: Required if graph is not provided
        graph: Optional pre-built graph (if None, will build from project_id)
        db_path: Optional path to SQLite database

    Returns:
        List of Component objects representing dependencies, ordered by distance

    Raises:
        ValueError: If component_id not found or if neither graph nor project_id provided

    Example:
        >>> deps = get_dependencies("component_123", depth=2, project_id="dream-studio")
        >>> print(f"Found {len(deps)} dependencies within 2 hops")
    """
    if graph is None:
        if project_id is None:
            raise ValueError("Either graph or project_id must be provided")
        graph = build_graph(project_id, db_path)

    if component_id not in graph:
        raise ValueError(f"Component '{component_id}' not found in graph")

    # Use BFS with depth limit to find dependencies
    dependencies = set()
    current_level = {component_id}

    for _ in range(depth):
        next_level = set()
        for node in current_level:
            # Get outgoing edges (successors = things this node depends on)
            successors = set(graph.successors(node))
            next_level.update(successors)
            dependencies.update(successors)
        current_level = next_level
        if not current_level:
            break

    # Convert to Component objects
    result = [_get_component_details(comp_id, graph, db_path) for comp_id in dependencies]

    logger.debug(f"Found {len(result)} dependencies for {component_id} at depth {depth}")
    return result


@_timed
def get_dependents(
    component_id: str,
    depth: int = 1,
    project_id: str | None = None,
    graph: nx.DiGraph | None = None,
    db_path: Path | None = None,
) -> list[Component]:
    """Get N-hop backward dependencies (components that depend on this component).

    Performs a breadth-first traversal of incoming edges to the given component.

    Args:
        component_id: Starting component identifier
        depth: Number of hops to traverse (default: 1 for immediate dependents)
        project_id: Required if graph is not provided
        graph: Optional pre-built graph (if None, will build from project_id)
        db_path: Optional path to SQLite database

    Returns:
        List of Component objects representing dependents, ordered by distance

    Raises:
        ValueError: If component_id not found or if neither graph nor project_id provided

    Example:
        >>> dependents = get_dependents("component_123", depth=2, project_id="dream-studio")
        >>> print(f"Found {len(dependents)} dependents within 2 hops")
    """
    if graph is None:
        if project_id is None:
            raise ValueError("Either graph or project_id must be provided")
        graph = build_graph(project_id, db_path)

    if component_id not in graph:
        raise ValueError(f"Component '{component_id}' not found in graph")

    # Use BFS with depth limit to find dependents
    dependents = set()
    current_level = {component_id}

    for _ in range(depth):
        next_level = set()
        for node in current_level:
            # Get incoming edges (predecessors = things that depend on this node)
            predecessors = set(graph.predecessors(node))
            next_level.update(predecessors)
            dependents.update(predecessors)
        current_level = next_level
        if not current_level:
            break

    # Convert to Component objects
    result = [_get_component_details(comp_id, graph, db_path) for comp_id in dependents]

    logger.debug(f"Found {len(result)} dependents for {component_id} at depth {depth}")
    return result
