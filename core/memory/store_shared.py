"""Shared dataclasses and constants for the canonical memory store.

WO-GF-CORE-DATA-split: split from core/memory/store.py into
store_{shared,main}.py; core/memory/store.py is now a thin facade
re-exporting the public API.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from core.ontology.lifecycles import MemoryLifecycle, to_db_value

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
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5  # 0.0-1.0
    confidence: float | None = None  # 0.0-1.0
    created_at: str = ""
    updated_at: str = ""
    last_accessed: str = ""
    access_count: int = 0
    tags: list[str] = field(default_factory=list)
    project: str | None = None
    skill: str | None = None
    provenance: dict[str, Any] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
    relationships: list[dict[str, Any]] = field(default_factory=list)
    embedding: list[float] | None = None


@dataclass
class MemoryQuery:
    text: str | None = None
    memory_type: str | None = None
    category: str | None = None
    tags: list[str] | None = None
    project: str | None = None
    skill: str | None = None
    min_importance: float = 0.0
    limit: int = 10
    include_decayed: bool = False
    lifecycle_states: list[str] | None = None


@dataclass
class RetrievalResult:
    entry: MemoryEntry
    relevance_score: float
    match_reason: str
