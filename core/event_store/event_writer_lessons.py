"""event_writer lessons group: raw_lessons + research_cache writers.

WO-GF-PROJECTION-ENGINE: split from ``core/event_store/event_writer.py``.
NOTE: reject_lesson has NO @_with_retry decorator — preserved verbatim (asymmetry
from the pre-split source).
"""

from __future__ import annotations
import hashlib
import json
from datetime import datetime, timedelta, UTC
from pathlib import Path

from .connection import (
    _CanonicalEventType,
    _NOW,
    _db_transaction,
    _reraise_if_busy,
    _try_emit_canonical,
    _with_retry,
)


@_with_retry
def insert_lesson(
    lesson_id: str,
    source: str,
    title: str,
    *,
    what_happened: str | None = None,
    lesson: str | None = None,
    evidence: str | None = None,
    confidence: str = "medium",
    prd_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    skill_id: str | None = None,
    db_path: Path | None = None,
) -> bool:
    """
    Insert lesson into raw_lessons table.

    Writes to activity_log FIRST via EventNormalizer, then links via activity_id (Phase 3 traceability).

    Args:
        lesson_id: Unique lesson identifier
        source: Source of the lesson (e.g., 'build', 'review', 'debug')
        title: Short lesson title
        what_happened: Description of what occurred
        lesson: The actual lesson learned
        evidence: Evidence supporting the lesson
        confidence: Confidence level ('low', 'medium', 'high')
        prd_id: Optional PRD ID for cross-domain linkage
        task_id: Optional task ID for cross-domain linkage
        session_id: Optional session ID for cross-domain linkage
        skill_id: Optional skill ID for cross-domain linkage
        db_path: Optional database path
    """
    try:
        with _db_transaction(db_path) as c:
            # 1. Emit canonical event (TA0c: activity_log retired)
            _try_emit_canonical(
                _CanonicalEventType.LESSON_CAPTURED,
                {
                    "lesson_id": lesson_id,
                    "source": source,
                    "title": title,
                    "confidence": confidence,
                },
                session_id=session_id,
                task_id=task_id,
                prd_id=prd_id,
                skill_id=skill_id,
            )
            activity_id = None  # deprecated FK column

            # 2. Insert into raw_lessons with activity_id FK
            c.execute(
                """INSERT OR IGNORE INTO raw_lessons
                   (lesson_id, source, title, what_happened, lesson,
                    evidence, confidence, created_at, activity_id,
                    prd_id, task_id, skill_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    lesson_id,
                    source,
                    title,
                    what_happened,
                    lesson,
                    evidence,
                    confidence,
                    _NOW(),
                    activity_id,
                    prd_id,
                    task_id,
                    skill_id,
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def draft_lesson(
    source: str,
    title: str,
    *,
    lesson_id: str | None = None,
    what_happened: str | None = None,
    lesson: str | None = None,
    evidence: str | None = None,
    confidence: str = "medium",
    db_path: Path | None = None,
) -> bool:
    """Create a draft lesson in raw_lessons. Single authoritative entry point.

    lesson_id defaults to a UUID if not supplied. Callers that need deterministic
    deduplication (e.g., file-based writers that deduplicated by filename) should
    supply a stable lesson_id (e.g., the old filename stem).
    """
    import uuid as _uuid

    lid = lesson_id if lesson_id is not None else str(_uuid.uuid4())
    return insert_lesson(
        lid,
        source,
        title,
        what_happened=what_happened,
        lesson=lesson,
        evidence=evidence,
        confidence=confidence,
        db_path=db_path,
    )


@_with_retry
def promote_lesson(lesson_id: str, promoted_to: str, db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                """UPDATE raw_lessons SET
                    status='promoted', promoted_to=?, reviewed_at=?
                   WHERE lesson_id=?""",
                (promoted_to, _NOW(), lesson_id),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


def reject_lesson(lesson_id: str, db_path: Path | None = None) -> bool:
    try:
        with _db_transaction(db_path) as c:
            c.execute(
                "UPDATE raw_lessons SET status='rejected', reviewed_at=? WHERE lesson_id=?",
                (_NOW(), lesson_id),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False


@_with_retry
def cache_research(
    topic: str,
    focus_areas: list[str],
    sources: list[dict],
    findings: str,
    *,
    confidence_score: float = 0.5,
    triangulation_score: float = 0.5,
    prd_id: str | None = None,
    task_id: str | None = None,
    session_id: str | None = None,
    ttl_days: int = 30,
    db_path: Path | None = None,
) -> bool:
    """
    Cache research results in research_cache table.

    Writes to activity_log FIRST via EventNormalizer, then links via activity_id (Phase 3 traceability).

    Args:
        topic: Research topic
        focus_areas: List of focus areas (JSON array)
        sources: List of source dicts with {url, title, summary, tier}
        findings: Markdown summary of research findings
        confidence_score: Overall confidence (0.0-1.0)
        triangulation_score: Source triangulation score (0.0-1.0)
        prd_id: Optional PRD ID for cross-domain linkage
        task_id: Optional task ID for cross-domain linkage
        session_id: Optional session ID for cross-domain linkage
        ttl_days: Time-to-live in days (default 30)
        db_path: Optional database path
    """
    try:
        cache_id = hashlib.sha256(topic.encode()).hexdigest()[:16]
        expires_at = (datetime.now(UTC) + timedelta(days=ttl_days)).isoformat()

        with _db_transaction(db_path) as c:
            # 1. Emit canonical event (TA0c: activity_log retired)
            _try_emit_canonical(
                _CanonicalEventType.RESEARCH_CACHE_STORED,
                {
                    "cache_id": cache_id,
                    "topic": topic,
                    "source_count": len(sources),
                    "confidence_score": confidence_score,
                    "triangulation_score": triangulation_score,
                },
                session_id=session_id,
                task_id=task_id,
                prd_id=prd_id,
            )
            activity_id = None  # deprecated FK column

            # 2. Insert into research_cache with activity_id FK
            c.execute(
                """INSERT OR REPLACE INTO research_cache
                   (cache_id, topic, focus_areas, sources, findings,
                    confidence_score, triangulation_score, activity_id,
                    prd_id, task_id, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cache_id,
                    topic,
                    json.dumps(focus_areas),
                    json.dumps(sources),
                    findings,
                    confidence_score,
                    triangulation_score,
                    activity_id,
                    prd_id,
                    task_id,
                    expires_at,
                ),
            )
        return True
    except Exception as e:
        _reraise_if_busy(e)
        return False
