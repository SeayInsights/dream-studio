"""Insights API routes — facade.

WO-GF-API-ROUTES: implementation moved to insights_{router,shared,core,rhythm,
diagnostics}.py; this module imports every group sibling (in original
top-to-bottom order) so their handlers decorate the shared `router`, then
re-exports the full prior public surface so existing
`from projections.api.routes.insights import X` callers are unchanged.
"""

from __future__ import annotations

from .insights_router import router
from .insights_shared import get_db_path, collect_metrics, analyze_metrics
from .insights_core import (
    get_all_insights,
    get_strengths,
    get_issues,
    get_opportunities,
    get_risks,
    get_high_priority,
    get_recommendations,
    analyze_root_cause,
)
from .insights_rhythm import get_work_rhythm
from .insights_diagnostics import (
    get_attribution_coverage,
    get_attribution_orphans,
    get_memory_surface,
    get_attribution_breakouts,
)

__all__ = [
    "router",
    "get_db_path",
    "collect_metrics",
    "analyze_metrics",
    "get_all_insights",
    "get_strengths",
    "get_issues",
    "get_opportunities",
    "get_risks",
    "get_high_priority",
    "get_recommendations",
    "analyze_root_cause",
    "get_work_rhythm",
    "get_attribution_coverage",
    "get_attribution_orphans",
    "get_memory_surface",
    "get_attribution_breakouts",
]
