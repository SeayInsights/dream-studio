"""Contract Atlas confirmed dependency graph builder.

WO-GF-SHARED-INTEL-SPLIT: extracted from contract_atlas.py.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.module_contracts import module_contracts
from core.telemetry.docker_profiles import DOCKER_MODULE_PROFILES
from core.telemetry.execution_spine import DASHBOARD_MODULES

from .contract_atlas_sections import _layer_contracts


def _confirmed_dependency_graph(
    *,
    projection_report: Mapping[str, Any],
    staleness_report: Mapping[str, Any],
    security_lifecycle_gate: Mapping[str, Any],
    production_readiness_gate: Mapping[str, Any],
    usage_accounting: Mapping[str, Any],
    task_attribution: Mapping[str, Any],
    prd_authority: Mapping[str, Any],
    analytics_only_status: Mapping[str, Any],
    github_cicd_profile: Mapping[str, Any],
    expert_workflows: Mapping[str, Any],
    capability_center: Mapping[str, Any],
    scoped_agents: Mapping[str, Any],
    github_repo_intake: Mapping[str, Any],
    platform_hardening: Mapping[str, Any],
) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def add_node(node_id: str, node_type: str, label: str) -> None:
        nodes.setdefault(node_id, {"id": node_id, "type": node_type, "label": label})

    def add_edge(source: str, target: str, relation: str, evidence: str) -> None:
        edges.append(
            {
                "source": source,
                "target": target,
                "relation": relation,
                "edge_status": "confirmed",
                "source_evidence": evidence,
            }
        )

    add_node("system:dream-studio", "system", "Dream Studio")
    for layer in _layer_contracts():
        layer_id = f"layer:{layer['layer_id']}"
        add_node(layer_id, "layer", layer["role"])
        add_edge(
            "system:dream-studio", layer_id, "contains_layer", "contract_atlas.layer_contracts"
        )

    for contract in module_contracts()["contracts"]:
        module_id = f"module:{contract['module_id']}"
        add_node(module_id, "module", contract["module_id"])
        add_edge(
            "system:dream-studio",
            module_id,
            "declares_module_contract",
            "core.module_contracts.MODULE_CONTRACTS",
        )
        for table in contract.get("owned_tables", []):
            table_id = f"table:{table}"
            add_node(table_id, "sqlite_table", str(table))
            add_edge(
                module_id,
                table_id,
                "owns_or_writes_authority",
                "core.module_contracts.MODULE_CONTRACTS",
            )

    for module in DASHBOARD_MODULES:
        module_id = f"module:{module['module_id']}"
        add_node(module_id, "module", module["module_name"])
        add_edge(
            "layer:telemetry_read_models",
            module_id,
            "declares_module",
            "core.telemetry.execution_spine.DASHBOARD_MODULES",
        )
        for table in module["source_tables"]:
            table_id = f"table:{table}"
            add_node(table_id, "sqlite_table", table)
            add_edge(
                module_id,
                table_id,
                "reads_source_table",
                "core.telemetry.execution_spine.DASHBOARD_MODULES",
            )
        if module.get("docker_profile"):
            profile_id = f"runtime:{module['docker_profile']}"
            add_node(profile_id, "runtime_profile", str(module["docker_profile"]))
            add_edge(
                module_id,
                profile_id,
                "optional_runtime_profile",
                "core.telemetry.execution_spine.DASHBOARD_MODULES",
            )

    for profile in DOCKER_MODULE_PROFILES:
        profile_id = f"runtime:{profile['profile']}"
        add_node(profile_id, "runtime_profile", profile["profile"])
        add_edge(
            "layer:runtime_profiles",
            profile_id,
            "declares_optional_profile",
            "core.telemetry.docker_profiles.DOCKER_MODULE_PROFILES",
        )

    add_node("module:security_lifecycle_gate", "module", "Security Lifecycle Gate")
    add_node(
        "contract:47_enterprise_security_controls",
        "contract",
        "47 Enterprise Security Controls",
    )
    add_node(
        "doc:docs/contracts/security-review-scan-catalog.yaml",
        "contract_doc",
        "Security Review Scan Catalog",
    )
    add_edge(
        "module:security_lifecycle_gate",
        "contract:47_enterprise_security_controls",
        "implements_control_framework",
        "core.security.lifecycle.build_security_lifecycle_gate",
    )
    add_edge(
        "contract:47_enterprise_security_controls",
        "doc:docs/contracts/security-review-scan-catalog.yaml",
        "mapped_by_catalog",
        str(security_lifecycle_gate.get("source_framework", {}).get("catalog_ref")),
    )
    add_node("module:production_readiness_workflow", "module", "Production Readiness Workflow")
    add_node(
        "contract:secure_production_readiness_gate",
        "contract",
        "Secure Production Readiness Gate",
    )
    add_edge(
        "module:production_readiness_workflow",
        "contract:secure_production_readiness_gate",
        "implements_readiness_gate",
        "core.production_readiness.controls.build_secure_production_readiness_gate",
    )
    add_edge(
        "module:production_readiness_workflow",
        "module:security_lifecycle_gate",
        "requires_security_lifecycle",
        str(production_readiness_gate.get("workflow_id")),
    )
    add_node("module:ai_usage_accounting", "module", "AI Usage Accounting")
    for table in usage_accounting.get("source_tables", []):
        table_id = f"table:{table}"
        add_node(table_id, "sqlite_table", str(table))
        add_edge(
            "module:ai_usage_accounting",
            table_id,
            "reads_source_table",
            "core.shared_intelligence.usage_accounting.adapter_usage_accounting_summary",
        )

    add_node("module:task_attribution_outcome_tracking", "module", "Task Attribution")
    add_edge(
        "module:task_attribution_outcome_tracking",
        "module:ai_usage_accounting",
        "feeds_adapter_usage_outcomes",
        "core.shared_intelligence.task_attribution.task_attribution_summary",
    )
    for table in task_attribution.get("source_tables", []):
        table_id = f"table:{table}"
        add_node(table_id, "sqlite_table", str(table))
        add_edge(
            "module:task_attribution_outcome_tracking",
            table_id,
            "reads_or_links_source_table",
            "core.shared_intelligence.task_attribution.TASK_ATTRIBUTION_SOURCE_TABLES",
        )

    add_node("module:analytics_only_ingestion", "module", "Analytics-Only Ingestion")
    for table in analytics_only_status.get("source_tables", []):
        table_id = f"table:{table}"
        add_node(table_id, "sqlite_table", str(table))
        add_edge(
            "module:analytics_only_ingestion",
            table_id,
            "imports_or_reads_current_authority",
            "core.analytics_ingestion.analytics_only_ingestion_contract",
        )

    add_node("module:github_cicd_profile", "module", "GitHub CI/CD Profile")
    add_node("workflow:pr-smoke", "github_workflow", "PR Smoke")
    add_node("workflow:full-ci", "github_workflow", "Manual Full CI")
    add_node("workflow:release-validation", "github_workflow", "Release Validation")
    add_edge(
        "module:github_cicd_profile",
        "workflow:pr-smoke",
        "requires_lightweight_remote_confidence",
        "core.release.github_pr_cicd_gate.build_dream_studio_cicd_profile",
    )
    add_edge(
        "module:github_cicd_profile",
        "workflow:full-ci",
        "manual_heavy_validation",
        str(github_cicd_profile.get("heavy_validation_layer")),
    )
    add_edge(
        "module:github_cicd_profile",
        "workflow:release-validation",
        "manual_or_tag_release_validation",
        "runtime/config/release-gates/dream-studio.json",
    )

    add_node("module:expert_workflow_system", "module", "Expert Workflow System")
    add_node(
        "module:skill_workflow_hook_telemetry",
        "module",
        "Skill, Workflow, And Hook Telemetry",
    )
    add_edge(
        "module:expert_workflow_system",
        "module:skill_workflow_hook_telemetry",
        "emits_structured_outputs_to",
        "core.shared_intelligence.expert_workflows.AUTHORITY_WRITE_TARGETS",
    )
    for workflow in expert_workflows.get("workflows", []):
        workflow_id = f"workflow:{workflow['workflow_id']}"
        add_node(workflow_id, "expert_workflow", workflow["workflow_id"])
        add_edge(
            "module:expert_workflow_system",
            workflow_id,
            "declares_expert_workflow",
            "core.shared_intelligence.expert_workflows.REQUIRED_WORKFLOW_IDS",
        )
        for owner in workflow.get("existing_owners", []):
            owner_id = f"skill:{owner}"
            add_node(owner_id, "skill_or_workflow_surface", str(owner))
            add_edge(
                workflow_id,
                owner_id,
                "maps_to_existing_owner",
                "core.shared_intelligence.expert_workflows.overlap_matrix",
            )

    add_node("module:capability_center", "module", "Capability Center")
    for section_id in capability_center.get("sections", {}):
        section_node = f"dashboard-section:capability-center:{section_id}"
        add_node(section_node, "dashboard_section", f"Capability Center {section_id}")
        add_edge(
            "module:capability_center",
            section_node,
            "exposes_derived_section",
            "core.shared_intelligence.capability_center.capability_center_summary",
        )

    add_node("module:scoped_agent_execution", "module", "Scoped Agent Execution")
    for agent in scoped_agents.get("agents", []):
        agent_id = f"agent:{agent['agent_id']}"
        add_node(agent_id, "scoped_agent", agent["agent_name"])
        add_edge(
            "module:scoped_agent_execution",
            agent_id,
            "declares_context_scoped_worker",
            "core.shared_intelligence.scoped_agents.DEFAULT_SCOPED_AGENTS",
        )
    add_edge(
        "module:scoped_agent_execution",
        "layer:sqlite_authority",
        "normalizes_results_to",
        "invocation/result authority tables",
    )

    add_node("module:github_repo_intake", "module", "GitHub Repo Intake")
    add_edge(
        "module:github_repo_intake",
        "module:security_lifecycle_gate",
        "requires_security_review_before_adoption",
        "core.shared_intelligence.github_repo_intake.WORKFLOW_STEPS",
    )
    add_edge(
        "module:github_repo_intake",
        "module:expert_workflow_system",
        "requires_overlap_review_before_new_skill_or_workflow",
        "core.shared_intelligence.github_repo_intake.WORKFLOW_STEPS",
    )
    for table in github_repo_intake.get("source_tables", []):
        table_id = f"table:{table}"
        add_node(table_id, "sqlite_table", str(table))
        add_edge(
            "module:github_repo_intake",
            table_id,
            "writes_evaluation_authority",
            "core.shared_intelligence.github_repo_intake.GITHUB_REPO_TABLES",
        )

    add_node("module:platform_hardening_sequence", "module", "Platform Hardening Sequence")
    add_edge(
        "module:platform_hardening_sequence",
        "module:contract_atlas",
        "feeds_maturity_and_docs_drift",
        "core.shared_intelligence.platform_hardening.platform_hardening_summary",
    )
    add_edge(
        "module:platform_hardening_sequence",
        "module:analytics_only_ingestion",
        "normalizes_connector_evidence",
        "core.shared_intelligence.platform_hardening.ingest_connector_payload",
    )
    for table in platform_hardening.get("source_tables", []):
        table_id = f"table:{table}"
        add_node(table_id, "sqlite_table", str(table))
        add_edge(
            "module:platform_hardening_sequence",
            table_id,
            "records_platform_hardening_authority",
            "core.shared_intelligence.platform_hardening.PLATFORM_HARDENING_TABLES",
        )

    for projection in projection_report.get("projections", []):
        adapter_id = f"adapter:{projection['adapter_id']}"
        projection_id = f"projection:{projection['projection_path']}"
        add_node(adapter_id, "adapter", projection["adapter_name"])
        add_node(projection_id, "adapter_projection", projection["projection_path"])
        add_edge(
            "layer:adapter_projection",
            adapter_id,
            "declares_adapter",
            "sqlite:adapter_authority_profiles",
        )
        add_edge(
            adapter_id,
            projection_id,
            "projects_config_to",
            "sqlite:adapter_authority_profiles",
        )

    for check in staleness_report.get("checks", []):
        active = check.get("active_repo_surface")
        if active:
            surface_id = f"active-surface:{active['path']}"
            add_node(surface_id, "active_repo_surface", active["path"])
            add_edge(
                f"adapter:{check['adapter_id']}",
                surface_id,
                "checked_active_surface",
                "core.shared_intelligence.adapter_staleness.ACTIVE_REPO_SURFACES",
            )

    return {
        "graph_type": "confirmed_dependency_graph",
        "inferred_edges_included": False,
        "unverified_edges_included": False,
        "nodes": sorted(nodes.values(), key=lambda item: item["id"]),
        "edges": sorted(edges, key=lambda item: (item["source"], item["target"], item["relation"])),
    }
