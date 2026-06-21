"""NetworkX graph builder and query engine for project dependency analysis.

This module provides graph-based querying of component dependencies using NetworkX.
It builds directed graphs from the pi_dependencies table and provides traversal,
cycle detection, centrality analysis, pathfinding, and impact analysis capabilities.

Key functions:
- build_graph(): Build directed graph from pi_dependencies
- get_dependencies(): Forward dependencies (N-hop)
- get_dependents(): Backward dependencies (N-hop)
- analyze_impact(): Impact analysis with risk scoring
- detect_cycles(): Circular dependency detection
- calculate_centrality(): PageRank-based importance scoring
- shortest_path(): Dijkstra-based path finding

Performance target: Build graph for 10k nodes in <2s.
Cache TTL: 5 minutes with staleness detection.
"""

from __future__ import annotations
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from functools import wraps

try:
    import networkx as nx
except ImportError:
    raise ImportError("NetworkX is required. Install with: pip install networkx")

from core.event_store.studio_db import _connect

# Configure logging
logger = logging.getLogger(__name__)

# Cache configuration
CACHE_TTL_SECONDS = 300  # 5 minutes
_graph_cache: Dict[str, tuple[nx.DiGraph, float]] = {}


class CachedGraphBuilder:
    """LRU-cached graph builder with TTL and staleness detection.

    Caching strategy:
    - Cache key: {project_id}_{max_updated_at} (invalidates on component updates)
    - TTL: 5 minutes per entry (configurable)
    - Performance: Cache hit returns graph in <50ms

    The cache key includes MAX(last_analyzed) from pi_components to automatically
    invalidate stale cache entries when components are updated.

    Example:
        >>> builder = CachedGraphBuilder(cache_ttl_seconds=300)
        >>> graph = builder.build_graph_cached("dream-studio")  # <50ms on cache hit
        >>> stats = builder.get_cache_stats()
    """

    def __init__(self, cache_ttl_seconds: int = 300, max_cache_size: int = 100):
        """Initialize the cached graph builder.

        Args:
            cache_ttl_seconds: Time-to-live for cached graphs in seconds (default: 300 = 5 min)
            max_cache_size: Maximum number of cached graphs to keep (default: 100)
        """
        self.cache_ttl = cache_ttl_seconds
        self.max_cache_size = max_cache_size
        self._cache: Dict[str, Tuple[nx.DiGraph, float, str]] = (
            {}
        )  # cache_key -> (graph, timestamp, max_updated_at)

    def _get_max_component_timestamp(self, project_id: str, db_path: Path | None = None) -> str:
        """Query MAX(last_analyzed) from pi_components for staleness detection.

        Args:
            project_id: Project identifier
            db_path: Optional path to SQLite database

        Returns:
            ISO timestamp string of latest component update (or '0' if no components)
        """
        try:
            conn = _connect(db_path)
            result = conn.execute(
                "SELECT MAX(last_analyzed) FROM pi_components WHERE project_id = ?", (project_id,)
            ).fetchone()
            conn.close()

            max_updated = result[0] if result and result[0] else "0"
            return max_updated
        except Exception as e:
            logger.error(f"Error querying max component timestamp for {project_id}: {e}")
            return "0"

    def _generate_cache_key(
        self,
        project_id: str,
        max_updated_at: str,
        db_path: Path | None = None,
    ) -> str:
        """Generate cache key with staleness detection.

        Key format: graph:{project_id}_{max_updated_at}
        This ensures cache invalidation when components are updated.
        """
        db_marker = str(Path(db_path).resolve()) if db_path else "runtime"
        return f"graph:{project_id}_{db_marker}_{max_updated_at}"

    def _evict_if_needed(self):
        """Evict oldest entry if cache exceeds max_cache_size."""
        if len(self._cache) >= self.max_cache_size:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
            del self._cache[oldest_key]
            logger.debug(f"Evicted cache entry {oldest_key} (cache full)")

    def _is_expired(self, timestamp: float) -> bool:
        """Check if cache entry is expired based on TTL."""
        return time.time() - timestamp > self.cache_ttl

    def build_graph_cached(self, project_id: str, db_path: Path | None = None) -> nx.DiGraph:
        """Build or retrieve cached graph with staleness detection.

        Strategy:
        1. Query MAX(last_analyzed) from pi_components
        2. Generate cache key with timestamp
        3. Check cache (time + staleness)
        4. If miss: build graph and cache it
        5. Return graph copy

        Args:
            project_id: Project identifier
            db_path: Optional path to SQLite database

        Returns:
            NetworkX DiGraph with component nodes and dependency edges

        Performance:
            - Cache hit (valid): <50ms
            - Cache miss: Full graph build + store
        """
        if not project_id:
            raise ValueError("project_id cannot be empty")

        # Step 1: Get max component update timestamp for staleness detection
        max_updated_at = self._get_max_component_timestamp(project_id, db_path)

        # Step 2: Generate cache key that includes staleness marker
        cache_key = self._generate_cache_key(project_id, max_updated_at, db_path)

        # Step 3: Check cache for valid entry
        if cache_key in self._cache:
            cached_graph, timestamp, stored_max_updated = self._cache[cache_key]
            if not self._is_expired(timestamp):
                logger.debug(f"Cache hit for {project_id} (stale marker: {max_updated_at})")
                return cached_graph.copy()
            # Entry expired, remove it
            del self._cache[cache_key]
            logger.debug(f"Cache expired for {cache_key}")

        # Step 4: Cache miss - build graph
        logger.debug(f"Cache miss for {project_id}. Building graph...")
        graph = self._build_graph_internal(project_id, db_path)

        # Step 5: Store in cache
        self._evict_if_needed()
        self._cache[cache_key] = (graph.copy(), time.time(), max_updated_at)
        logger.info(
            f"Cached graph for {project_id}: {graph.number_of_nodes()} nodes, "
            f"{graph.number_of_edges()} edges (stale marker: {max_updated_at})"
        )

        return graph

    def _build_graph_internal(self, project_id: str, db_path: Path | None = None) -> nx.DiGraph:
        """Internal graph building logic (extracted from build_graph)."""
        graph = nx.DiGraph()

        try:
            conn = _connect(db_path)

            # pi_components was dropped in migration 084; return empty graph if absent
            tables = {
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            if "pi_components" not in tables:
                conn.close()
                return graph

            # Load all components
            components_query = """
                SELECT component_id, name, path, component_type, lines, complexity_score
                FROM pi_components
                WHERE project_id = ?
            """
            component_rows = conn.execute(components_query, (project_id,)).fetchall()

            for row in component_rows:
                graph.add_node(
                    row[0],  # component_id
                    name=row[1],
                    file_path=row[2],
                    type=row[3],
                    lines=row[4],
                    complexity_score=row[5],
                )

            # Load all dependencies
            dependencies_query = """
                SELECT from_component, to_component
                FROM pi_dependencies
                WHERE project_id = ?
            """
            dependency_rows = conn.execute(dependencies_query, (project_id,)).fetchall()

            for row in dependency_rows:
                from_component = row[0]
                to_component = row[1]
                if from_component in graph and to_component in graph:
                    graph.add_edge(from_component, to_component)

            conn.close()
            return graph

        except Exception as e:
            logger.error(f"Error building graph for {project_id}: {e}")
            raise

    def clear_cache(self, project_id: str | None = None):
        """Clear cache for a project or all projects.

        Args:
            project_id: Project to clear cache for. If None, clears all.
        """
        if project_id:
            # Clear all entries matching this project_id
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(f"graph:{project_id}_")]
            for k in keys_to_delete:
                del self._cache[k]
            logger.debug(f"Cleared {len(keys_to_delete)} cache entries for {project_id}")
        else:
            self._cache.clear()
            logger.debug("Cleared all graph caches")

    def get_cache_stats(self) -> Dict[str, int]:
        """Return cache statistics."""
        return {
            "size": len(self._cache),
            "max_size": self.max_cache_size,
            "ttl_seconds": self.cache_ttl,
        }


