"""API routes for /api/discovery/research — trigger, cache lookup, and invalidation."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, HTTPException, Query, Path as PathParam
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from control.research import web as web_research

router = APIRouter()


class ResearchRequest(BaseModel):
    topic: str
    focus_areas: List[str] = []

    @field_validator("topic")
    @classmethod
    def topic_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("topic must not be empty")
        return v


def _report_to_dict(report: web_research.ResearchReport) -> dict:
    return {
        "topic": report.topic,
        "sources": [
            {"url": s.url, "title": s.title, "snippet": s.snippet, "tier": s.tier}
            for s in report.sources
        ],
        "findings": report.findings,
        "confidence": report.confidence,
        "triangulation": report.triangulation,
    }


@router.post("")
async def trigger_research(req: ResearchRequest) -> dict:
    """Trigger web research or return cached result."""
    cached = web_research.load_from_cache(req.topic)
    if cached is not None:
        return _report_to_dict(cached)
    report = web_research.research_topic(req.topic, req.focus_areas)
    web_research.save_to_cache(req.topic, report, emit_events=False)
    return _report_to_dict(report)


@router.get("")
async def get_cached_by_topic(topic: str = Query(...)) -> dict:
    """Return cached research report for a topic."""
    report = web_research.load_from_cache(topic)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No cached research for: {topic}")
    return _report_to_dict(report)


@router.get("/{cache_id}")
async def get_cached_by_id(cache_id: str = PathParam(...)) -> dict:
    """Return cached research report by cache_id."""
    report = web_research.load_from_cache_by_id(cache_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Cache entry not found: {cache_id}")
    data = _report_to_dict(report)
    data["cache_id"] = cache_id
    return data


@router.delete("/{cache_id}", status_code=204)
async def invalidate_by_id(cache_id: str = PathParam(...)) -> Response:
    """Remove cache entry by cache_id. Idempotent."""
    web_research.delete_from_cache_by_id(cache_id)
    return Response(status_code=204)
