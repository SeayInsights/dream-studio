"""Expert workflow catalog schema constants and boundary tuples.

WO-GF-SHARED-INTEL-SPLIT: extracted from expert_workflows.py.
"""

from __future__ import annotations

EXPERT_WORKFLOW_CATALOG_SCHEMA = "dream_studio.expert_workflows.v1"

DECISION_VALUES = frozenset(
    {
        "keep_existing",
        "strengthen_existing",
        "split_existing",
        "merge_duplicate",
        "create_new",
        "supersede_existing",
        "deprecate_existing",
        "manual_review_required",
    }
)

REQUIRED_WORKFLOW_IDS = frozenset(
    {
        "intentional_implementation_workflow",
        "code_quality_architecture_workflow",
        "root_cause_debugging_workflow",
        "performance_efficiency_workflow",
        "frontend_design_excellence_workflow",
        "seo_content_growth_workflow",
        "documentation_quality_workflow",
        "data_modeling_authority_workflow",
        "api_integration_design_workflow",
        "product_demo_and_case_study_workflow",
    }
)

DESIGN_SPECIALIZED_SKILLS = (
    "product_ux_review",
    "information_architecture_review",
    "visual_design_system_review",
    "responsive_layout_review",
    "component_architecture_review",
    "accessibility_review",
    "interaction_motion_review",
    "data_visualization_review",
    "implementation_feasibility_review",
    "design_to_code_contract",
)

APPLICATION_AUTOMATION_BOUNDARIES = (
    "do_not_create_accounts",
    "do_not_bypass_captchas",
    "do_not_misrepresent_operator",
    "do_not_submit_without_explicit_approval_or_policy",
    "pause_on_ambiguous_questions",
    "store_sensitive_fields_only_in_approved_private_storage",
    "do_not_print_secrets_or_private_identifiers_unnecessarily",
    "record_filled_skipped_and_operator_input_needed",
)

AUTHORITY_WRITE_TARGETS = (
    "workflow_invocations",
    "skill_invocations",
    "research_evidence_records",
    "validation_results",
    # artifact_records: dropped migration 130
    # decision_records + dashboard_attention_items: dropped migration 139 (WO-AI-SPINE, AD-5)
    "work_order_records",
)
