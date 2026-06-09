"""Web research module with confidence scoring and source triangulation.

Provides multi-source research capabilities with tier-based trust scoring.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime, timezone, timedelta
import json
import sys
import os
from pathlib import Path

# Add hooks dir to path for imports
hooks_dir = Path(__file__).parent.parent
if str(hooks_dir) not in sys.path:
    sys.path.insert(0, str(hooks_dir))

from core.config.database import transaction, get_connection

from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType as CanonicalEventType
from emitters.shared.spool_writer import write_envelopes


def _emit_metric(event: str, data: dict) -> None:
    """Emit telemetry metric to raw_metrics table if it exists.

    Args:
        event: Event name (e.g., "web_research.search")
        data: Event data dict
    """
    try:
        metric = {"event": event, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()}
        metric_json = json.dumps(metric)

        with transaction() as c:
            # Check if raw_metrics table exists
            table_exists = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='raw_metrics'"
            ).fetchone()

            if table_exists:
                # EXEMPTION CANDIDATE: raw_metrics writes are infrastructure telemetry, not business state
                c.execute("INSERT INTO raw_metrics (metric_json) VALUES (?)", (metric_json,))
    except Exception:
        # Silently fail - metrics are best-effort
        pass


@dataclass
class Source:
    """Represents a single research source with quality tier.

    Tier 1: Official docs, GitHub repos, readthedocs
    Tier 2: Technical blogs, Medium, dev.to
    Tier 3: Forums, Stack Overflow, Reddit
    """

    url: str
    title: str
    snippet: str
    tier: int
    source_type: str = "unknown"
    accessed_at: str = "unknown"
    extraction_notes: str = "unavailable"
    verification_status: str = "unverified"


@dataclass
class ResearchReport:
    """Complete research report with confidence metrics."""

    topic: str
    sources: List[Source]
    findings: str
    confidence: float
    triangulation: float
    verification_status: str = "unverified"
    cache_status: str = "not_cached"
    privacy_export_classification: str = "local_only"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def _source_to_cache_dict(source: Source) -> dict:
    """Serialize source metadata with Phase 12 compatibility fields."""
    return {
        "url": source.url,
        "title": source.title,
        "snippet": source.snippet,
        "tier": source.tier,
        "source_type": source.source_type,
        "accessed_at": source.accessed_at,
        "extraction_notes": source.extraction_notes,
        "verification_status": source.verification_status,
    }


def _source_from_cache_dict(data: dict) -> Source:
    """Deserialize legacy or Phase 12 source metadata."""
    snippet = data.get("snippet", "")
    return Source(
        url=data["url"],
        title=data["title"],
        snippet=snippet,
        tier=data["tier"],
        source_type=data.get("source_type", "unknown"),
        accessed_at=data.get("accessed_at", "unknown"),
        extraction_notes=data.get("extraction_notes") or snippet or "unavailable",
        verification_status=data.get("verification_status", "unverified"),
    )


def _get_source_tier(url: str) -> int:
    """Determine source quality tier based on domain.

    Args:
        url: Source URL

    Returns:
        Tier level (1-3, lower is higher quality)
    """
    url_lower = url.lower()

    # Tier 1: Official documentation and primary sources
    tier1_domains = [
        "github.com",
        "readthedocs.io",
        "readthedocs.org",
        "python.org",
        "nodejs.org",
        "docs.microsoft.com",
        "developer.mozilla.org",
        "w3.org",
        "ietf.org",
        "npmjs.com",
        "pypi.org",
        "crates.io",
        "golang.org",
        "rust-lang.org",
        "kotlinlang.org",
        "swift.org",
        "apache.org",
        "eclipse.org",
        "kubernetes.io",
    ]

    # Tier 2: Technical blogs and curated content
    tier2_domains = [
        "medium.com",
        "dev.to",
        "hashnode.dev",
        "blog.",
        "engineering.",
        "tech.",
        "martinfowler.com",
        "overreacted.io",
        "smashingmagazine.com",
        "css-tricks.com",
        "freecodecamp.org",
        "digitalocean.com/community",
    ]

    # Tier 3: Forums and Q&A sites
    tier3_domains = [
        "stackoverflow.com",
        "stackexchange.com",
        "reddit.com",
        "discord.com",
        "discourse.org",
        "discuss.",
        "community.",
        "forum.",
    ]

    for domain in tier1_domains:
        if domain in url_lower:
            return 1

    for domain in tier2_domains:
        if domain in url_lower:
            return 2

    for domain in tier3_domains:
        if domain in url_lower:
            return 3

    # Default to tier 2 for unknown domains
    return 2


def extract_sources(search_results: List[dict]) -> List[Source]:
    """Parse search results into Source objects with tier classification.

    Args:
        search_results: List of dicts with 'url', 'title', 'snippet' keys

    Returns:
        List of Source objects with tier assignments
    """
    sources = []

    for result in search_results:
        url = result.get("url", "")
        title = result.get("title", "")
        snippet = result.get("snippet", "")

        if not url or not title:
            continue

        tier = _get_source_tier(url)
        sources.append(
            Source(
                url=url,
                title=title,
                snippet=snippet,
                tier=tier,
                extraction_notes=snippet or "unavailable",
            )
        )

    return sources


def calculate_confidence(sources: List[Source]) -> float:
    """Calculate confidence score based on source quality and count.

    Formula: (tier1_weight * count1 + tier2_weight * count2 + tier3_weight * count3) / max_possible

    Args:
        sources: List of Source objects

    Returns:
        Confidence score between 0.0 and 1.0
    """
    if not sources:
        return 0.0

    # Weights by tier (tier 1 = highest weight)
    tier_weights = {1: 1.0, 2: 0.6, 3: 0.3}

    # Count sources by tier
    tier_counts = {1: 0, 2: 0, 3: 0}
    for source in sources:
        tier_counts[source.tier] = tier_counts.get(source.tier, 0) + 1

    # Calculate weighted score
    weighted_sum = sum(tier_counts[tier] * tier_weights[tier] for tier in tier_counts)

    # Max possible score for this many sources (all tier 1)
    max_score = len(sources) * tier_weights[1]

    # Normalize to 0-1
    confidence = min(weighted_sum / max_score, 1.0) if max_score > 0 else 0.0

    return round(confidence, 2)


def calculate_triangulation(sources: List[Source]) -> float:
    """Calculate source triangulation score based on independent agreement.

    Triangulation improves with more sources (need 3+ for full confidence).

    Args:
        sources: List of Source objects

    Returns:
        Triangulation score between 0.0 and 1.0
    """
    if not sources:
        return 0.0

    # Need at least 3 sources for 1.0 triangulation
    triangulation = min(len(sources) / 3.0, 1.0)

    return round(triangulation, 2)


def summarize_findings(sources: List[Source]) -> str:
    """Generate markdown summary of research findings.

    Args:
        sources: List of Source objects

    Returns:
        Markdown formatted summary string
    """
    if not sources:
        return "No sources found."

    # Group sources by tier
    by_tier = {1: [], 2: [], 3: []}
    for source in sources:
        by_tier[source.tier].append(source)

    lines = ["## Research Findings\n"]

    tier_labels = {
        1: "Primary Sources (Tier 1)",
        2: "Technical Content (Tier 2)",
        3: "Community Discussion (Tier 3)",
    }

    for tier in [1, 2, 3]:
        tier_sources = by_tier[tier]
        if not tier_sources:
            continue

        lines.append(f"\n### {tier_labels[tier]}\n")

        for source in tier_sources:
            lines.append(f"- **[{source.title}]({source.url})**")
            if source.snippet:
                # Clean and truncate snippet
                snippet = source.snippet.replace("\n", " ").strip()
                if len(snippet) > 200:
                    snippet = snippet[:197] + "..."
                lines.append(f"  {snippet}\n")

    return "\n".join(lines)


def search_jina(query: str) -> List[Source]:
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
            {"reason": "no_api_key", "timestamp": datetime.now(timezone.utc).isoformat()},
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return sources

    except Exception as e:
        _emit_metric(
            "web_research.jina_error",
            {"query": query, "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()},
        )
        return []


def search_web(query: str, source: str = "websearch") -> List[Source]:
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
        {"query": query, "source": source, "timestamp": datetime.now(timezone.utc).isoformat()},
    )

    # Placeholder: In real implementation, this would invoke WebSearch tool
    # and parse the results into the expected format
    # For now, return empty list - integration with harness needed

    return []


def research_topic(topic: str, focus_areas: List[str]) -> ResearchReport:
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
    start_time = datetime.now(timezone.utc)

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
    duration = (datetime.now(timezone.utc) - start_time).total_seconds()
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
        start = datetime.now(timezone.utc)
        result = func(*args, **kwargs)
        duration = (datetime.now(timezone.utc) - start).total_seconds()

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


# ============================================================================
# Research Caching Layer
# ============================================================================


def save_to_cache(
    topic: str,
    report: ResearchReport,
    ttl_days: int = 30,
    *,
    emit_events: bool = True,
) -> None:
    """Save research report to cache with TTL.

    Args:
        topic: Research topic (used as cache key)
        report: ResearchReport to cache
        ttl_days: Time-to-live in days (default: 30 for technical, 7 for market)
        emit_events: Emit canonical research cache events when True. API projection
            routes pass False so advisory cache mutation does not become hidden
            dashboard authority.

    Raises:
        ValueError: If topic is empty or ttl_days is negative
    """
    if not topic or not topic.strip():
        raise ValueError("Topic cannot be empty")
    if ttl_days < 0:
        raise ValueError("TTL days must be non-negative")

    topic_key = topic.strip().lower()
    expires_at = datetime.now(timezone.utc) + timedelta(days=ttl_days)

    # Serialize sources to JSON
    sources_json = json.dumps([_source_to_cache_dict(s) for s in report.sources])

    with transaction() as c:
        if emit_events:
            # Slice 3: Emit event via spool pipeline
            write_envelopes(
                [
                    CanonicalEventEnvelope(
                        event_type=CanonicalEventType.RESEARCH_CACHE_CLEARED.value,
                        session_id=None,
                        payload={"topic": topic_key},
                        confidence="unavailable",
                        project_id=None,
                    )
                ]
            )

        # Delete existing entry if present, then insert new one
        c.execute("DELETE FROM research_cache WHERE topic = ?", (topic_key,))

        # Generate cache_id from topic
        import hashlib

        cache_id = hashlib.sha256(topic_key.encode()).hexdigest()[:16]

        if emit_events:
            # Slice 3: Emit event via spool pipeline
            write_envelopes(
                [
                    CanonicalEventEnvelope(
                        event_type=CanonicalEventType.RESEARCH_CACHE_STORED.value,
                        session_id=None,
                        payload={
                            "cache_id": cache_id,
                            "topic": topic_key,
                            "source_count": len(report.sources),
                            "confidence_score": report.confidence,
                            "triangulation_score": report.triangulation,
                            "ttl_days": ttl_days,
                        },
                        confidence="unavailable",
                        project_id=None,
                    )
                ]
            )

        c.execute(
            """
            INSERT INTO research_cache (
                cache_id,
                topic,
                focus_areas,
                sources,
                findings,
                confidence_score,
                triangulation_score,
                created_at,
                expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'), ?)
        """,
            (
                cache_id,
                topic_key,
                json.dumps([]),  # focus_areas stored empty for now
                sources_json,
                report.findings,
                report.confidence,
                report.triangulation,
                expires_at.isoformat(),
            ),
        )

    _emit_research_cache_telemetry(topic_key, report, cache_id, ttl_days)
    _emit_metric(
        "web_research.cache_save",
        {
            "topic": topic,
            "source_count": len(report.sources),
            "ttl_days": ttl_days,
            "expires_at": expires_at.isoformat(),
        },
    )


def _emit_research_cache_telemetry(
    topic_key: str,
    report: ResearchReport,
    cache_id: str,
    ttl_days: int,
) -> None:
    """Best-effort dual-write from the SQLite research cache."""

    try:
        from core.telemetry.emitters import TelemetryContext, emit_research_evidence_record

        sources = [_source_to_cache_dict(source) for source in report.sources]
        emit_research_evidence_record(
            question=topic_key,
            decision_class="research_allowed",
            confidence=report.confidence,
            sources=sources,
            source_summary=report.findings,
            decision_impact="research_cache_saved",
            operator_verification_required=report.confidence < 0.6,
            research_id=f"research-cache-{cache_id}",
            context=TelemetryContext(
                project_id="dream-studio",
                source_refs=("control/research/web.py",),
                evidence_refs=(f"research_cache:{cache_id}",),
            ),
            metadata={"triangulation": report.triangulation, "ttl_days": ttl_days},
        )
    except Exception:
        return


def load_from_cache(topic: str) -> Optional[ResearchReport]:
    """Load research report from cache if not expired.

    Args:
        topic: Research topic to look up

    Returns:
        ResearchReport if found and not expired, None otherwise

    Performance target: <50ms for cache hit
    """
    if not topic or not topic.strip():
        return None

    topic_key = topic.strip().lower()
    start_time = datetime.now(timezone.utc)

    with get_connection() as c:
        row = c.execute(
            """
            SELECT sources, findings, confidence_score, triangulation_score
            FROM research_cache
            WHERE topic = ? AND expires_at > datetime('now')
        """,
            (topic_key,),
        ).fetchone()

        if not row:
            _emit_metric("web_research.cache_miss", {"topic": topic})
            return None

        # Deserialize sources
        sources_data = json.loads(row[0])
        sources = [_source_from_cache_dict(s) for s in sources_data]

        report = ResearchReport(
            topic=topic,
            sources=sources,
            findings=row[1],
            confidence=row[2],
            triangulation=row[3],
            cache_status="cached",
        )

        duration_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

        _emit_metric(
            "web_research.cache_hit",
            {"topic": topic, "duration_ms": round(duration_ms, 2), "source_count": len(sources)},
        )

        return report


def invalidate_cache(topic: str, *, emit_events: bool = True) -> None:
    """Delete cached research for a topic.

    Args:
        topic: Research topic to invalidate
        emit_events: Emit canonical research cache events when True.

    Note:
        Silently succeeds even if topic not found in cache
    """
    if not topic or not topic.strip():
        return

    topic_key = topic.strip().lower()

    if emit_events:
        # Slice 3: Emit event via spool pipeline
        write_envelopes(
            [
                CanonicalEventEnvelope(
                    event_type=CanonicalEventType.RESEARCH_CACHE_CLEARED.value,
                    session_id=None,
                    payload={"topic": topic_key},
                    confidence="unavailable",
                    project_id=None,
                )
            ]
        )

    with transaction() as c:
        rows_deleted = c.execute(
            "DELETE FROM research_cache WHERE topic = ?", (topic_key,)
        ).rowcount

    _emit_metric("web_research.cache_invalidate", {"topic": topic, "rows_deleted": rows_deleted})
