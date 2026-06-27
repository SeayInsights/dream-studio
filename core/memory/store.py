"""Canonical memory store — unified retrieval across all knowledge sources.

ALL LONG-TERM SEMANTIC MEMORY CONVERGES INTO memory_entries.

Other systems are ingestion sources, lifecycle stages, or retrieval indexes.
memory_entries is the canonical semantic memory authority.

Memory entries are stored in SQLite with importance scoring, temporal decay,
lifecycle state management, and provenance tracking.
"""

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from core.config.database import get_connection, transaction
from core.config.paths import state_dir
from core.ontology.lifecycles import LIFECYCLE_CATALOG, MemoryLifecycle, to_db_value

_DEFAULT_RETRIEVE_STATES = (
    to_db_value(MemoryLifecycle.ACTIVE),
    to_db_value(MemoryLifecycle.PROMOTED),
    to_db_value(MemoryLifecycle.CANDIDATE),
)

VALID_MEMORY_TYPES = frozenset(
    {
        "lesson",
        "gotcha",
        "correction",
        "decision",
        "pattern",
        "operational",
    }
)

VALID_SOURCE_TYPES = frozenset(
    {
        "raw_lessons",
        "reg_gotchas",
        # cor_skill_corrections retired migration 131 (table + ingestion consumer removed)
        "canonical_events",
        "filesystem",
        "ds_documents",
        "unknown",
    }
)

DECAY_HALF_LIVES = {
    "lesson": 30.0,
    "gotcha": 90.0,
    "correction": 14.0,
    "decision": 30.0,
    "pattern": 30.0,
    "operational": 14.0,
}


@dataclass
class MemoryEntry:
    memory_id: str
    memory_type: str  # lesson | gotcha | correction | decision | pattern | operational
    category: str  # security | architecture | debugging | workflow | skill_routing | general
    content: str
    source_type: str = (
        "unknown"  # raw_lessons | reg_gotchas | canonical_events | filesystem | ds_documents
    )
    source_id: str = ""  # FK to source record (lesson_id, gotcha_id, etc.)
    lifecycle_state: str = "ACTIVE"  # persisted as string; see MemoryLifecycle for valid values
    metadata: Dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5  # 0.0-1.0
    confidence: Optional[float] = None  # 0.0-1.0
    created_at: str = ""
    updated_at: str = ""
    last_accessed: str = ""
    access_count: int = 0
    tags: List[str] = field(default_factory=list)
    project: Optional[str] = None
    skill: Optional[str] = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    lineage: Dict[str, Any] = field(default_factory=dict)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    embedding: Optional[List[float]] = None


@dataclass
class MemoryQuery:
    text: Optional[str] = None
    memory_type: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    project: Optional[str] = None
    skill: Optional[str] = None
    min_importance: float = 0.0
    limit: int = 10
    include_decayed: bool = False
    lifecycle_states: Optional[List[str]] = None


@dataclass
class RetrievalResult:
    entry: MemoryEntry
    relevance_score: float
    match_reason: str


