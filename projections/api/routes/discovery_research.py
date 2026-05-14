"""
Research API Routes for Unified Discovery System
Created: 2026-05-06
Purpose: FastAPI endpoints for web research with caching (T138, Phase 7)
"""

import logging
import time
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Path as PathParam
from pydantic import BaseModel, Field

from control.research import web as web_research

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter()


# ============================================================================
# PYDANTIC MODELS
# ============================================================================


class SourceModel(BaseModel):
    """Source metadata with quality tier."""

    url: str = Field(..., description="Source URL")
    title: str = Field(..., description="Source title")
    snippet: str = Field(..., description="Source snippet/summary")
    tier: int = Field(..., ge=1, le=3, description="Source quality tier (1=highest)")
    source_type: str = Field("unknown", description="Source type classification")
    accessed_at: str = Field("unknown", description="When the source was accessed")
    extraction_notes: str = Field("unavailable", description="Extracted notes from source")
    verification_status: str = Field("unverified", description="Source verification posture")


class ResearchReportResponse(BaseModel):
    """Complete research report with confidence metrics."""

    topic: str = Field(..., description="Research topic")
    sources: List[SourceModel] = Field(default_factory=list, description="Research sources")
    findings: str = Field(..., description="Markdown-formatted findings summary")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score (0.0-1.0)")
    triangulation: float = Field(..., ge=0.0, le=1.0, description="Triangulation score (0.0-1.0)")
    cache_id: Optional[str] = Field(None, description="Cache ID if cached")
    verification_status: str = Field("unverified", description="Report verification posture")
    cache_status: str = Field("not_cached", description="Research cache status")
    privacy_export_classification: str = Field(
        "local_only",
        description="Privacy/export classification for this advisory artifact",
    )
    created_at: str = Field("unknown", description="Report creation timestamp")


class ResearchRequest(BaseModel):
    """Request body for triggering research."""

    topic: str = Field(..., min_length=1, description="Main research topic")
    focus_areas: List[str] = Field(default_factory=list, description="Specific focus areas")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================


def _load_by_cache_id(cache_id: str) -> Optional[web_research.ResearchReport]:
    """Load research report from cache by cache_id.

    Args:
        cache_id: Cache ID to lookup

    Returns:
        ResearchReport if found and not expired, None otherwise
    """
    from core.event_store.studio_db import _connect
    from datetime import datetime, timezone
    import json

    with _connect() as c:
        row = c.execute(
            """
            SELECT topic, sources, findings, confidence_score, triangulation_score
            FROM research_cache
            WHERE cache_id = ? AND expires_at > datetime('now')
        """,
            (cache_id,),
        ).fetchone()

        if not row:
            return None

        # Deserialize sources
        sources_data = json.loads(row[1])
        sources = [web_research._source_from_cache_dict(s) for s in sources_data]

        return web_research.ResearchReport(
            topic=row[0],
            sources=sources,
            findings=row[2],
            confidence=row[3],
            triangulation=row[4],
            cache_status="cached",
        )


def _invalidate_by_cache_id(cache_id: str) -> bool:
    """Invalidate cache by cache_id.

    Args:
        cache_id: Cache ID to invalidate

    Returns:
        True if cache entry was deleted, False if not found
    """
    from core.event_store.studio_db import _connect

    with _connect() as c:
        rows_deleted = c.execute(
            "DELETE FROM research_cache WHERE cache_id = ?", (cache_id,)
        ).rowcount

    return rows_deleted > 0


def _get_cache_id_for_topic(topic: str) -> Optional[str]:
    """Get cache_id for a topic if it exists and is not expired.

    Args:
        topic: Research topic

    Returns:
        cache_id if found, None otherwise
    """
    from core.event_store.studio_db import _connect

    if not topic or not topic.strip():
        return None

    topic_key = topic.strip().lower()

    with _connect() as c:
        row = c.execute(
            """
            SELECT cache_id
            FROM research_cache
            WHERE topic = ? AND expires_at > datetime('now')
        """,
            (topic_key,),
        ).fetchone()

        return row[0] if row else None


def _report_to_response(
    report: web_research.ResearchReport, cache_id: Optional[str] = None
) -> ResearchReportResponse:
    """Convert ResearchReport to API response model.

    Args:
        report: ResearchReport from web_research module
        cache_id: Optional cache_id to include

    Returns:
        ResearchReportResponse
    """
    return ResearchReportResponse(
        topic=report.topic,
        sources=[
            SourceModel(
                url=s.url,
                title=s.title,
                snippet=s.snippet,
                tier=s.tier,
                source_type=s.source_type,
                accessed_at=s.accessed_at,
                extraction_notes=s.extraction_notes,
                verification_status=s.verification_status,
            )
            for s in report.sources
        ],
        findings=report.findings,
        confidence=report.confidence,
        triangulation=report.triangulation,
        cache_id=cache_id,
        verification_status=report.verification_status,
        cache_status=report.cache_status,
        privacy_export_classification=report.privacy_export_classification,
        created_at=report.created_at,
    )


# ============================================================================
# ENDPOINTS
# ============================================================================


