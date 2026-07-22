"""Research caching layer (SQLite-backed) for web research.

WO-GF-CONTROL-INSTALL-split: see web.py facade docstring.
"""

from __future__ import annotations

from datetime import datetime, timedelta, UTC
import json

from canonical.events.envelope import CanonicalEventEnvelope
from canonical.events.types import EventType as CanonicalEventType
from core.config.database import transaction, get_connection
from emitters.shared.spool_writer import write_envelopes

from .web_shared import ResearchReport, Source, _emit_metric


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
    expires_at = datetime.now(UTC) + timedelta(days=ttl_days)

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


def load_from_cache(topic: str) -> ResearchReport | None:
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
    start_time = datetime.now(UTC)

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

        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000

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


def load_from_cache_by_id(cache_id: str) -> ResearchReport | None:
    """Load research report from cache by cache_id, or None if not found/expired."""
    with get_connection() as c:
        row = c.execute(
            "SELECT topic, sources, findings, confidence_score, triangulation_score "
            "FROM research_cache WHERE cache_id = ? AND expires_at > datetime('now')",
            (cache_id,),
        ).fetchone()
    if row is None:
        return None
    sources = [_source_from_cache_dict(s) for s in json.loads(row[1])]
    return ResearchReport(
        topic=row[0],
        sources=sources,
        findings=row[2],
        confidence=row[3],
        triangulation=row[4],
        cache_status="cached",
    )


def delete_from_cache_by_id(cache_id: str) -> None:
    """Remove cache entry by cache_id. Idempotent — succeeds even if not found."""
    with transaction() as c:
        c.execute("DELETE FROM research_cache WHERE cache_id = ?", (cache_id,))
