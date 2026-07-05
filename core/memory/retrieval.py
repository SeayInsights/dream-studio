"""Memory retrieval layer — FTS5-accelerated search over memory_entries.

The retrieval layer is a PROJECTION of memory_entries. It can be rebuilt
from scratch at any time. FTS5 indexes are disposable acceleration structures.

Usage:
    retriever = FTS5MemoryRetriever()
    results = retriever.search("security vulnerability", top_k=5)
    retriever.rebuild_index()
"""

import logging
import math
import sqlite3
from datetime import datetime, UTC
from typing import Protocol

from core.config.database import get_connection, transaction
from core.memory.store import (
    DECAY_HALF_LIVES,
    MemoryEntry,
    MemoryQuery,
    MemoryStore,
    RetrievalResult,
    _DEFAULT_RETRIEVE_STATES,
)

logger = logging.getLogger(__name__)


def check_fts5_capability() -> dict:
    """Probe FTS5 support using a throwaway in-memory SQLite connection.

    Does NOT touch the active Dream Studio database.
    Safe to call during startup or health checks.

    Returns:
        dict with keys: available (bool), status (str)
        Status values: fts5_available, unavailable_fts5_missing
    """
    probe = sqlite3.connect(":memory:")
    try:
        probe.execute("CREATE VIRTUAL TABLE _fts5_probe USING fts5(content)")
        return {"available": True, "status": "fts5_available"}
    except sqlite3.OperationalError:
        return {"available": False, "status": "unavailable_fts5_missing"}
    finally:
        probe.close()


class MemoryRetriever(Protocol):
    def search(
        self, query: str, filters: MemoryQuery | None = None, top_k: int = 10
    ) -> list[RetrievalResult]: ...

    def rebuild_index(self) -> int: ...

    def index_entry(self, entry: MemoryEntry) -> None: ...