class MemoryStore:
    """Unified memory store with importance scoring, temporal decay, and lifecycle management."""

    DEFAULT_HALF_LIFE = 30.0

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or str(state_dir() / "studio.db")
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        # Table must exist — created by migration 011_memory_entries.sql.
        # If missing, the migration sequence did not run correctly.
        with get_connection(read_only=True) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memory_entries'"
            ).fetchone()
        if not row:
            raise RuntimeError(
                "memory_entries table not found. "
                "Run the migration sequence: py -m interfaces.cli.ds install"
            )

    # ── Core CRUD ────────────────────────────────────────────────────────────

    def store(self, entry: MemoryEntry) -> str:
        if not entry.memory_id:
            entry.memory_id = str(uuid4())
        now = datetime.now(timezone.utc).isoformat()
        if not entry.created_at:
            entry.created_at = now
        entry.updated_at = now

        with transaction() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_entries
                    (memory_id, source, category, content, source_type, source_id,
                     lifecycle_state, metadata, importance, confidence,
                     created_at, updated_at, last_accessed, access_count,
                     tags, project, skill, provenance, lineage, relationships)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.memory_id,
                    entry.memory_type,
                    entry.category,
                    entry.content,
                    entry.source_type,
                    entry.source_id or None,
                    entry.lifecycle_state,
                    json.dumps(entry.metadata) if entry.metadata else None,
                    entry.importance,
                    entry.confidence,
                    entry.created_at,
                    entry.updated_at,
                    entry.last_accessed,
                    entry.access_count,
                    json.dumps(entry.tags) if entry.tags else None,
                    entry.project,
                    entry.skill,
                    json.dumps(entry.provenance) if entry.provenance else None,
                    json.dumps(entry.lineage) if entry.lineage else None,
                    json.dumps(entry.relationships) if entry.relationships else None,
                ),
            )
        return entry.memory_id

    def upsert_by_provenance(self, entry: MemoryEntry) -> str:
        """Idempotent upsert keyed by (source_type, source_id).

        If a memory with the same provenance exists:
        - Updates content, metadata, confidence, tags
        - Preserves lifecycle_state, importance, access_count
        - Updates provenance.ingested_at
        """
        if not entry.source_type or not entry.source_id:
            raise ValueError("upsert_by_provenance requires source_type and source_id")

        now = datetime.now(timezone.utc).isoformat()
        entry.updated_at = now
        if entry.provenance:
            entry.provenance["ingested_at"] = now

        with transaction() as conn:
            existing = conn.execute(
                "SELECT memory_id, lifecycle_state, importance, access_count, created_at "
                "FROM memory_entries WHERE source_type = ? AND source_id = ?",
                (entry.source_type, entry.source_id),
            ).fetchone()

            if existing:
                entry.memory_id = existing[0]
                entry.lifecycle_state = existing[1]
                entry.importance = existing[2]
                entry.access_count = existing[3]
                entry.created_at = existing[4]

                conn.execute(
                    """
                    UPDATE memory_entries SET
                        content = ?, category = ?, metadata = ?, confidence = ?,
                        tags = ?, updated_at = ?, provenance = ?,
                        lineage = ?, relationships = ?, project = ?, skill = ?
                    WHERE memory_id = ?
                """,
                    (
                        entry.content,
                        entry.category,
                        json.dumps(entry.metadata) if entry.metadata else None,
                        entry.confidence,
                        json.dumps(entry.tags) if entry.tags else None,
                        now,
                        json.dumps(entry.provenance) if entry.provenance else None,
                        json.dumps(entry.lineage) if entry.lineage else None,
                        json.dumps(entry.relationships) if entry.relationships else None,
                        entry.project,
                        entry.skill,
                        entry.memory_id,
                    ),
                )
                return entry.memory_id

            if not entry.memory_id:
                entry.memory_id = str(uuid4())
            if not entry.created_at:
                entry.created_at = now

            return self.store(entry)

    # ── Retrieval ────────────────────────────────────────────────────────────

    def retrieve(self, query: MemoryQuery) -> List[RetrievalResult]:
        """Retrieve memories with relevance ranking."""
        sql = "SELECT * FROM memory_entries WHERE 1=1"
        params: list = []

        if query.memory_type:
            sql += " AND source = ?"
            params.append(query.memory_type)
        if query.category:
            sql += " AND category = ?"
            params.append(query.category)
        if query.project:
            sql += " AND (project = ? OR project IS NULL)"
            params.append(query.project)
        if query.skill:
            sql += " AND (skill = ? OR skill IS NULL)"
            params.append(query.skill)
        if query.min_importance > 0:
            sql += " AND importance >= ?"
            params.append(query.min_importance)
        if query.tags:
            for tag in query.tags:
                sql += " AND tags LIKE ?"
                params.append(f"%{tag}%")
        if query.lifecycle_states:
            placeholders = ",".join("?" for _ in query.lifecycle_states)
            sql += f" AND lifecycle_state IN ({placeholders})"
            params.extend(query.lifecycle_states)
        else:
            _defaults = ", ".join(f"'{s}'" for s in _DEFAULT_RETRIEVE_STATES)
            sql += f" AND lifecycle_state IN ({_defaults})"

        sql += " ORDER BY importance DESC, created_at DESC"
        sql += f" LIMIT {query.limit * 3}"

        with get_connection(read_only=True) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, params).fetchall()

        results: List[RetrievalResult] = []
        now = datetime.now(timezone.utc)

        for row in rows:
            entry = self._row_to_entry(row)
            half_life = DECAY_HALF_LIVES.get(entry.memory_type, self.DEFAULT_HALF_LIFE)

            try:
                base = entry.last_accessed or entry.created_at
                base_dt = datetime.fromisoformat(base.replace("Z", "+00:00"))
                age_days = (now - base_dt).total_seconds() / 86400
            except (ValueError, TypeError):
                age_days = 365.0

            temporal_weight = math.exp(-0.693 * age_days / half_life)

            text_score = 0.0
            if query.text and entry.content:
                terms = query.text.lower().split()
                content_lower = entry.content.lower()
                matches = sum(1 for t in terms if t in content_lower)
                text_score = matches / max(len(terms), 1)

            access_boost = min(math.log(entry.access_count + 1) / 5, 1.0)
            recency_boost = max(0.0, 1.0 - age_days / 7.0) if age_days < 7 else 0.0

            relevance = (
                entry.importance * 0.30
                + temporal_weight * 0.25
                + text_score * 0.25
                + access_boost * 0.10
                + recency_boost * 0.10
            )

            if not query.include_decayed and temporal_weight < 0.1:
                continue

            reason_parts = []
            if text_score > 0:
                reason_parts.append(f"text_match={text_score:.2f}")
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
        return results[: query.limit]

    # ── Lifecycle management ─────────────────────────────────────────────────

    def transition(self, memory_id: str, new_state: str) -> None:
        """Transition a memory entry to a new lifecycle state.

        Raises ValueError on invalid transition.
        """
        if not LIFECYCLE_CATALOG.validate_state("memory", new_state):
            raise ValueError(f"Invalid state: {new_state}")

        with transaction() as conn:
            row = conn.execute(
                "SELECT lifecycle_state FROM memory_entries WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
            if not row:
                raise ValueError(f"Memory {memory_id} not found")

            current = row[0]
            if not LIFECYCLE_CATALOG.validate_transition("memory", current, new_state):
                raise ValueError(f"Invalid transition: {current} -> {new_state}.")

            conn.execute(
                "UPDATE memory_entries SET lifecycle_state = ?, updated_at = ? WHERE memory_id = ?",
                (new_state, datetime.now(timezone.utc).isoformat(), memory_id),
            )

    def record_access(self, memory_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with transaction() as conn:
            conn.execute(
                """
                UPDATE memory_entries SET
                    last_accessed = ?,
                    access_count = access_count + 1,
                    updated_at = ?
                WHERE memory_id = ?
            """,
                (now, now, memory_id),
            )

    def boost_importance(self, memory_id: str, delta: float = 0.1) -> None:
        with transaction() as conn:
            conn.execute(
                """
                UPDATE memory_entries SET
                    importance = MIN(1.0, importance + ?),
                    updated_at = ?
                WHERE memory_id = ?
            """,
                (delta, datetime.now(timezone.utc).isoformat(), memory_id),
            )

    def decay_importance(self, memory_id: str, delta: float = 0.1) -> None:
        with transaction() as conn:
            conn.execute(
                """
                UPDATE memory_entries SET
                    importance = MAX(0.0, importance - ?),
                    updated_at = ?
                WHERE memory_id = ?
            """,
                (delta, datetime.now(timezone.utc).isoformat(), memory_id),
            )

    # ── Convenience ingest methods ───────────────────────────────────────────

    def ingest_lesson(
        self,
        lesson_path: str,
        content: str,
        skill: Optional[str] = None,
        project: Optional[str] = None,
        source_id: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> str:
        """Ingest a lesson into memory via canonical API."""
        tags = _auto_tags(content)
        now = datetime.now(timezone.utc).isoformat()

        entry = MemoryEntry(
            memory_id=str(uuid4()),
            memory_type="lesson",
            category=_infer_category(content),
            content=content[:2000],
            source_type="filesystem" if not source_id else "raw_lessons",
            source_id=source_id or lesson_path,
            lifecycle_state=to_db_value(MemoryLifecycle.DRAFT),
            metadata={"file_path": lesson_path},
            importance=0.6,
            confidence=confidence,
            tags=tags,
            project=project,
            skill=skill,
            provenance={
                "source_type": "filesystem" if not source_id else "raw_lessons",
                "source_id": source_id or lesson_path,
                "ingested_at": now,
                "ingested_by": "MemoryStore.ingest_lesson",
                "original_timestamp": now,
            },
        )

        if source_id:
            return self.upsert_by_provenance(entry)
        return self.store(entry)

    def ingest_gotcha(
        self,
        title: str,
        fix: str,
        severity: str,
        skill: Optional[str] = None,
        source_id: Optional[str] = None,
    ) -> str:
        importance = {"critical": 0.95, "high": 0.8, "medium": 0.6, "low": 0.4}.get(
            severity.lower(), 0.5
        )
        now = datetime.now(timezone.utc).isoformat()

        entry = MemoryEntry(
            memory_id=str(uuid4()),
            memory_type="gotcha",
            category="known_issue",
            content=f"{title}\nFix: {fix}",
            source_type="reg_gotchas" if source_id else "unknown",
            source_id=source_id or "",
            lifecycle_state=to_db_value(MemoryLifecycle.PROMOTED),
            importance=importance,
            confidence=1.0,
            tags=["gotcha", severity.lower()],
            skill=skill,
            provenance={
                "source_type": "reg_gotchas" if source_id else "unknown",
                "source_id": source_id or "",
                "ingested_at": now,
                "ingested_by": "MemoryStore.ingest_gotcha",
                "original_timestamp": now,
            },
        )

        if source_id:
            return self.upsert_by_provenance(entry)
        return self.store(entry)

    def ingest_decision(
        self,
        decision_type: str,
        outcome: str,
        reasoning: str,
        confidence: float,
        subsystem: str,
        source_id: Optional[str] = None,
    ) -> str:
        now = datetime.now(timezone.utc).isoformat()

        entry = MemoryEntry(
            memory_id=str(uuid4()),
            memory_type="decision",
            category=decision_type,
            content=f"Decision: {outcome}\nReasoning: {reasoning}",
            source_type="canonical_events" if source_id else "unknown",
            source_id=source_id or "",
            lifecycle_state=to_db_value(MemoryLifecycle.PROMOTED),
            metadata={"subsystem": subsystem},
            importance=0.5 + (confidence * 0.3),
            confidence=confidence,
            tags=["decision", subsystem],
            provenance={
                "source_type": "canonical_events" if source_id else "unknown",
                "source_id": source_id or "",
                "ingested_at": now,
                "ingested_by": "MemoryStore.ingest_decision",
                "original_timestamp": now,
            },
        )

        if source_id:
            return self.upsert_by_provenance(entry)
        return self.store(entry)

    # ── Stats ────────────────────────────────────────────────────────────────

    def stats(self) -> Dict[str, Any]:
        with get_connection(read_only=True) as conn:
            total = conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()[0]
            by_type = {}
            for row in conn.execute("SELECT source, COUNT(*) FROM memory_entries GROUP BY source"):
                by_type[row[0]] = row[1]
            by_state = {}
            for row in conn.execute(
                "SELECT lifecycle_state, COUNT(*) FROM memory_entries GROUP BY lifecycle_state"
            ):
                by_state[row[0]] = row[1]
            by_source = {}
            for row in conn.execute(
                "SELECT source_type, COUNT(*) FROM memory_entries GROUP BY source_type"
            ):
                by_source[row[0]] = row[1]
            avg_importance = conn.execute("SELECT AVG(importance) FROM memory_entries").fetchone()[
                0
            ]
        return {
            "total_entries": total,
            "by_memory_type": by_type,
            "by_lifecycle_state": by_state,
            "by_source_type": by_source,
            "avg_importance": round(avg_importance or 0, 3),
        }

    def get_entry(self, memory_id: str) -> Optional[MemoryEntry]:
        with get_connection(read_only=True) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM memory_entries WHERE memory_id = ?", (memory_id,)
            ).fetchone()
            if not row:
                return None
            return self._row_to_entry(row)

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _row_to_entry(row) -> MemoryEntry:
        return MemoryEntry(
            memory_id=row["memory_id"],
            memory_type=row["source"],
            category=row["category"],
            content=row["content"],
            source_type=row["source_type"] if "source_type" in row.keys() else "unknown",
            source_id=row["source_id"] if "source_id" in row.keys() else "",
            lifecycle_state=row["lifecycle_state"] if "lifecycle_state" in row.keys() else "ACTIVE",
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            importance=row["importance"],
            confidence=row["confidence"] if "confidence" in row.keys() else None,
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] if "updated_at" in row.keys() else "",
            last_accessed=row["last_accessed"] or "",
            access_count=row["access_count"],
            tags=json.loads(row["tags"]) if row["tags"] else [],
            project=row["project"],
            skill=row["skill"],
            provenance=json.loads(row["provenance"]) if _col(row, "provenance") else {},
            lineage=json.loads(row["lineage"]) if _col(row, "lineage") else {},
            relationships=json.loads(row["relationships"]) if _col(row, "relationships") else [],
        )


def _col(row, name):
    """Safely get a column value from a sqlite3.Row, returning None if missing."""
    try:
        val = row[name]
        return val
    except (IndexError, KeyError):
        return None


def _auto_tags(content: str) -> List[str]:
    tags = []
    cl = content.lower()
    if "security" in cl:
        tags.append("security")
    if "debug" in cl:
        tags.append("debugging")
    if "performance" in cl or "optimize" in cl:
        tags.append("performance")
    return tags


def _infer_category(content: str) -> str:
    cl = content.lower()
    if any(w in cl for w in ("security", "vulnerability", "auth")):
        return "security"
    if any(w in cl for w in ("architecture", "refactor", "design")):
        return "architecture"
    if any(w in cl for w in ("debug", "fix", "error", "bug")):
        return "debugging"
    if any(w in cl for w in ("workflow", "pipeline", "deploy")):
        return "workflow"
    if any(w in cl for w in ("skill", "mode", "routing")):
        return "skill_routing"
    return "general"
