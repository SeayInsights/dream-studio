"""Intelligence API - converts raw metrics to actionable insights — facade.

Provides tier-based intelligence for the dashboard:
- Tier 1: Critical issues needing immediate attention
- Tier 2: Health snapshot + positive signals (wins)
- Tier 3: Detailed metrics (served by existing routes)

All intelligence rules are data-driven with explicit thresholds.

WO-GF-API-ROUTES: implementation moved to intelligence_{router,overview,
domains,workflow_patterns,friction}.py; this module imports every group
sibling (in original top-to-bottom order, to preserve FastAPI route
registration order — friction-signals/classifications before
friction-signals/{signal_id}) so their handlers decorate the shared
`router`, then re-exports the full prior public+private surface so existing
`from projections.api.routes.intelligence import X` callers are unchanged.
"""

from __future__ import annotations

from .intelligence_router import router
from .intelligence_overview import (
    get_cost_alerts,
    get_reliability_alerts,
    get_performance_alerts,
    get_critical_issues,
    get_health_snapshot,
    get_whats_working,
    get_overview,
)
from .intelligence_domains import (
    get_token_intelligence,
    get_agent_capabilities,
    get_architecture_intelligence,
    get_system_controls_intelligence,
)
from .intelligence_workflow_patterns import (
    get_workflow_patterns,
    suppress_workflow_pattern,
    run_workflow_pattern_analysis,
)
from .intelligence_friction import (
    _friction_table_missing,
    list_friction_signals,
    get_friction_classifications,
    get_friction_signal,
)

__all__ = [
    "router",
    "get_cost_alerts",
    "get_reliability_alerts",
    "get_performance_alerts",
    "get_critical_issues",
    "get_health_snapshot",
    "get_whats_working",
    "get_overview",
    "get_token_intelligence",
    "get_agent_capabilities",
    "get_architecture_intelligence",
    "get_system_controls_intelligence",
    "get_workflow_patterns",
    "suppress_workflow_pattern",
    "run_workflow_pattern_analysis",
    "_friction_table_missing",
    "list_friction_signals",
    "get_friction_classifications",
    "get_friction_signal",
]
