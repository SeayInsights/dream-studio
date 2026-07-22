"""NetworkX graph builder and query engine for project dependency analysis —
facade over the split modules.

WO-GF-CORE-DATA-split: implementation moved to query_{shared,traversal,
analysis,io}.py; this module re-exports the public API so existing
`from core.graph.query import X` callers are unchanged.

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

from .query_shared import (
    CACHE_TTL_SECONDS,
    CachedGraphBuilder,
    Component,
    ImpactReport,
    _cache_key,
    _cached_builder,
    _clear_expired_cache,
    _get_component_details,
    _graph_cache,
    _timed,
    logger,
)
from .query_traversal import (
    build_graph,
    get_dependencies,
    get_dependents,
)
from .query_analysis import (
    analyze_impact,
    calculate_centrality,
    detect_communities,
    detect_cycles,
    shortest_path,
    get_project_stats,
)
from .query_io import (
    clear_cache,
    graph_to_dict,
)

__all__ = [
    "CACHE_TTL_SECONDS",
    "CachedGraphBuilder",
    "Component",
    "ImpactReport",
    "_cache_key",
    "_cached_builder",
    "_clear_expired_cache",
    "_get_component_details",
    "_graph_cache",
    "_timed",
    "analyze_impact",
    "build_graph",
    "calculate_centrality",
    "clear_cache",
    "detect_communities",
    "detect_cycles",
    "get_dependencies",
    "get_dependents",
    "get_project_stats",
    "graph_to_dict",
    "logger",
    "shortest_path",
]
