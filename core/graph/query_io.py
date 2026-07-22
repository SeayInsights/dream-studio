"""Cache control and dict-serialization for API responses.

WO-GF-CORE-DATA-split: split from core/graph/query.py — see query_shared.py
for the module-level split rationale.
"""

from __future__ import annotations

import networkx as nx

from .query_shared import _cached_builder


def clear_cache(project_id: str | None = None):
    """Clear the graph cache for a specific project or all projects.

    Args:
        project_id: Project to clear cache for. If None, clears all cached graphs.
    """
    _cached_builder.clear_cache(project_id)


def graph_to_dict(graph: nx.DiGraph, limit: int | None = None, offset: int = 0) -> dict[str, any]:
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
