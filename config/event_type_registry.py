"""Event type routing registry for the v2 dual canonical architecture.

Declares routes_to for every known event_type. The ingestor reads this at
ingest time to decide which canonical table(s) to write to.

Routing destinations:
  ("business",)        → business_canonical_events only
  ("ai",)              → ai_canonical_events only
  ("business", "ai")   → both canonicals, linked by correlation_id
  ()                   → raw only (Commitment 9: mechanical detail)

Event-presence rule (data-model-v2.md):
  Pure operator actions with no AI involvement → business only
  AI mechanical work with no business outcome  → ai only
  AI-driven work producing a business artifact → both (paired)
  Individual tool calls / mechanical detail    → raw only

WO-GF-EVENT-TAXONOMY-SPLIT: implementation moved to event_type_registry_{shared,
entries_business,entries_ai,entries_other,data,queries}.py; this module
re-exports the public and private surface so existing
`from config.event_type_registry import X` callers are unchanged.
"""

from __future__ import annotations

from .event_type_registry_data import _ENTRIES, _REGISTRY
from .event_type_registry_queries import all_entries, get_entry, get_routes, is_registered
from .event_type_registry_shared import RegistryEntry, _AI, _BOTH, _BUSINESS, _RAW_ONLY

__all__ = [
    "RegistryEntry",
    "_AI",
    "_BOTH",
    "_BUSINESS",
    "_ENTRIES",
    "_RAW_ONLY",
    "_REGISTRY",
    "all_entries",
    "get_entry",
    "get_routes",
    "is_registered",
]