class FTS5MemoryRetriever:
    """FTS5-based memory retrieval with importance-weighted ranking.

    Uses a standalone FTS5 table (no content= sync) managed explicitly.
    Call rebuild_index() after ingestion to update the search index.
    """

    DEFAULT_HALF_LIFE = 30.0

    def __init__(self, store: MemoryStore | None = None):
        self.store = store or MemoryStore()
        self._ensure_fts()

    def _ensure_fts(self) -> None:
        try:
            with transaction() as conn:
                conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
                        memory_id UNINDEXED,
                        content,
                        category,
                        tags
                    )
                """)
        except sqlite3.OperationalError as e:
            if "no such module" in str(e).lower():
                logger.warning("FTS5 not available — falling back to keyword search")
            else:
                raise

    def search(
        self, query: str, filters: MemoryQuery | None = None, top_k: int = 10
    ) -> list[RetrievalResult]:
        if not query or not query.strip():
            return []

        filters = filters or MemoryQuery()

        if self._fts_available():
            return self._fts_search(query, filters, top_k)
        return self._keyword_search(query, filters, top_k)

    def _fts_search(self, query: str, filters: MemoryQuery, top_k: int) -> list[RetrievalResult]:
        safe_query = self._sanitize_fts_query(query)
        if not safe_query:
            return []

        lifecycle_filter = filters.lifecycle_states or list(_DEFAULT_RETRIEVE_STATES)
        placeholders = ",".join("?" for _ in lifecycle_filter)

        sql = f"""
            SELECT me.*, bm25(memory_fts) as fts_rank
            FROM memory_fts mf
            JOIN memory_entries me ON mf.memory_id = me.memory_id
            WHERE mf MATCH ?
              AND me.lifecycle_state IN ({placeholders})
        """
        params: list = [safe_query] + lifecycle_filter

        if filters.memory_type:
            sql += " AND me.source = ?"
            params.append(filters.memory_type)
        if filters.category:
            sql += " AND me.category = ?"
            params.append(filters.category)
        if filters.project:
            sql += " AND (me.project = ? OR me.project IS NULL)"
            params.append(filters.project)
        if filters.skill:
            sql += " AND (me.skill = ? OR me.skill IS NULL)"
            params.append(filters.skill)
        if filters.min_importance > 0:
            sql += " AND me.importance >= ?"
            params.append(filters.min_importance)

        sql += f" ORDER BY bm25(memory_fts) LIMIT {top_k * 3}"

        with get_connection(read_only=True) as conn:
            conn.row_factory = sqlite3.Row
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                return self._keyword_search(query, filters, top_k)

        return self._rank_results(rows, top_k, filters.include_decayed)

    def _keyword_search(
        self, query: str, filters: MemoryQuery, top_k: int
    ) -> list[RetrievalResult]:
        return self.store.retrieve(
            MemoryQuery(
                text=query,
                memory_type=filters.memory_type,
                category=filters.category,
                project=filters.project,
                skill=filters.skill,
                min_importance=filters.min_importance,
                tags=filters.tags,
                limit=top_k,
                include_decayed=filters.include_decayed,
                lifecycle_states=filters.lifecycle_states,
            )
        )

    def _rank_results(self, rows, top_k: int, include_decayed: bool) -> list[RetrievalResult]:
        results: list[RetrievalResult] = []
        now = datetime.now(UTC)

        max_bm25 = 1.0
        if rows:
            scores = [abs(r["fts_rank"]) for r in rows]
            max_bm25 = max(scores) if scores else 1.0

        for row in rows:
            entry = MemoryStore._row_to_entry(row)
            half_life = DECAY_HALF_LIVES.get(entry.memory_type, self.DEFAULT_HALF_LIFE)

            try:
                base = entry.last_accessed or entry.created_at
                base_dt = datetime.fromisoformat(base.replace("Z", "+00:00"))
                age_days = (now - base_dt).total_seconds() / 86400
            except (ValueError, TypeError):
                age_days = 365.0

            temporal_weight = math.exp(-0.693 * age_days / half_life)

            if not include_decayed and temporal_weight < 0.1:
                continue

            text_match = abs(row["fts_rank"]) / max_bm25 if max_bm25 > 0 else 0.0
            access_boost = min(math.log(entry.access_count + 1) / 5, 1.0)
            recency_boost = max(0.0, 1.0 - age_days / 7.0) if age_days < 7 else 0.0

            relevance = (
                entry.importance * 0.30
                + temporal_weight * 0.25
                + text_match * 0.25
                + access_boost * 0.10
                + recency_boost * 0.10
            )

            reason_parts = []
            if text_match > 0.5:
                reason_parts.append(f"fts_match={text_match:.2f}")
            if entry.importance >= 0.8:
                reason_parts.append("high_importance")
            if temporal_weight > 0.8:
                reason_parts.append("recent")

            results.append(
                RetrievalResult(
                    entry=entry,
                    relevance_score=relevance,
                    match_reason=", ".join(reason_parts) or "baseline",
                )
            )

        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:top_k]

    def rebuild_index(self) -> int:
        """Drop and rebuild FTS5 index from memory_entries."""
        count = 0
        with transaction() as conn:
            try:
                conn.execute("DELETE FROM memory_fts")
            except sqlite3.OperationalError:
                return 0

            placeholders = ",".join("?" for _ in _DEFAULT_RETRIEVE_STATES)
            rows = conn.execute(
                f"""
                SELECT memory_id, content, category, tags
                FROM memory_entries
                WHERE lifecycle_state IN ({placeholders})
            """,
                _DEFAULT_RETRIEVE_STATES,
            ).fetchall()

            for row in rows:
                conn.execute(
                    """
                    INSERT INTO memory_fts(memory_id, content, category, tags)
                    VALUES (?, ?, ?, ?)
                """,
                    (row[0], row[1], row[2], row[3]),
                )
                count += 1

        logger.info(f"Rebuilt memory_fts index: {count} entries indexed")
        return count

    def index_entry(self, entry: MemoryEntry) -> None:
        """Index a single entry into FTS5."""
        if entry.lifecycle_state not in _DEFAULT_RETRIEVE_STATES:
            return
        with transaction() as conn:
            try:
                conn.execute(
                    "DELETE FROM memory_fts WHERE memory_id = ?",
                    (entry.memory_id,),
                )
                conn.execute(
                    """
                    INSERT INTO memory_fts(memory_id, content, category, tags)
                    VALUES (?, ?, ?, ?)
                """,
                    (
                        entry.memory_id,
                        entry.content,
                        entry.category,
                        ",".join(entry.tags) if entry.tags else "",
                    ),
                )
            except sqlite3.OperationalError:
                pass

    def _fts_available(self) -> bool:
        try:
            with get_connection(read_only=True) as conn:
                conn.execute("SELECT 1 FROM memory_fts LIMIT 0")
                return True
        except sqlite3.OperationalError:
            return False

    @staticmethod
    def _sanitize_fts_query(query: str) -> str:
        tokens = query.strip().split()
        safe = []
        for t in tokens:
            cleaned = "".join(c for c in t if c.isalnum() or c in "-_")
            if cleaned:
                safe.append(cleaned)
        if not safe:
            return ""
        return " OR ".join(safe)
