"""Internal discovery API routes for unified-discovery Phase 5.3

Provides REST endpoint for component dependency graphs.

Part of unified-discovery API Layer (FR-001).
"""

import logging
from fastapi import APIRouter, HTTPException, Query, Path as PathParam
from pydantic import BaseModel, Field

from core.graph import query as graph_query

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Pydantic Response Models ─────────────────────────────────────────────────


class GraphNode(BaseModel):
    """Graph node representing a component"""

    id: str
    name: str
    component_type: str
    path: str
    lines: int | None = None
    complexity_score: float | None = None
    incoming_edges: int = 0
    outgoing_edges: int = 0
    centrality_score: int = 0


class GraphEdge(BaseModel):
    """Graph edge representing a dependency"""

    source: str
    target: str
    dependency_type: str
    strength: float | None = None


class GraphResponse(BaseModel):
    """Full dependency graph response"""

    nodes: list[GraphNode]
    edges: list[GraphEdge]
    node_count: int = Field(description="Total number of nodes")
    edge_count: int = Field(description="Total number of edges")


# ── Helper Functions ──────────────────────────────────────────────────────────

from core.config.database import get_connection


def verify_project_exists(project_id: str) -> None:
    """Verify project exists, raise 404 if not"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT COUNT(*) as count FROM business_projects WHERE project_id = ?"
        result = cursor.execute(query, (project_id,)).fetchone()

        if result["count"] == 0:
            raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    finally:
        conn.close()


# ── API Endpoints ─────────────────────────────────────────────────────────────


@router.get(
    "/graph/{project_id}",
    response_model=GraphResponse,
    summary="Get dependency graph",
    description="Returns dependency graph with nodes and edges for a project (paginated)",
)
async def get_dependency_graph(
    project_id: str = PathParam(..., description="Project ID"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of nodes to return"),
    offset: int = Query(0, ge=0, description="Number of nodes to skip for pagination"),
) -> GraphResponse:
    """
    Get the dependency graph for a project with pagination support.

    Returns components as nodes and dependencies as edges.
    Includes centrality metrics for each node.

    **Pagination:**
    - Default limit: 1000 nodes
    - Use offset to fetch subsequent pages
    - Edges are filtered to only include edges between returned nodes

    **Performance:** p95 response time target <500ms

    **Example:**
    - First page: `GET /api/discovery/internal/graph/dream-studio?limit=100&offset=0`
    - Second page: `GET /api/discovery/internal/graph/dream-studio?limit=100&offset=100`
    """
    try:
        # Verify project exists
        verify_project_exists(project_id)

        # Build graph using graph_query library (cached)
        nx_graph = graph_query.build_graph(project_id)

        # Convert to dict format with pagination
        graph_data = graph_query.graph_to_dict(nx_graph, limit=limit, offset=offset)

        # Get total counts from full graph
        total_nodes = nx_graph.number_of_nodes()
        total_edges = nx_graph.number_of_edges()

        return GraphResponse(
            nodes=[GraphNode(**node) for node in graph_data["nodes"]],
            edges=[GraphEdge(**edge) for edge in graph_data["edges"]],
            node_count=total_nodes,
            edge_count=total_edges,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error building graph for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to build dependency graph: {str(e)}")