# Global instance of cached graph builder
_cached_builder = CachedGraphBuilder(cache_ttl_seconds=CACHE_TTL_SECONDS)


@dataclass
class Component:
    """Component metadata from pi_components table."""

    component_id: str
    name: str
    file_path: str
    type: str
    lines: Optional[int] = None
    complexity_score: Optional[float] = None


@dataclass
class ImpactReport:
    """Impact analysis report for a component change.

    Attributes:
        component_id: The component being analyzed
        affected_components: List of components affected by changes to this component
        risk_score: Normalized risk (0.0-1.0) based on percentage of affected components
        depth: Traversal depth used for analysis
    """

    component_id: str
    affected_components: List[Component]
    risk_score: float
    depth: int


def _clear_expired_cache():
    """Remove expired cache entries."""
    now = time.time()
    expired = [
        k for k, (_, timestamp) in _graph_cache.items() if now - timestamp > CACHE_TTL_SECONDS
    ]
    for k in expired:
        del _graph_cache[k]


def _cache_key(project_id: str) -> str:
    """Generate cache key for a project."""
    return f"graph:{project_id}"


def _timed(fn):
    """Decorator to log function execution time."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = fn(*args, **kwargs)
        duration = time.time() - start
        logger.debug(f"{fn.__name__} completed in {duration:.3f}s")
        return result

    return wrapper


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


def _get_component_details(
    component_id: str, graph: nx.DiGraph, db_path: Path | None = None
) -> Component:
    """Fetch component details from graph attributes.

    Args:
        component_id: Component identifier
        graph: NetworkX graph containing the component
        db_path: Optional database path (for consistency with other functions)

    Returns:
        Component dataclass with metadata

    Raises:
        ValueError: If component_id not found in graph
    """
    if component_id not in graph:
        raise ValueError(f"Component '{component_id}' not found in graph")

    attrs = graph.nodes[component_id]
    return Component(
        component_id=component_id,
        name=attrs.get("name", ""),
        file_path=attrs.get("file_path", ""),
        type=attrs.get("type", ""),
        lines=attrs.get("lines"),
        complexity_score=attrs.get("complexity_score"),
    )


@_timed
def get_dependencies(
    component_id: str,
    depth: int = 1,
    project_id: str | None = None,
    graph: nx.DiGraph | None = None,
    db_path: Path | None = None,
) -> List[Component]:
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
) -> List[Component]:
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
) -> List[List[Component]]:
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
def calculate_centrality(graph: nx.DiGraph) -> Dict[str, float]:
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
) -> List[Component]:
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


def clear_cache(project_id: str | None = None):
    """Clear the graph cache for a specific project or all projects.

    Args:
        project_id: Project to clear cache for. If None, clears all cached graphs.
    """
    _cached_builder.clear_cache(project_id)


@_timed
def detect_communities(graph: nx.DiGraph) -> Dict[str, int]:
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
def get_project_stats(project_id: str, db_path: Path | None = None) -> Dict[str, any]:
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


def graph_to_dict(graph: nx.DiGraph, limit: int | None = None, offset: int = 0) -> Dict[str, any]:
    """Convert NetworkX graph to dictionary format for API responses with pagination support.

    Args:
        graph: NetworkX DiGraph with component nodes and dependency edges
        limit: Maximum number of nodes to return (None = all nodes)
        offset: Number of nodes to skip for pagination (default: 0)

    Returns:
        Dictionary with paginated "nodes" and "edges" arrays matching API schema

    Example:
        >>> graph = build_graph("dream-studio")
        >>> data = graph_to_dict(graph, limit=100, offset=0)  # First 100 nodes
        >>> data = graph_to_dict(graph, limit=100, offset=100)  # Next 100 nodes
    """
    # Get all node IDs sorted for stable pagination
    all_node_ids = sorted(graph.nodes())

    # Apply pagination to nodes
    if limit is not None:
        paginated_node_ids = all_node_ids[offset : offset + limit]
    else:
        paginated_node_ids = all_node_ids[offset:]

    paginated_node_set = set(paginated_node_ids)

    # Convert nodes to dict format
    nodes = []
    for node_id in paginated_node_ids:
        attrs = graph.nodes[node_id]
        nodes.append(
            {
                "id": node_id,
                "name": attrs.get("name", ""),
                "component_type": attrs.get("type", ""),
                "path": attrs.get("file_path", ""),
                "lines": attrs.get("lines"),
                "complexity_score": attrs.get("complexity_score"),
                "incoming_edges": graph.in_degree(node_id),
                "outgoing_edges": graph.out_degree(node_id),
                "centrality_score": 0,  # Placeholder - can be computed separately
            }
        )

    # Convert edges - only include edges where BOTH nodes are in the paginated set
    edges = []
    for source, target in graph.edges():
        if source in paginated_node_set and target in paginated_node_set:
            edges.append(
                {
                    "source": source,
                    "target": target,
                    "dependency_type": "import",  # Default type
                    "strength": None,
                }
            )

    return {"nodes": nodes, "edges": edges}