@router.post("/api/discovery/research", response_model=ResearchReportResponse)
async def trigger_research(request: ResearchRequest) -> ResearchReportResponse:
    """
    Trigger web research on a topic with confidence scoring and source triangulation.

    **Performance target:** <10s for full research

    **Process:**
    1. Check cache for existing research
    2. If not cached, execute web search across multiple sources
    3. Calculate confidence score based on source quality (tier 1-3)
    4. Calculate triangulation score based on source count
    5. Generate markdown findings summary
    6. Cache results with 30-day TTL

    **Source Tiers:**
    - **Tier 1 (1.0x weight):** Official docs, GitHub repos, readthedocs
    - **Tier 2 (0.6x weight):** Technical blogs, Medium, dev.to
    - **Tier 3 (0.3x weight):** Forums, Stack Overflow, Reddit

    **Confidence Scoring:**
    - Based on weighted source count by tier
    - Range: 0.0-1.0 (higher = better source quality)

    **Triangulation Scoring:**
    - Based on number of independent sources
    - 3+ sources = 1.0 (full triangulation)
    - 2 sources = 0.67
    - 1 source = 0.33

    **Example:**
    ```json
    POST /api/discovery/research
    {
        "topic": "FastAPI async performance",
        "focus_areas": ["benchmarks", "best practices"]
    }
    ```

    Returns cached report if available, otherwise performs fresh research.
    """
    start_time = time.time()

    # Validate request
    if not request.topic.strip():
        raise HTTPException(status_code=400, detail="Topic cannot be empty")

    try:
        # Check cache first
        cached_report = web_research.load_from_cache(request.topic)

        if cached_report:
            cache_id = _get_cache_id_for_topic(request.topic)
            execution_time_ms = (time.time() - start_time) * 1000

            logger.info(
                f"Research cache hit: topic='{request.topic}', "
                f"sources={len(cached_report.sources)}, "
                f"time={execution_time_ms:.1f}ms"
            )

            return _report_to_response(cached_report, cache_id)

        # Execute research
        report = web_research.research_topic(topic=request.topic, focus_areas=request.focus_areas)

        # Cache the results
        web_research.save_to_cache(
            topic=request.topic,
            report=report,
            ttl_days=30,
            emit_events=False,
        )

        # Get cache_id for response
        cache_id = _get_cache_id_for_topic(request.topic)

        execution_time_ms = (time.time() - start_time) * 1000

        logger.info(
            f"Research completed: topic='{request.topic}', "
            f"sources={len(report.sources)}, "
            f"confidence={report.confidence}, "
            f"triangulation={report.triangulation}, "
            f"time={execution_time_ms:.1f}ms"
        )

        return _report_to_response(report, cache_id)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Research failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Research failed: {str(e)}")


@router.get("/api/discovery/research/{cache_id}", response_model=ResearchReportResponse)
async def get_cached_research_by_id(
    cache_id: str = PathParam(..., description="Cache ID from previous research")
) -> ResearchReportResponse:
    """
    Retrieve cached research report by cache_id.

    **Performance target:** <50ms

    **Cache ID format:** 16-character hex string (SHA256 hash of topic)

    **Expiration:** Reports expire after 30 days

    **Example:**
    ```
    GET /api/discovery/research/a1b2c3d4e5f6g7h8
    ```

    Returns cached report if found and not expired.

    **Errors:**
    - `404 Not Found`: Cache ID not found or expired
    """
    try:
        report = _load_by_cache_id(cache_id)

        if not report:
            raise HTTPException(status_code=404, detail=f"Cached research not found: {cache_id}")

        logger.info(f"Cache retrieval by ID: {cache_id}")

        return _report_to_response(report, cache_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve cached research {cache_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve research: {str(e)}")


@router.get("/api/discovery/research", response_model=ResearchReportResponse)
async def get_cached_research_by_topic(
    topic: str = Query(..., min_length=1, description="Research topic to lookup")
) -> ResearchReportResponse:
    """
    Check if cached research exists for a topic.

    **Performance target:** <50ms

    **Topic matching:** Case-insensitive, whitespace normalized

    **Example:**
    ```
    GET /api/discovery/research?topic=FastAPI%20async%20performance
    ```

    Returns cached report if found and not expired.

    **Errors:**
    - `404 Not Found`: No cached research found for topic
    """
    try:
        report = web_research.load_from_cache(topic)

        if not report:
            raise HTTPException(
                status_code=404, detail=f"No cached research found for topic: {topic}"
            )

        cache_id = _get_cache_id_for_topic(topic)

        logger.info(f"Cache retrieval by topic: {topic}")

        return _report_to_response(report, cache_id)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve cached research for topic '{topic}': {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve research: {str(e)}")


@router.delete("/api/discovery/research/{cache_id}", status_code=204)
async def invalidate_cached_research(
    cache_id: str = PathParam(..., description="Cache ID to invalidate")
) -> None:
    """
    Invalidate (delete) cached research by cache_id.

    **Use cases:**
    - Force fresh research on next request
    - Remove stale/incorrect research
    - Clean up cache manually

    **Example:**
    ```
    DELETE /api/discovery/research/a1b2c3d4e5f6g7h8
    ```

    Returns 204 No Content on success (even if cache_id not found).

    **Note:** Idempotent - calling multiple times is safe.
    """
    try:
        deleted = _invalidate_by_cache_id(cache_id)

        if deleted:
            logger.info(f"Cache invalidated: {cache_id}")
        else:
            logger.info(f"Cache invalidation (not found): {cache_id}")

        # Always return 204, even if not found (idempotent)
        return None

    except Exception as e:
        logger.error(f"Failed to invalidate cache {cache_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to invalidate cache: {str(e)}")
