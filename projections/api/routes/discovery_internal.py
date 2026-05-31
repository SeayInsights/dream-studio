"""Internal discovery API routes for unified-discovery Phase 5.3

Provides REST endpoints for component dependency graphs, impact analysis,
component listings, and project statistics.

Part of unified-discovery API Layer (FR-001).
"""

import logging
from fastapi import APIRouter, HTTPException, Query, Path as PathParam
from typing import Dict, Any, List, Optional
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
    lines: Optional[int] = None
    complexity_score: Optional[float] = None
    incoming_edges: int = 0
    outgoing_edges: int = 0
    centrality_score: int = 0


class GraphEdge(BaseModel):
    """Graph edge representing a dependency"""

    source: str
    target: str
    dependency_type: str
    strength: Optional[float] = None


class GraphResponse(BaseModel):
    """Full dependency graph response"""

    nodes: List[GraphNode]
    edges: List[GraphEdge]
    node_count: int = Field(description="Total number of nodes")
    edge_count: int = Field(description="Total number of edges")


class AffectedComponent(BaseModel):
    """Component affected by a change"""

    component_id: str
    name: str
    component_type: str
    path: str
    distance: int = Field(description="Hops from the changed component")


class ImpactResponse(BaseModel):
    """Impact analysis response"""

    component_id: str
    component_name: str
    depth: int = Field(description="Maximum depth traversed")
    total_affected: int = Field(description="Total affected components")
    direct_dependents: int = Field(description="Components directly depending on this")
    transitive_dependents: int = Field(description="Indirectly affected components")
    affected_components: List[AffectedComponent]
    critical_paths: List[List[str]] = Field(description="Critical dependency paths")


class Component(BaseModel):
    """Component listing entry"""

    component_id: str
    name: str
    component_type: str
    path: str
    lines: Optional[int] = None
    complexity_score: Optional[float] = None
    last_analyzed: Optional[str] = None


class ComponentListResponse(BaseModel):
    """Component listing response"""

    project_id: str
    components: List[Component]
    total: int
    filtered_by: Optional[str] = None


class StatsResponse(BaseModel):
    """Project statistics response"""

    project_id: str
    component_count: int
    dependency_count: int
    avg_centrality: float
    component_types: Dict[str, int] = Field(description="Breakdown by component type")


class Cycle(BaseModel):
    """A circular dependency cycle"""

    cycle_id: int = Field(description="Sequential cycle identifier (0-based)")
    component_ids: List[str] = Field(description="Component IDs forming the cycle")
    component_names: List[str] = Field(description="Component names forming the cycle")
    cycle_length: int = Field(description="Number of components in the cycle")


class CyclesResponse(BaseModel):
    """Cycle detection response"""

    project_id: str
    total_cycles: int = Field(description="Total number of cycles detected")
    cycles: List[Cycle] = Field(description="List of all cycles found")


class CommunityMapping(BaseModel):
    """Community detection response"""

    project_id: str
    communities: Dict[str, int] = Field(description="Mapping of component_id to community_id")
    community_count: int = Field(description="Total number of distinct communities")
    largest_community_size: int = Field(description="Size of largest community")


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


