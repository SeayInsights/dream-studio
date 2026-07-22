"""Web research module with confidence scoring and source triangulation.

Provides multi-source research capabilities with tier-based trust scoring.

WO-GF-CONTROL-INSTALL-split: implementation moved to web_{shared,scoring,
search,cache}.py; this module re-exports the public+private surface so
existing `from control.research.web import X` callers are unchanged.
"""

from __future__ import annotations

from .web_cache import get_connection, transaction  # noqa: F401 — pre-split passthrough
from .web_cache import (
    _emit_research_cache_telemetry,
    _source_from_cache_dict,
    _source_to_cache_dict,
    delete_from_cache_by_id,
    invalidate_cache,
    load_from_cache,
    load_from_cache_by_id,
    save_to_cache,
)
from .web_scoring import (
    _get_source_tier,
    calculate_confidence,
    calculate_triangulation,
    extract_sources,
    summarize_findings,
)
from .web_search import _check_performance, research_topic, search_jina, search_web
from .web_shared import ResearchReport, Source, _emit_metric

__all__ = [
    "ResearchReport",
    "Source",
    "_check_performance",
    "_emit_metric",
    "_emit_research_cache_telemetry",
    "_get_source_tier",
    "_source_from_cache_dict",
    "_source_to_cache_dict",
    "calculate_confidence",
    "calculate_triangulation",
    "delete_from_cache_by_id",
    "extract_sources",
    "invalidate_cache",
    "load_from_cache",
    "load_from_cache_by_id",
    "research_topic",
    "save_to_cache",
    "search_jina",
    "search_web",
    "summarize_findings",
]
