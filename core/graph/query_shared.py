"""Shared cache infrastructure, dataclasses, and cross-sibling helpers for the
graph query engine.

WO-GF-CORE-DATA-split: implementation split from core/graph/query.py into
query_{shared,traversal,analysis,io}.py; core/graph/query.py is now a thin
facade re-exporting the public API.
"""

from __future__ import annotations
import logging
import time
from pathlib import Path
from dataclasses import dataclass
from functools import wraps

try:
    import networkx as nx
except ImportError:
    raise ImportError("NetworkX is required. Install with: pip install networkx")

from core.event_store.studio_db import _connect

# Configure logging
logger = logging.getLogger("core.graph.query")

# Cache configuration
CACHE_TTL_SECONDS = 300  # 5 minutes
_graph_cache: dict[str, tuple[nx.DiGraph, float]] = {}


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
        self._cache: dict[str, tuple[nx.DiGraph, float, str]] = (
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

    def get_cache_stats(self) -> dict[str, int]:
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
    lines: int | None = None
    complexity_score: float | None = None


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
    affected_components: list[Component]
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