def verify_component_exists(component_id: str) -> None:
    """Verify component exists, raise 404 if not"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        query = "SELECT COUNT(*) as count FROM pi_components WHERE component_id = ?"
        result = cursor.execute(query, (component_id,)).fetchone()

        if result["count"] == 0:
            raise HTTPException(status_code=404, detail=f"Component {component_id} not found")
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


@router.get(
    "/impact/{component_id}",
    response_model=ImpactResponse,
    summary="Analyze component impact",
    description="Analyzes the impact of changes to a component by finding all dependents",
)
async def analyze_component_impact(
    component_id: str = PathParam(..., description="Component ID to analyze"),
    depth: int = Query(2, ge=1, le=5, description="Maximum traversal depth"),
) -> ImpactResponse:
    """
    Analyze the impact of changes to a component.

    Traverses the dependency graph to find all components that depend on this one,
    up to the specified depth. Returns direct and transitive dependents, along
    with critical dependency paths.

    **Performance:** p95 response time target <500ms

    **Parameters:**
    - **component_id**: ID of the component to analyze
    - **depth**: How many hops to traverse (default: 2, max: 5)
    """
    try:
        # Verify component exists
        verify_component_exists(component_id)

        # Analyze impact using graph_query library
        impact_report = graph_query.analyze_impact(component_id, depth)

        return ImpactResponse(
            component_id=impact_report.component_id,
            component_name=impact_report.component_name,
            depth=impact_report.depth,
            total_affected=impact_report.total_affected,
            direct_dependents=impact_report.direct_dependents,
            transitive_dependents=impact_report.transitive_dependents,
            affected_components=[
                AffectedComponent(**comp) for comp in impact_report.affected_components
            ],
            critical_paths=impact_report.critical_paths,
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing impact for component {component_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to analyze component impact: {str(e)}")


@router.get(
    "/components/{project_id}",
    response_model=ComponentListResponse,
    summary="List project components",
    description="Lists components in a project with optional type filtering and pagination",
)
async def list_components(
    project_id: str = PathParam(..., description="Project ID"),
    type: Optional[str] = Query(
        None,
        description="Filter by component type (module, class, function, component, route, api)",
    ),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of components to return"),
    offset: int = Query(0, ge=0, description="Number of components to skip for pagination"),
) -> ComponentListResponse:
    """
    List components for a project with pagination.

    Optionally filter by component type. Returns component metadata including
    complexity scores and analysis timestamps.

    **Pagination:**
    - Default limit: 100 components
    - Use offset to fetch subsequent pages
    - Total count includes all components (not just current page)

    **Parameters:**
    - **project_id**: ID of the project
    - **type**: Optional component type filter
    - **limit**: Maximum components per page (default: 100, max: 1000)
    - **offset**: Number of components to skip (default: 0)

    **Example:**
    - First page: `GET /api/discovery/internal/components/dream-studio?limit=100&offset=0`
    - Second page: `GET /api/discovery/internal/components/dream-studio?limit=100&offset=100`
    """
    try:
        # Verify project exists
        verify_project_exists(project_id)

        conn = get_connection()
        try:
            cursor = conn.cursor()

            # Build count query
            if type:
                count_query = """
                SELECT COUNT(*) as total
                FROM pi_components
                WHERE project_id = ? AND component_type = ?
                """
                count_params = (project_id, type)
            else:
                count_query = """
                SELECT COUNT(*) as total
                FROM pi_components
                WHERE project_id = ?
                """
                count_params = (project_id,)

            total_count = cursor.execute(count_query, count_params).fetchone()["total"]

            # Build paginated query
            if type:
                query = """
                SELECT
                    component_id,
                    name,
                    component_type,
                    path,
                    lines,
                    complexity_score,
                    last_analyzed
                FROM pi_components
                WHERE project_id = ? AND component_type = ?
                ORDER BY name
                LIMIT ? OFFSET ?
                """
                params = (project_id, type, limit, offset)
            else:
                query = """
                SELECT
                    component_id,
                    name,
                    component_type,
                    path,
                    lines,
                    complexity_score,
                    last_analyzed
                FROM pi_components
                WHERE project_id = ?
                ORDER BY name
                LIMIT ? OFFSET ?
                """
                params = (project_id, limit, offset)

            rows = cursor.execute(query, params).fetchall()

            components = [
                Component(
                    component_id=row["component_id"],
                    name=row["name"],
                    component_type=row["component_type"],
                    path=row["path"],
                    lines=row["lines"],
                    complexity_score=row["complexity_score"],
                    last_analyzed=row["last_analyzed"],
                )
                for row in rows
            ]

            return ComponentListResponse(
                project_id=project_id, components=components, total=total_count, filtered_by=type
            )

        finally:
            conn.close()

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing components for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list components: {str(e)}")


@router.get(
    "/stats/{project_id}",
    response_model=StatsResponse,
    summary="Get project statistics",
    description="Returns aggregate statistics about a project's dependency graph",
)
async def get_project_stats(
    project_id: str = PathParam(..., description="Project ID")
) -> StatsResponse:
    """
    Get aggregate statistics for a project.

    Returns component count, dependency count, average centrality score,
    and breakdown by component type.

    **Performance:** Fast aggregation using database views
    """
    try:
        # Verify project exists
        verify_project_exists(project_id)

        # Get stats using graph_query library
        stats = graph_query.get_project_stats(project_id)

        return StatsResponse(
            project_id=project_id,
            component_count=stats["component_count"],
            dependency_count=stats["dependency_count"],
            avg_centrality=stats["avg_centrality"],
            component_types=stats["component_types"],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting stats for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get project statistics: {str(e)}")


@router.get(
    "/cycles/{project_id}",
    response_model=CyclesResponse,
    summary="Detect circular dependencies",
    description="Detects all circular dependency cycles in a project's dependency graph",
)
async def detect_cycles(
    project_id: str = PathParam(..., description="Project ID")
) -> CyclesResponse:
    """
    Detect circular dependencies in the dependency graph.

    Uses NetworkX's simple_cycles algorithm to find all cycles.
    Cycles indicate architectural issues such as circular imports
    or tight coupling between components.

    **Performance:** Cycle detection is O(V+E) complexity.
    Results are cached along with the graph (5 min TTL).

    **Dashboard Integration:**
    - Cycles are highlighted with red edges in the graph visualization
    - Each cycle is numbered sequentially for reference

    **Example:**
    - `GET /api/discovery/internal/cycles/dream-studio`

    **Returns:**
    - List of all cycles found
    - Each cycle contains component IDs and names forming the circular path
    """
    try:
        # Verify project exists
        verify_project_exists(project_id)

        # Build graph and detect cycles
        nx_graph = graph_query.build_graph(project_id)
        cycles_components = graph_query.detect_cycles(graph=nx_graph)

        # Convert to response format
        cycles = []
        for cycle_idx, cycle_component_list in enumerate(cycles_components):
            cycle = Cycle(
                cycle_id=cycle_idx,
                component_ids=[c.component_id for c in cycle_component_list],
                component_names=[c.name for c in cycle_component_list],
                cycle_length=len(cycle_component_list),
            )
            cycles.append(cycle)

        return CyclesResponse(project_id=project_id, total_cycles=len(cycles), cycles=cycles)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error detecting cycles for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to detect cycles: {str(e)}")


@router.get(
    "/communities/{project_id}",
    response_model=CommunityMapping,
    summary="Detect communities in dependency graph",
    description="Groups components into communities using Louvain community detection",
)
async def detect_communities(
    project_id: str = PathParam(..., description="Project ID")
) -> CommunityMapping:
    """
    Detect communities (clusters) in the dependency graph.

    Communities represent groups of components that depend heavily on each other.
    This is useful for identifying architectural modules and understanding coupling.

    Uses the Louvain method for community detection, which optimizes modularity
    to find densely connected groups.

    **Performance:** Community detection is O(V log V) complexity.
    Results are computed on-demand and cached with the graph (5 min TTL).

    **Dashboard Integration:**
    - Each community is assigned a distinct color in graph visualization
    - Components in the same community are rendered with the same color
    - Community boundaries help visualize architectural layering

    **Example:**
    - `GET /api/discovery/internal/communities/dream-studio`

    **Returns:**
    - Mapping of component_id to community_id (integer)
    - Community count and largest community size for statistics
    """
    try:
        # Verify project exists
        verify_project_exists(project_id)

        # Build graph and detect communities
        nx_graph = graph_query.build_graph(project_id)
        community_mapping = graph_query.detect_communities(nx_graph)

        # Calculate statistics
        if community_mapping:
            community_count = len(set(community_mapping.values()))

            # Calculate largest community size
            from collections import Counter

            community_sizes = Counter(community_mapping.values())
            largest_community_size = max(community_sizes.values()) if community_sizes else 0
        else:
            community_count = 0
            largest_community_size = 0

        return CommunityMapping(
            project_id=project_id,
            communities=community_mapping,
            community_count=community_count,
            largest_community_size=largest_community_size,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error detecting communities for project {project_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to detect communities: {str(e)}")
