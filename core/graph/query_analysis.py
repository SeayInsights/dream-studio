"""Impact analysis, cycle detection, centrality, pathfinding, and project stats.

WO-GF-CORE-DATA-split: split from core/graph/query.py — see query_shared.py
for the module-level split rationale.
"""

from __future__ import annotations
from pathlib import Path

import networkx as nx

from .query_shared import Component, ImpactReport, _timed, _get_component_details, logger
from .query_traversal import build_graph, get_dependents


@_timed
def analyze_impact(
    component_id: str,
    depth: int = 2,
    project_id: str | None = None,
    graph: nx.DiGraph | None = None,
    db_path: Path | None = None,
) -> ImpactReport:
    """Analyze the impact of changes to a component.

    Calculates the scope of impact when a component is modified by identifying
    all affected dependents and computing a risk score based on the percentage
    of total components in the project that would be impacted.

    Risk thresholds:
    - Low: <0.05 (affects <5% of components)
    - Medium: 0.05-0.2 (affects 5-20% of components)
    - High: >0.2 (affects >20% of components)

    Args:
        component_id: Starting component identifier
        depth: Number of hops to traverse (default: 2 for direct + transitive dependents)
        project_id: Required if graph is not provided
        graph: Optional pre-built graph (if None, will build from project_id)
        db_path: Optional path to SQLite database

    Returns:
        ImpactReport with affected components list and calculated risk_score

    Raises:
        ValueError: If component_id not found or if neither graph nor project_id provided

    Example:
        >>> report = analyze_impact("component_123", depth=2, project_id="dream-studio")
        >>> print(f"Risk: {report.risk_score:.2%}")
        >>> print(f"Affects {len(report.affected_components)} components")
    """
    if graph is None:
        if project_id is None:
            raise ValueError("Either graph or project_id must be provided")
        graph = build_graph(project_id, db_path)

    if component_id not in graph:
        raise ValueError(f"Component '{component_id}' not found in graph")

    # Get all dependents using existing function
    affected = get_dependents(component_id, depth=depth, graph=graph, db_path=db_path)

    # Calculate risk score as percentage of total components
    total_components = graph.number_of_nodes()
    risk_score = len(affected) / total_components if total_components > 0 else 0.0

    report = ImpactReport(
        component_id=component_id, affected_components=affected, risk_score=risk_score, depth=depth
    )

    risk_level = "low" if risk_score < 0.05 else ("medium" if risk_score < 0.2 else "high")
    logger.info(
        f"Impact analysis for {component_id}: {len(affected)} affected components, "
        f"risk_score={risk_score:.4f} ({risk_level})"
    )

    return report


@_timed
def detect_cycles(
    project_id: str | None = None, graph: nx.DiGraph | None = None, db_path: Path | None = None
) -> list[list[Component]]:
    """Find circular dependencies (cycles) in the dependency graph.

    Uses NetworkX's simple_cycles algorithm to find all cycles. Cycles are returned
    as lists of components forming the circular dependency chain.

    Args:
        project_id: Required if graph is not provided
        graph: Optional pre-built graph (if None, will build from project_id)
        db_path: Optional path to SQLite database

    Returns:
        List of cycles, where each cycle is a list of Component objects
        Empty list if no cycles detected

    Raises:
        ValueError: If neither graph nor project_id provided

    Example:
        >>> cycles = detect_cycles(project_id="dream-studio")
        >>> if cycles:
        ...     print(f"Found {len(cycles)} circular dependencies")
        ...     for cycle in cycles:
        ...         print(" -> ".join(c.name for c in cycle))
    """
    if graph is None:
        if project_id is None:
            raise ValueError("Either graph or project_id must be provided")
        graph = build_graph(project_id, db_path)

    # Find all cycles using NetworkX
    try:
        cycle_nodes = list(nx.simple_cycles(graph))
    except Exception as e:
        logger.error(f"Error detecting cycles: {e}")
        return []

    # Convert node IDs to Component objects
    cycles = []
    for cycle_node_ids in cycle_nodes:
        cycle_components = [
            _get_component_details(node_id, graph, db_path) for node_id in cycle_node_ids
        ]
        cycles.append(cycle_components)

    logger.info(f"Detected {len(cycles)} circular dependencies")
    return cycles


@_timed
def calculate_centrality(graph: nx.DiGraph) -> dict[str, float]:
    """Calculate PageRank centrality scores for all components.

    PageRank identifies the most "important" components based on the dependency graph
    structure. Components with many incoming dependencies and dependencies from other
    important components score higher.

    Args:
        graph: NetworkX DiGraph (typically from build_graph())

    Returns:
        Dictionary mapping component_id to centrality score (0.0 to 1.0)
        Empty dict if graph is empty

    Example:
        >>> graph = build_graph("dream-studio")
        >>> scores = calculate_centrality(graph)
        >>> top_components = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:10]
        >>> for comp_id, score in top_components:
        ...     print(f"{graph.nodes[comp_id]['name']}: {score:.4f}")
    """
    if graph.number_of_nodes() == 0:
        logger.warning("Cannot calculate centrality for empty graph")
        return {}

    try:
        # Use PageRank for centrality
        centrality = nx.pagerank(graph, max_iter=100, tol=1e-6)
        logger.debug(f"Calculated centrality for {len(centrality)} components")
        return centrality
    except Exception as e:
        logger.error(f"Error calculating centrality: {e}")
        return {}


