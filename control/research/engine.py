"""Legacy opt-in cache-first research engine.

This module is maintained as a compatibility lineage engine for callers that
explicitly opt into ``raw_research`` trust scoring. It is not the dashboard/API
research cache authority, and it must not promote research output into workflow,
execution, architecture, or semantic-memory authority by itself.
"""

from __future__ import annotations
import json
from datetime import datetime, UTC

from core.event_store.studio_db import _connect
from core.files.store import connect_files
from core.storage.document_store import ensure_documents_schema

# Decision transparency layer
from core.decisions import emit_decision

# Transaction pattern for database writes
from core.config.database import transaction

_NOW = lambda: datetime.now(UTC).isoformat()

ENGINE_STATUS = "legacy_opt_in"
ENGINE_AUTHORITY_CLASSIFICATION = "raw_research_advisory_lineage"


# ═══════════════════════════════════════════════════════════════════════════
# DECISION TRANSPARENCY: Trust Score Policy
# ═══════════════════════════════════════════════════════════════════════════
# All trust score assignments follow this explicit policy.
# Trust scores determine cache eligibility (higher = more likely to cache).

TRUST_POLICY = {
    "fresh_research": {
        "score": 0.5,
        "reason": "No validation history at creation time; baseline trust until validated",
    },
    "analyzed_repo": {
        "score": 0.7,
        "reason": "Derived from structured repository analysis; higher confidence than web research",
    },
    "default": {
        "score": 0.5,
        "reason": "Fallback for unknown sources; conservative baseline trust",
    },
}


# ═══════════════════════════════════════════════════════════════════════════
# DECISION TRANSPARENCY: TTL (Time-To-Live) Policy
# ═══════════════════════════════════════════════════════════════════════════
# Research cache expiration times based on domain volatility.
# Higher volatility = shorter TTL = faster invalidation.

TTL_POLICY = {
    "security": {
        "days": 7,
        "reason": "High volatility domain; vulnerabilities and patches change weekly",
    },
    "stack": {
        "days": 30,
        "reason": "Medium volatility; framework versions update monthly on average",
    },
    "docs": {"days": 60, "reason": "Low volatility; official documentation changes infrequently"},
    "pattern": {
        "days": 90,
        "reason": "Very low volatility; coding patterns are stable over quarters",
    },
    "general": {
        "days": 14,
        "reason": "Default for unclassified research; conservative 2-week refresh",
    },
}


def research_with_cache(
    query: str, context: dict, research_type: str, min_trust: float = 0.7
) -> dict:
    """
    Main entry point for all research with cache-first strategy.

    raw_research table dropped migration 131. Cache lookup and storage removed;
    analyzed-repo lookup via files.db ds_documents is preserved.

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
    # 1. Check analyzed repos (files.db ds_documents — not raw_research)
    repo_result = _check_analyzed_repos(query, context, min_trust)
    if repo_result:
        _emit_metric(
            "research.repo_hit",
            {
                "query": query,
                "research_type": research_type,
                "trust_score": repo_result["trust_score"],
            },
        )
        return {
            "data": repo_result["data"],
            "primary_source": repo_result["source_url"],
            "cached": False,
            "trust_score": repo_result["trust_score"],
        }

    # 2. Execute fresh research
    _emit_metric("research.cache_miss", {"query": query, "research_type": research_type})
    fresh_result = _execute_research(query, context, research_type)

    _emit_metric(
        "research.fresh_research",
        {"query": query, "research_type": research_type},
    )

    return {
        "data": fresh_result["data"],
        "primary_source": fresh_result["primary_source"],
        "cached": False,
        "trust_score": TRUST_POLICY["fresh_research"]["score"],
        "trust_reason": TRUST_POLICY["fresh_research"]["reason"],
    }


def _check_analyzed_repos(query: str, _context: dict, min_trust: float) -> dict | None:
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

        c = connect_files()
        try:
            ensure_documents_schema(c)
            # Search for analyzed repos or code patterns in files.db
            rows = c.execute(
                """SELECT d.doc_id, d.title, d.content, d.metadata
                   FROM ds_documents d
                   INNER JOIN ds_documents_fts f ON d.doc_id = f.rowid
                   WHERE ds_documents_fts MATCH ?
                     AND d.doc_type IN ('repo_analysis', 'code_pattern', 'api_doc')
                     AND d.status = 'active'
                   LIMIT 3""",
                (keywords,),
            ).fetchall()
        finally:
            c.close()

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

        # Get trust score from metadata or use policy default for analyzed repos
        trust_score = metadata.get("trust_score", TRUST_POLICY["analyzed_repo"]["score"])

        if trust_score < min_trust:
            return None

        return {
            "data": {
                "title": top_match["title"],
                "content": top_match["content"],
                "metadata": metadata,
                "source": "analyzed_repo",
            },
            "source_url": metadata.get("repo_url", f"doc://{top_match['doc_id']}"),
            "trust_score": trust_score,
            "trust_reason": TRUST_POLICY["analyzed_repo"]["reason"],
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
    # research methods removed in Phase 18.1.12 (operator decision: remove stub, not ship fake data)
    return {
        "data": {
            "query": query,
            "context": context,
            "research_type": research_type,
            "status": "unavailable",
            "note": "Research integration not implemented. Removed in Phase 18.1.12.",
        },
        "primary_source": "internal://not-available",
    }


def _determine_ttl(research_type: str) -> int:
    """
    Determine time-to-live in days based on research type.

    Uses TTL_POLICY for explicit domain volatility mapping.
    See TTL_POLICY documentation above for rationale.

    Args:
        research_type: Type of research ('stack', 'security', 'docs', 'pattern', 'general')

    Returns:
        TTL in days (from policy)
    """
    # Use policy-defined TTL, fallback to 'general' if type unknown
    policy_entry = TTL_POLICY.get(research_type, TTL_POLICY["general"])
    ttl_days = policy_entry["days"]

    # Emit decision for TTL assignment
    emit_decision(
        decision_type="ttl.assignment",
        context={"research_type": research_type},
        outcome=ttl_days,
        reasoning={
            "policy": "TTL_POLICY",
            "rule": research_type,
            "rationale": policy_entry["reason"],
        },
        confidence=1.0,  # Deterministic policy lookup
        policy_applied="TTL_POLICY_V1",
        source_subsystem="research_engine",
    )

    return ttl_days


def _emit_metric(event: str, data: dict) -> None:
    """
    Emit telemetry metric to raw_metrics table if it exists.

    Args:
        event: Event name (e.g., "research.cache_hit")
        data: Event data dict
    """
    try:
        metric = {"event": event, "data": data, "timestamp": _NOW()}
        metric_json = json.dumps(metric)

        with _connect() as c:
            # Check if raw_metrics table exists
            table_exists = c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='raw_metrics'"
            ).fetchone()

            if table_exists:
                # Use transaction pattern for write
                with transaction() as conn:
                    conn.execute(
                        "INSERT INTO raw_metrics (event, data, created_at) VALUES (?, ?, ?)",
                        (event, metric_json, _NOW()),
                    )
    except Exception:
        # Fail silently if metrics table doesn't exist or write fails
        pass
