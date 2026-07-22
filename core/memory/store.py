"""Canonical memory store — unified retrieval across all knowledge sources —
facade over the split modules.

ALL LONG-TERM SEMANTIC MEMORY CONVERGES INTO memory_entries.

Other systems are ingestion sources, lifecycle stages, or retrieval indexes.
memory_entries is the canonical semantic memory authority.

Memory entries are stored in SQLite with importance scoring, temporal decay,
lifecycle state management, and provenance tracking.

WO-GF-CORE-DATA-split: implementation moved to store_{shared,main}.py; this
module re-exports the public API so existing
`from core.memory.store import X` callers are unchanged.
"""

from __future__ import annotations

from .store_shared import (
    DECAY_HALF_LIVES,
    MemoryEntry,
    MemoryQuery,
    RetrievalResult,
    VALID_MEMORY_TYPES,
    VALID_SOURCE_TYPES,
    _DEFAULT_RETRIEVE_STATES,
)
from .store_main import (
    MemoryStore,
    _auto_tags,
    _col,
    _infer_category,
)

__all__ = [
    "DECAY_HALF_LIVES",
    "MemoryEntry",
    "MemoryQuery",
    "MemoryStore",
    "RetrievalResult",
    "VALID_MEMORY_TYPES",
    "VALID_SOURCE_TYPES",
    "_DEFAULT_RETRIEVE_STATES",
    "_auto_tags",
    "_col",
    "_infer_category",
]
