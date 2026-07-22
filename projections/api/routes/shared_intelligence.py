"""Shared-intelligence authority API routes — facade.

These routes expose dashboard-consumable read models over SQLite authority.
They deliberately do not write adapter configs, persist generated context
packets, mutate routing policy, or authorize execution.

WO-GF-API-ROUTES: implementation moved to shared_intelligence_{router,shared,
capability,platform,learning,routing,attribution}.py; this module imports
every group sibling (capability, platform, learning, routing, attribution —
in original top-to-bottom order, none of the route paths overlap so
registration order is not otherwise significant here) so their handlers
decorate the shared `router`, then re-exports the full prior public+private
surface so existing `from projections.api.routes.shared_intelligence import X`
callers are unchanged.
"""

from __future__ import annotations

from .shared_intelligence_router import router
from .shared_intelligence_shared import _with_connection, _dashboard_response, _split_query_list
from .shared_intelligence_capability import (
    get_shared_intelligence_status,
    get_analytics_only_status,
    get_module_contracts,
    get_expert_workflow_catalog,
    get_capability_center,
    get_scoped_agent_registry,
    preview_scoped_agent_context_packet,
    get_github_repo_intake,
)
from .shared_intelligence_platform import (
    get_platform_hardening,
    get_skill_evaluation_harness,
    preview_policy_decision,
    get_connector_ingestion_framework,
    get_adapter_router_status,
    get_security_lifecycle_status,
    get_production_readiness_status,
    get_production_readiness_controls,
)
from .shared_intelligence_learning import (
    get_learning_dashboard,
    get_adapter_projection_report,
    get_adapter_staleness_report,
    preview_context_packet,
)
from .shared_intelligence_routing import (
    preview_capability_route,
    get_model_provider_summary,
    get_model_provider_capability_matrix,
    get_ai_usage_accounting,
)
from .shared_intelligence_attribution import (
    get_task_attribution,
    get_work_order_task_attribution,
    get_contract_atlas,
    get_contract_atlas_maturity_ledger,
    get_contract_atlas_docs_drift,
    get_contract_atlas_freshness,
)

__all__ = [
    "router",
    "_with_connection",
    "_dashboard_response",
    "_split_query_list",
    "get_shared_intelligence_status",
    "get_analytics_only_status",
    "get_module_contracts",
    "get_expert_workflow_catalog",
    "get_capability_center",
    "get_scoped_agent_registry",
    "preview_scoped_agent_context_packet",
    "get_github_repo_intake",
    "get_platform_hardening",
    "get_skill_evaluation_harness",
    "preview_policy_decision",
    "get_connector_ingestion_framework",
    "get_adapter_router_status",
    "get_security_lifecycle_status",
    "get_production_readiness_status",
    "get_production_readiness_controls",
    "get_learning_dashboard",
    "get_adapter_projection_report",
    "get_adapter_staleness_report",
    "preview_context_packet",
    "preview_capability_route",
    "get_model_provider_summary",
    "get_model_provider_capability_matrix",
    "get_ai_usage_accounting",
    "get_task_attribution",
    "get_work_order_task_attribution",
    "get_contract_atlas",
    "get_contract_atlas_maturity_ledger",
    "get_contract_atlas_docs_drift",
    "get_contract_atlas_freshness",
]
