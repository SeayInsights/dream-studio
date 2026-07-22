"""Search execution and top-level research entry point for web research.

WO-GF-CONTROL-INSTALL-split: see web.py facade docstring.
"""

from __future__ import annotations

from datetime import datetime, UTC
import os

from .web_scoring import calculate_confidence, calculate_triangulation, summarize_findings
from .web_shared import ResearchReport, Source, _emit_metric


def search_jina(query: str) -> list[Source]:
    """Execute Jina Search API and return higher-tier sources.

    Args:
        query: Search query string

    Returns:
        List of Source objects with tier mapping from relevance scores
        Returns empty list if JINA_API_KEY not set

    Tier mapping:
        - relevance_score > 0.9: Tier 1
        - relevance_score 0.7-0.9: Tier 2
        - relevance_score < 0.7: Tier 3
    """
    api_key = os.environ.get("JINA_API_KEY")

    if not api_key:
        _emit_metric(
            "web_research.jina_skip",
            {"reason": "no_api_key", "timestamp": datetime.now(UTC).isoformat()},
        )
        return []

    try:
        import requests

        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

        payload = {"query": query, "limit": 10}

        response = requests.post(
            "https://api.jina.ai/v1/search", headers=headers, json=payload, timeout=5
        )

        response.raise_for_status()
        data = response.json()

        sources = []
        for result in data.get("results", []):
            url = result.get("url", "")
            title = result.get("title", "")
            snippet = result.get("snippet", "")
            relevance_score = result.get("relevance_score", 0.0)

            if not url or not title:
                continue

            # Map relevance_score to tier
            if relevance_score > 0.9:
                tier = 1
            elif relevance_score >= 0.7:
                tier = 2
            else:
                tier = 3

            sources.append(
                Source(
                    url=url,
                    title=title,
                    snippet=snippet,
                    tier=tier,
                    extraction_notes=snippet or "unavailable",
                )
            )

        _emit_metric(
            "web_research.jina_success",
            {
                "query": query,
                "result_count": len(sources),
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        return sources

    except Exception as e:
        _emit_metric(
            "web_research.jina_error",
            {"query": query, "error": str(e), "timestamp": datetime.now(UTC).isoformat()},
        )
        return []


def search_web(query: str, source: str = "websearch") -> list[Source]:
    """Execute web search and return parsed sources.

    Args:
        query: Search query string
        source: Search source ('websearch' or 'jina')

    Returns:
        List of Source objects
    """
    # For now, we'll use the WebSearch tool via the harness
    # This is a placeholder that needs integration with the actual tool
    # In production, this would call the WebSearch tool through the harness

    _emit_metric(
        "web_research.search",
        {"query": query, "source": source, "timestamp": datetime.now(UTC).isoformat()},
    )

    # Placeholder: In real implementation, this would invoke WebSearch tool
    # and parse the results into the expected format
    # For now, return empty list - integration with harness needed

    return []


def research_topic(topic: str, focus_areas: list[str]) -> ResearchReport:
    """Main entry point for web research with confidence scoring.

    Performs multi-source research, calculates confidence metrics,
    and returns a structured report.

    Prefers Jina Search if JINA_API_KEY is available, falls back to WebSearch.

    Args:
        topic: Main research topic
        focus_areas: List of specific areas to focus on

    Returns:
        ResearchReport with sources and metrics
    """
    start_time = datetime.now(UTC)

    # Build search query
    if focus_areas:
        query = f"{topic} {' '.join(focus_areas)}"
    else:
        query = topic

    # Execute search - prefer Jina if available
    sources = search_jina(query)
    search_source = "jina"

    # Fallback to WebSearch if Jina returned no results
    if not sources:
        sources = search_web(query)
        search_source = "websearch"

    # Calculate metrics
    confidence = calculate_confidence(sources)
    triangulation = calculate_triangulation(sources)

    # Generate summary
    findings = summarize_findings(sources)

    # Create report
    report = ResearchReport(
        topic=topic,
        sources=sources,
        findings=findings,
        confidence=confidence,
        triangulation=triangulation,
        cache_status="fresh",
        created_at=start_time.isoformat(),
    )

    # Emit metrics
    duration = (datetime.now(UTC) - start_time).total_seconds()
    _emit_metric(
        "web_research.complete",
        {
            "topic": topic,
            "source_count": len(sources),
            "confidence": confidence,
            "triangulation": triangulation,
            "duration_seconds": round(duration, 2),
            "search_source": search_source,
        },
    )

    return report


# Performance tracking
def _check_performance(func):
    """Decorator to ensure <10s performance for research operations."""

    def wrapper(*args, **kwargs):
        start = datetime.now(UTC)
        result = func(*args, **kwargs)
        duration = (datetime.now(UTC) - start).total_seconds()

        if duration > 10.0:
            _emit_metric(
                "web_research.slow",
                {
                    "function": func.__name__,
                    "duration_seconds": duration,
                    "warning": "exceeded_10s_target",
                },
            )

        return result

    return wrapper


# Apply performance tracking to main entry point
research_topic = _check_performance(research_topic)
