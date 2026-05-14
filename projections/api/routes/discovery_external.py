"""
External Discovery API Routes
Created: 2026-05-05
Purpose: FastAPI endpoints for tool search and retrieval (T115)
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from control.research import tools as tool_search

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class ToolSearchResult(BaseModel):
    """Single tool search result."""

    tool_id: str = Field(..., description="Unique tool identifier")
    name: str = Field(..., description="Tool name")
    category: str = Field(..., description="Tool category (mcp, python_package, api, saas)")
    description: str = Field(..., description="Tool description")
    source_url: str = Field(..., description="Source URL or repository")
    install_command: str = Field(..., description="Installation command")
    tags: list[str] = Field(default_factory=list, description="Tool tags")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    match_reason: str = Field(..., description="Why this tool was matched")


class ToolSearchResponse(BaseModel):
    """Response for tool search endpoint."""

    query: str = Field(..., description="Original search query")
    category: Optional[str] = Field(None, description="Category filter applied")
    total_results: int = Field(..., description="Number of results returned")
    tools: list[ToolSearchResult] = Field(default_factory=list, description="Matched tools")
    execution_time_ms: float = Field(..., description="Query execution time in milliseconds")


class ToolDetailResponse(BaseModel):
    """Response for tool detail endpoint."""

    tool_id: str = Field(..., description="Unique tool identifier")
    name: str = Field(..., description="Tool name")
    category: str = Field(..., description="Tool category")
    description: str = Field(..., description="Tool description")
    source_url: str = Field(..., description="Source URL or repository")
    install_command: str = Field(..., description="Installation command")
    tags: list[str] = Field(default_factory=list, description="Tool tags")
    confidence_score: float = Field(..., ge=0.0, le=1.0, description="Base confidence score")


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/api/discovery/external/tools", response_model=ToolSearchResponse)
async def search_external_tools(
    query: str = Query(..., min_length=1, description="Search query string"),
    top_k: int = Query(10, ge=1, le=100, description="Maximum number of results per page"),
    category: Optional[str] = Query(
        None, pattern="^(mcp|python_package|api|saas)$", description="Category filter"
    ),
    offset: int = Query(0, ge=0, description="Number of results to skip for pagination"),
) -> ToolSearchResponse:
    """
    Search for external tools matching query with pagination.

    **Performance target:** <200ms

    **Pagination:**
    - Default limit: 10 results per page
    - Use offset to skip results for subsequent pages
    - Returns total_results count for all matches

    **Query matching:**
    - Exact name match (highest priority)
    - Partial name match
    - Description match
    - Tag match
    - Word-level matching

    **Scoring:**
    - Combines match relevance (70%) + base confidence (30%)
    - Results sorted by confidence score descending

    **Category filters:**
    - `mcp`: MCP Server (Model Context Protocol)
    - `python_package`: Python Package (PyPI)
    - `api`: External API Service
    - `saas`: SaaS Platform

    **Example:**
    ```
    POST /api/discovery/external/tools?query=video&category=python_package&top_k=10&offset=0
    POST /api/discovery/external/tools?query=video&category=python_package&top_k=10&offset=10
    ```

    Returns paginated Python packages related to video processing.
    """
    import time

    start_time = time.time()

    # Validate query
    if not query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    try:
        # Execute search with higher top_k to get more results for pagination
        # Fetch up to offset + top_k + 20 to ensure we have enough results
        search_limit = offset + top_k + 20

        matches = tool_search.search_tools(query=query, top_k=search_limit, category=category)

        # Store total count before pagination
        total_results = len(matches)

        # Apply pagination
        paginated_matches = matches[offset : offset + top_k]

        # Convert to response format — ToolMatch uses .confidence, not .confidence_score
        tools = [
            ToolSearchResult(
                tool_id=match.tool_id,
                name=match.name,
                category=match.category,
                description=match.description,
                source_url=match.source_url,
                install_command=match.install_command,
                tags=[],
                confidence_score=match.confidence,
                match_reason="TF-IDF similarity match",
            )
            for match in paginated_matches
        ]

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Tool search: query='{query}', category={category}, "
            f"offset={offset}, top_k={top_k}, total_results={total_results}, "
            f"returned={len(tools)}, time={execution_time_ms:.1f}ms"
        )

        return ToolSearchResponse(
            query=query,
            category=category,
            total_results=total_results,
            tools=tools,
            execution_time_ms=round(execution_time_ms, 2),
        )

    except Exception as e:
        logger.error(f"Tool search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/api/discovery/external/tools/{tool_id}", response_model=ToolDetailResponse)
async def get_tool_details(tool_id: str) -> ToolDetailResponse:
    """
    Get detailed information for a specific tool.

    **Tool ID format:** `category:slug`

    **Examples:**
    - `mcp:firecrawl`
    - `python_package:opencv-python`
    - `api:openai`
    - `saas:notion`

    **Response:**
    - Full tool metadata
    - Installation command
    - Tags and confidence score

    **Errors:**
    - `404 Not Found`: Tool ID does not exist in registry
    """
    try:
        # Query tool by ID
        tool = tool_search.get_tool_by_id(tool_id)

        if not tool:
            raise HTTPException(status_code=404, detail=f"Tool not found: {tool_id}")

        logger.info(f"Tool detail retrieved: {tool_id}")

        return ToolDetailResponse(
            tool_id=tool.tool_id,
            name=tool.name,
            category=tool.category,
            description=tool.description,
            source_url=tool.source_url,
            install_command=tool.install_command,
            tags=tool.tags,
            confidence_score=tool.confidence_score,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve tool {tool_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve tool: {str(e)}")


@router.get("/api/discovery/external/health")
async def health_check() -> dict:
    """
    Health check for discovery service.

    Returns database connectivity status and tool count.
    """
    try:
        from core.config.database import get_connection, get_db_path

        if not get_db_path().exists():
            return {"status": "degraded", "database": "not_found", "tool_count": 0}

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tool_registry")
        count = cursor.fetchone()[0]
        conn.close()

        return {"status": "healthy", "database": "connected", "tool_count": count}

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {"status": "unhealthy", "error": str(e)}
