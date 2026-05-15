"""SQLite-first shared intelligence authority helpers."""

from core.shared_intelligence.authority import (
    REQUIRED_SHARED_INTELLIGENCE_TABLES,
    build_adapter_context_packet,
    record_adapter_authority_profile,
    record_adapter_result,
    record_artifact_authority,
    record_capability_route,
    record_hardening_candidate,
    record_learning_event,
    record_model_provider_profile,
    record_shared_context_packet,
    require_shared_intelligence_tables,
)
from core.shared_intelligence.adapter_alignment import (
    adapter_alignment_summary,
    adapter_projection_policy,
    default_adapter_authority_profiles,
    register_default_adapter_authority_profiles,
)
from core.shared_intelligence.adapter_config_projection import (
    adapter_config_projection,
    adapter_config_projection_report,
    validate_adapter_config_projection_report,
)
from core.shared_intelligence.adapter_staleness import (
    adapter_staleness_report,
    validate_adapter_staleness_report,
)
from core.shared_intelligence.agent_independence import (
    agent_model_independence_validation,
    validate_agent_model_independence_report,
)
from core.shared_intelligence.capability_routing import (
    capability_route_summary,
    recommend_capability_route,
)
from core.shared_intelligence.capability_center import (
    capability_center_summary,
    validate_capability_center_summary,
)
from core.shared_intelligence.context_packets import (
    generate_shared_context_packet,
    shared_context_packet_policy,
)
from core.shared_intelligence.convergence import (
    adapter_surface_classification,
    independent_configuration_matrix,
    legacy_source_classification,
)
from core.shared_intelligence.dashboard_views import (
    learning_hardening_dashboard_view,
    validate_learning_hardening_dashboard_view,
)
from core.shared_intelligence.feedback_loop import cross_model_learning_feedback
from core.shared_intelligence.github_repo_intake import (
    github_repo_intake_dashboard_summary,
    github_repo_intake_workflow,
    validate_github_repo_intake_workflow,
)
from core.shared_intelligence.hardening_loop import (
    create_hardening_candidate_from_learning_event,
    hardening_candidate_lifecycle,
    record_hardening_validation,
    validate_hardening_loop_report,
)
from core.shared_intelligence.model_registry import (
    model_provider_capability_matrix,
    model_provider_registry_policy,
    model_provider_registry_summary,
)
from core.shared_intelligence.multi_agent_demo import (
    multi_agent_shared_intelligence_demo_packet,
    validate_multi_agent_shared_intelligence_demo_packet,
)
from core.shared_intelligence.promotion_policy import (
    learning_promotion_decision,
    learning_promotion_policy_report,
)
from core.shared_intelligence.read_models import (
    component_learning_health,
    learning_event_summary,
    learning_promotion_queue,
)
from core.shared_intelligence.result_normalization import (
    adapter_result_summary,
    normalize_adapter_result_payload,
    record_normalized_adapter_result,
)
from core.shared_intelligence.skill_versioning import (
    skill_version_evaluation_policy,
    skill_version_evaluation_report,
    validate_skill_version_evaluation_report,
)
from core.shared_intelligence.scoped_agents import (
    scoped_agent_registry,
    scoped_context_packet,
    validate_scoped_agent_registry,
)
from core.shared_intelligence.usage_accounting import (
    adapter_usage_accounting_summary,
    record_adapter_accounting_profile,
    record_ai_usage_operational_record,
    register_default_adapter_accounting_profiles,
)

__all__ = [
    "REQUIRED_SHARED_INTELLIGENCE_TABLES",
    "build_adapter_context_packet",
    "record_adapter_authority_profile",
    "record_adapter_result",
    "record_artifact_authority",
    "record_capability_route",
    "record_hardening_candidate",
    "record_learning_event",
    "record_model_provider_profile",
    "record_shared_context_packet",
    "require_shared_intelligence_tables",
    "capability_route_summary",
    "recommend_capability_route",
    "capability_center_summary",
    "validate_capability_center_summary",
    "generate_shared_context_packet",
    "shared_context_packet_policy",
    "adapter_surface_classification",
    "independent_configuration_matrix",
    "legacy_source_classification",
    "learning_hardening_dashboard_view",
    "validate_learning_hardening_dashboard_view",
    "cross_model_learning_feedback",
    "github_repo_intake_dashboard_summary",
    "github_repo_intake_workflow",
    "validate_github_repo_intake_workflow",
    "adapter_alignment_summary",
    "adapter_projection_policy",
    "default_adapter_authority_profiles",
    "register_default_adapter_authority_profiles",
    "adapter_config_projection",
    "adapter_config_projection_report",
    "validate_adapter_config_projection_report",
    "adapter_staleness_report",
    "validate_adapter_staleness_report",
    "agent_model_independence_validation",
    "validate_agent_model_independence_report",
    "create_hardening_candidate_from_learning_event",
    "hardening_candidate_lifecycle",
    "record_hardening_validation",
    "validate_hardening_loop_report",
    "model_provider_capability_matrix",
    "model_provider_registry_policy",
    "model_provider_registry_summary",
    "multi_agent_shared_intelligence_demo_packet",
    "validate_multi_agent_shared_intelligence_demo_packet",
    "learning_promotion_decision",
    "learning_promotion_policy_report",
    "component_learning_health",
    "learning_event_summary",
    "learning_promotion_queue",
    "adapter_result_summary",
    "normalize_adapter_result_payload",
    "record_normalized_adapter_result",
    "skill_version_evaluation_policy",
    "skill_version_evaluation_report",
    "validate_skill_version_evaluation_report",
    "scoped_agent_registry",
    "scoped_context_packet",
    "validate_scoped_agent_registry",
    "adapter_usage_accounting_summary",
    "record_adapter_accounting_profile",
    "record_ai_usage_operational_record",
    "register_default_adapter_accounting_profiles",
]