@_timed
def shortest_path(
    source_id: str,
    target_id: str,
    project_id: str | None = None,
    graph: nx.DiGraph | None = None,
    db_path: Path | None = None,
) -> list[Component]:
    """Find shortest dependency path between two components.

    Uses Dijkstra's algorithm to find the shortest path from source to target
    following the direction of dependencies.

    Args:
        source_id: Starting component identifier
        target_id: Target component identifier
        project_id: Required if graph is not provided
        graph: Optional pre-built graph (if None, will build from project_id)
        db_path: Optional path to SQLite database

    Returns:
        List of Component objects representing the path from source to target
        Empty list if no path exists

    Raises:
        ValueError: If source_id or target_id not found, or neither graph nor project_id provided

    Example:
        >>> path = shortest_path("comp_a", "comp_b", project_id="dream-studio")
        >>> if path:
        ...     print(" -> ".join(c.name for c in path))
        ... else:
        ...     print("No path found")
    """
    if graph is None:
        if project_id is None:
            raise ValueError("Either graph or project_id must be provided")
        graph = build_graph(project_id, db_path)

    if source_id not in graph:
        raise ValueError(f"Source component '{source_id}' not found in graph")

    if target_id not in graph:
        raise ValueError(f"Target component '{target_id}' not found in graph")

    try:
        # Find shortest path using NetworkX
        path_nodes = nx.shortest_path(graph, source=source_id, target=target_id)

        # Convert to Component objects
        path_components = [
            _get_component_details(node_id, graph, db_path) for node_id in path_nodes
        ]

        logger.debug(f"Found path from {source_id} to {target_id}: {len(path_components)} nodes")
        return path_components

    except nx.NetworkXNoPath:
        logger.debug(f"No path exists from {source_id} to {target_id}")
        return []
    except Exception as e:
        logger.error(f"Error finding shortest path: {e}")
        return []


@_timed
def detect_communities(graph: nx.DiGraph) -> dict[str, int]:
    """Detect communities (clusters) in the dependency graph using Louvain algorithm.

    Communities represent groups of components that depend heavily on each other.
    This is useful for visualizing architectural modules and identifying coupling.

    Uses the Louvain method for community detection, which optimizes modularity
    to find densely connected groups.

    Args:
        graph: NetworkX DiGraph (typically from build_graph())

    Returns:
        Dictionary mapping component_id to community_id (integer)
        Empty dict if graph is empty or has no edges

    Example:
        >>> graph = build_graph("dream-studio")
        >>> communities = detect_communities(graph)
        >>> # Group components by community
        >>> from collections import defaultdict
        >>> groups = defaultdict(list)
        >>> for comp_id, comm_id in communities.items():
        ...     groups[comm_id].append(comp_id)
        >>> print(f"Found {len(groups)} communities")
    """
    if graph.number_of_nodes() == 0:
        logger.warning("Cannot detect communities for empty graph")
        return {}

    if graph.number_of_edges() == 0:
        logger.warning("Cannot detect communities for graph with no edges")
        return {}

    try:
        # Convert directed graph to undirected for community detection
        # (Louvain algorithm works on undirected graphs)
        undirected = graph.to_undirected()

        # Detect communities using Louvain method
        communities_sets = nx.community.louvain_communities(undirected)

        # Convert sets to dict: {component_id: community_id}
        component_to_community = {}
        for community_id, community_set in enumerate(communities_sets):
            for component_id in community_set:
                component_to_community[component_id] = community_id

        logger.info(
            f"Detected {len(communities_sets)} communities across {len(component_to_community)} components"
        )
        return component_to_community

    except Exception as e:
        logger.error(f"Error detecting communities: {e}")
        return {}


@_timed
def get_project_stats(project_id: str, db_path: Path | None = None) -> dict[str, any]:
    """Get aggregate statistics for a project's dependency graph.

    Calculates component count, dependency count, average centrality,
    and breakdown by component type.

    Args:
        project_id: Project identifier
        db_path: Optional path to SQLite database

    Returns:
        Dictionary with stats:
        - component_count: Total number of components
        - dependency_count: Total number of dependencies
        - avg_centrality: Average PageRank centrality score
        - component_types: Dict mapping component_type to count

    Example:
        >>> stats = get_project_stats("dream-studio")
        >>> print(f"Components: {stats['component_count']}")
        >>> print(f"Dependencies: {stats['dependency_count']}")
        >>> print(f"Component types: {stats['component_types']}")
    """
    try:
        # Build graph
        graph = build_graph(project_id, db_path)

        # Basic counts
        component_count = graph.number_of_nodes()
        dependency_count = graph.number_of_edges()

        # Calculate average centrality
        if component_count > 0:
            centrality = calculate_centrality(graph)
            avg_centrality = sum(centrality.values()) / len(centrality) if centrality else 0.0
        else:
            avg_centrality = 0.0

        # Component types breakdown
        component_types = {}
        for node_id in graph.nodes():
            comp_type = graph.nodes[node_id].get("type", "unknown")
            component_types[comp_type] = component_types.get(comp_type, 0) + 1

        stats = {
            "component_count": component_count,
            "dependency_count": dependency_count,
            "avg_centrality": avg_centrality,
            "component_types": component_types,
        }

        logger.debug(
            f"Project stats for {project_id}: {component_count} components, "
            f"{dependency_count} dependencies, avg_centrality={avg_centrality:.6f}"
        )
        return stats

    except Exception as e:
        logger.error(f"Error getting project stats for {project_id}: {e}")
        raise
