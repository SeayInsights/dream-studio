"""Cache-first research engine with trust scoring and source tracking."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Optional

from .studio_db import _connect

_NOW = lambda: datetime.now(timezone.utc).isoformat()


def research_with_cache(
    query: str,
    context: dict,
    research_type: str,
    min_trust: float = 0.7
) -> dict:
    """
    Main entry point for all research with cache-first strategy.

    Args:
        query: Research query string
        context: Context dict for research (project, skill, etc.)
        research_type: Type of research ('stack', 'security', 'docs', 'pattern', 'general')
        min_trust: Minimum trust score threshold (0.0-1.0)

    Returns:
        dict with keys:
            - data: Research findings (dict)
            - primary_source: Source URL (str)
            - cached: Whether result came from cache (bool)
            - trust_score: Trust score of result (float)
    """
    query_hash = hashlib.sha256(query.encode()).hexdigest()

    # 1. Check cache first
    cached_result = _check_cache(query_hash, min_trust)
    if cached_result:
        _emit_metric("research.cache_hit", {
            "query_hash": query_hash,
            "research_type": research_type,
            "trust_score": cached_result["trust_score"]
        })
        return {
            "data": cached_result["findings"],
            "primary_source": cached_result["source_url"],
            "cached": True,
            "trust_score": cached_result["trust_score"]
        }

    # 2. Check analyzed repos
    repo_result = _check_analyzed_repos(query, context, min_trust)
    if repo_result:
        _emit_metric("research.repo_hit", {
            "query": query,
            "research_type": research_type,
            "trust_score": repo_result["trust_score"]
        })
        # Store repo findings in cache for future use
        ttl_days = _determine_ttl(research_type)
        _store_research(
            query,
            query_hash,
            repo_result["source_url"],
            repo_result["data"],
            research_type,
            ttl_days
        )
        return {
            "data": repo_result["data"],
            "primary_source": repo_result["source_url"],
            "cached": False,
            "trust_score": repo_result["trust_score"]
        }

    # 3. Execute fresh research
    _emit_metric("research.cache_miss", {
        "query": query,
        "research_type": research_type
    })
    fresh_result = _execute_research(query, context, research_type)

    # 4. Store result
    ttl_days = _determine_ttl(research_type)
    research_id = _store_research(
        query,
        query_hash,
        fresh_result["primary_source"],
        fresh_result["data"],
        research_type,
        ttl_days
    )

    _emit_metric("research.fresh_research", {
        "query": query,
        "research_type": research_type,
        "research_id": research_id
    })

    return {
        "data": fresh_result["data"],
        "primary_source": fresh_result["primary_source"],
        "cached": False,
        "trust_score": 0.5  # Default trust for new research
    }


def _check_cache(query_hash: str, min_trust: float) -> Optional[dict]:
    """
    Query cache for validated research with sufficient trust.

    Args:
        query_hash: SHA256 hash of query string
        min_trust: Minimum trust score threshold

    Returns:
        dict with findings, source_url, trust_score if found, else None
    """
    try:
        now = _NOW()
        with _connect() as c:
            row = c.execute(
                """SELECT research_id, findings, source_url, trust_score, times_referenced
                   FROM raw_research
                   WHERE query_hash = ?
                     AND validation_status = 'validated'
                     AND trust_score >= ?
                     AND (expires_at IS NULL OR expires_at > ?)
                   ORDER BY trust_score DESC, created_at DESC
                   LIMIT 1""",
                (query_hash, min_trust, now)
            ).fetchone()

            if not row:
                return None

            # Increment reference counter
            c.execute(
                "UPDATE raw_research SET times_referenced = times_referenced + 1 WHERE research_id = ?",
                (row["research_id"],)
            )

            # Parse findings JSON
            try:
                findings = json.loads(row["findings"])
            except (json.JSONDecodeError, TypeError):
                findings = {"raw": row["findings"]}

            return {
                "findings": findings,
                "source_url": row["source_url"],
                "trust_score": row["trust_score"]
            }
    except Exception:
        return None


def _check_analyzed_repos(query: str, _context: dict, min_trust: float) -> Optional[dict]:
    """
    Query analyzed repos (ds_documents) for matching knowledge.

    Args:
        query: Research query string
        context: Context dict (may contain project_id, skill_id)
        min_trust: Minimum trust score threshold

    Returns:
        dict with data, source_url, trust_score if found, else None
    """
    try:
        # Extract keywords from query for FTS search
        keywords = query.lower().strip()

        with _connect() as c:
            # Search for analyzed repos or code patterns
            rows = c.execute(
                """SELECT d.doc_id, d.title, d.content, d.metadata
                   FROM ds_documents d
                   INNER JOIN ds_documents_fts f ON d.doc_id = f.rowid
                   WHERE ds_documents_fts MATCH ?
                     AND d.doc_type IN ('repo_analysis', 'code_pattern', 'api_doc')
                     AND d.status = 'active'
                   LIMIT 3""",
                (keywords,)
            ).fetchall()

            if not rows:
                return None

            # Extract findings from top match
            top_match = rows[0]
            metadata = {}
            if top_match["metadata"]:
                try:
                    metadata = json.loads(top_match["metadata"])
                except (json.JSONDecodeError, TypeError):
                    pass

            # Get trust score from metadata or use default
            trust_score = metadata.get("trust_score", 0.7)

            if trust_score < min_trust:
                return None

            return {
                "data": {
                    "title": top_match["title"],
                    "content": top_match["content"],
                    "metadata": metadata,
                    "source": "analyzed_repo"
                },
                "source_url": metadata.get("repo_url", f"doc://{top_match['doc_id']}"),
                "trust_score": trust_score
            }
    except Exception:
        return None


def _execute_research(query: str, context: dict, research_type: str) -> dict:
    """
    Dispatch to appropriate research method based on type.

    Args:
        query: Research query string
        context: Context dict
        research_type: Type of research

    Returns:
        dict with keys:
            - data: Research findings
            - primary_source: Source URL
    """
    # Import research methods (gracefully handle if not implemented yet)
    try:
        from hooks.lib.research_methods import (
            _research_stack_compatibility,
            _research_security_pattern,
            _research_documentation,
            _research_code_pattern,
            _research_general
        )

        method_map = {
            'stack': _research_stack_compatibility,
            'security': _research_security_pattern,
            'docs': _research_documentation,
            'pattern': _research_code_pattern,
            'general': _research_general
        }

        method = method_map.get(research_type, _research_general)
        return method(query, context)

    except ImportError:
        # Fallback: return stub response if research_methods not implemented yet
        return {
            "data": {
                "query": query,
                "context": context,
                "research_type": research_type,
                "status": "pending_implementation",
                "note": "Research methods module not yet implemented"
            },
            "primary_source": "internal://stub"
        }


def _store_research(
    query: str,
    query_hash: str,
    source_url: str,
    findings: dict,
    source_type: str,
    ttl_days: int
) -> int:
    """
    Store research findings in cache.

    Args:
        query: Original query string
        query_hash: SHA256 hash of query
        source_url: Primary source URL
        findings: Research findings dict
        source_type: Type of research source
        ttl_days: Time-to-live in days

    Returns:
        research_id of stored record
    """
    try:
        expires_at = None
        if ttl_days > 0:
            expires_dt = datetime.now(timezone.utc) + timedelta(days=ttl_days)
            expires_at = expires_dt.isoformat()

        findings_json = json.dumps(findings)

        with _connect() as c:
            cursor = c.execute(
                """INSERT INTO raw_research
                   (query, query_hash, source_type, source_url, findings,
                    confidence_score, trust_score, validation_status,
                    times_referenced, success_rate, created_at, ttl_days, expires_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (query, query_hash, source_type, source_url, findings_json,
                 0.5, 0.5, 'pending', 0, 0.5, _NOW(), ttl_days, expires_at)
            )
            return cursor.lastrowid or -1
    except Exception:
        return -1


def _determine_ttl(research_type: str) -> int:
    """
    Determine time-to-live in days based on research type.

    Args:
        research_type: Type of research

    Returns:
        TTL in days
    """
    ttl_map = {
        'stack': 30,
        'security': 7,
        'docs': 60,
        'pattern': 90,
        'general': 14
    }
    return ttl_map.get(research_type, 14)


def _emit_metric(event: str, data: dict) -> None:
    """
    Emit telemetry metric to raw_metrics table if it exists.

    Args:
        event: Event name (e.g., "research.cache_hit")
        data: Event data dict
    """
    try:
        metric = {
            "event": event,
            "data": data,
            "timestamp": _NOW()
        }
        metric_json = json.dumps(metric)

        with _connect() as c:
            # Check if raw_metrics table exists
            table_exists = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='raw_metrics'"
            ).fetchone()

            if table_exists:
                c.execute(
                    "INSERT INTO raw_metrics (event, data, created_at) VALUES (?, ?, ?)",
                    (event, metric_json, _NOW())
                )
    except Exception:
        # Fail silently if metrics table doesn't exist or write fails
        pass
