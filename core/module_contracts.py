"""Dream Studio module boundary contracts.

These declarations are source-level contracts for installed modules and runtime
profiles. They do not create authority; they make the existing SQLite, API,
dashboard, CLI, and profile boundaries explicit enough to validate.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from core.module_profiles import module_profile_map

MODULE_CONTRACT_SCHEMA = "dream_studio.module_contracts.v1"

MODULE_CONTRACT_IDS: tuple[str, ...] = (
    "core",
    "telemetry",
    "dashboard",
    "security_only",
    "token_only",
    "analytics_only",
    "shared_intelligence",
    "adapter_router",
    "adapter_projection",
    "external_project",
    "capability_center",
    "scoped_agents",
    "github_repo_intake",
    "docker_optional",
    "full",
)

MODULE_CONTRACTS: tuple[dict[str, Any], ...] = (
    {
        "module_id": "core",
        "purpose": "Bootstrap source/state paths, SQLite, runtime config, and global commands.",
        "owned_tables": ["schema_migrations"],
        "read_dependencies": [],
        "write_dependencies": ["state/studio.db bootstrap during install or rehearsal"],
        "emitted_events": ["runtime_status_checked", "runtime_validation_checked"],
        "api_routes": [],
        "dashboard_surfaces": [],
        "cli_commands": ["ds status", "ds validate", "ds modules"],
        "required_modules": [],
        "optional_modules": ["telemetry", "dashboard", "shared_intelligence"],
        "disabled_module_behavior": "Optional surfaces report unavailable without creating state.",
        "empty_state_behavior": "Core reports runtime paths and missing optional surfaces honestly.",
        "install_runtime_profile_membership": ["core", "full"],
        "security_readiness_impact": "Core path and DB health are release readiness inputs.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            "tests/unit/test_installed_adapter_runtime.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "telemetry",
        "purpose": "Persist and read operational events, validations, invocations, outcomes, and artifacts.",
        "owned_tables": [
            "execution_events",
            "process_runs",
            "validation_results",
            # artifact_records: dropped migration 130
            "outcome_records",
        ],
        "read_dependencies": ["project authority tables when scoped by project"],
        "write_dependencies": ["explicit telemetry producers or analytics ingestion"],
        "emitted_events": ["execution_event_recorded", "validation_result_recorded"],
        "api_routes": ["/api/telemetry/*"],
        "dashboard_surfaces": ["Telemetry", "Validation", "Artifacts"],
        "cli_commands": ["ds status", "ds validate"],
        "required_modules": ["core"],
        "optional_modules": ["dashboard", "analytics_only"],
        "disabled_module_behavior": "Dashboard consumers show telemetry unavailable or empty.",
        "empty_state_behavior": "No telemetry records have been captured yet.",
        "install_runtime_profile_membership": ["telemetry_only", "analytics_only", "full"],
        "security_readiness_impact": "Validation and evidence recency affect health/readiness.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            "tests/unit/test_telemetry_read_models.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "dashboard",
        "purpose": "Expose derived human-facing API and UI read models without owning authority.",
        "owned_tables": [],
        "read_dependencies": ["telemetry", "security_only", "token_only", "analytics_only"],
        "write_dependencies": [],
        "emitted_events": [],
        "api_routes": ["/dashboard", "/api/v1/*", "/api/shared-intelligence/*"],
        "dashboard_surfaces": ["All Projects", "Project Details", "Security", "Usage", "Readiness"],
        "cli_commands": [
            "ds dashboard --status",
            "ds dashboard --serve",
            "ds dashboard --open",
            "ds dashboard --check",
            "ds validate",
        ],
        "required_modules": ["core"],
        "optional_modules": ["telemetry", "security_only", "token_only", "shared_intelligence"],
        "disabled_module_behavior": "Optional panels show unavailable with a reason.",
        "empty_state_behavior": "Derived views render honest empty states when source facts are absent.",
        "install_runtime_profile_membership": ["dashboard_only", "analytics_only", "full"],
        "security_readiness_impact": "Dashboard integrity and stale data detection affect health.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            # test_actual_shared_intelligence_routes.py retired migration 131 (it tested the
            # dormant shared-intelligence dashboard surfaces — learning/hardening/model-provider/
            # context-packet — that read tables with no live writer; those routes now return
            # honest empty states and their live siblings are covered below).
            "tests/unit/test_dashboard_safety.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "security_only",
        "purpose": "Read and classify security findings and 47-control lifecycle status independently.",
        "owned_tables": ["findings", "security_control_results"],
        "read_dependencies": ["reg_projects", "validation_results"],
        "write_dependencies": ["security lifecycle gate or explicit normalized import"],
        "emitted_events": ["security_assessment_recorded"],
        "api_routes": ["/api/v1/security/*"],
        "dashboard_surfaces": ["Security Dashboard", "Project Security Detail"],
        "cli_commands": ["ds status", "ds modules"],
        "required_modules": ["core"],
        "optional_modules": ["dashboard", "analytics_only"],
        "disabled_module_behavior": "Security panels show no findings or unavailable controls.",
        "empty_state_behavior": "No security findings recorded for the selected scope.",
        "install_runtime_profile_membership": ["security_only", "analytics_only", "full"],
        "security_readiness_impact": "Open security findings and unknown controls can block release.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            "tests/unit/test_security_lifecycle_gate.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "token_only",
        "purpose": "Report token and AI usage telemetry without inventing per-run cost.",
        "owned_tables": [
            "token_usage_records",
            "ai_adapter_accounting_profiles",
            "ai_usage_operational_records",
        ],
        "read_dependencies": ["execution_events", "validation_results"],
        "write_dependencies": [
            "provider metadata, provider export, local telemetry, or explicit import"
        ],
        "emitted_events": ["ai_usage_recorded"],
        "api_routes": ["/api/v1/metrics/tokens", "/api/shared-intelligence/ai-usage-accounting"],
        "dashboard_surfaces": ["Token Analytics", "AI Usage Accounting"],
        "cli_commands": ["ds status", "ds modules"],
        "required_modules": ["core"],
        "optional_modules": ["dashboard", "analytics_only"],
        "disabled_module_behavior": "Usage panels show unavailable or no usage records.",
        "empty_state_behavior": "No token or AI usage records have been imported or captured.",
        "install_runtime_profile_membership": ["token_only", "analytics_only", "full"],
        "security_readiness_impact": "Usage outcome quality can inform readiness; unknown cost is not a blocker.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            "tests/unit/test_ai_usage_accounting.py",
            "tests/unit/test_module_contracts.py",
        ],
        "policy": "Tokens are usage telemetry; cost remains unknown unless provider-reported or configured.",
    },
    {
        "module_id": "analytics_only",
        "purpose": "Import normalized analytics and expose read-only dashboard/API intelligence standalone.",
        "owned_tables": [],
        "read_dependencies": [
            "reg_projects",
            "validation_results",
            "findings",
            "token_usage_records",
        ],
        "write_dependencies": ["explicit ds analytics-ingest --execute only"],
        "emitted_events": ["analytics_payload_ingested"],
        "api_routes": [
            "/api/v1/projects*",
            "/api/v1/metrics/*",
            "/api/v1/security/*",
            "/api/shared-intelligence/analytics-only",
        ],
        "dashboard_surfaces": ["All Projects", "Project Details", "Metrics", "Security"],
        "cli_commands": ["ds analytics-ingest", "ds status", "ds modules"],
        "required_modules": ["core"],
        "optional_modules": ["telemetry", "security_only", "token_only", "dashboard"],
        "disabled_module_behavior": "Missing optional facts appear as unavailable, not zero.",
        "empty_state_behavior": "Analytics routes return empty sections when no normalized facts exist.",
        "install_runtime_profile_membership": ["analytics_only", "full"],
        "security_readiness_impact": "Imported facts can feed health/readiness but do not overclaim evidence.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            "tests/unit/test_analytics_only_ingestion.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "shared_intelligence",
        "purpose": "Expose adapter, model, context packet, usage accounting, and Contract Atlas read models.",
        "owned_tables": ["adapter_authority_profiles", "model_provider_profiles"],
        "read_dependencies": ["adapter profiles", "module contracts", "runtime profiles"],
        "write_dependencies": ["setup/config commands only when explicitly authorized"],
        "emitted_events": ["context_packet_generated"],
        "api_routes": ["/api/shared-intelligence/*"],
        "dashboard_surfaces": ["Contract Atlas", "Adapter Health", "AI Usage Accounting"],
        "cli_commands": [
            "ds contract-atlas",
            "ds contract-atlas-refresh",
            "ds context-packet",
            "ds adapters",
        ],
        "required_modules": ["core"],
        "optional_modules": ["adapter_router", "adapter_projection", "dashboard"],
        "disabled_module_behavior": "Live adapter execution stays unavailable; context packets still work.",
        "empty_state_behavior": "Shared intelligence sections report their own empty states.",
        "install_runtime_profile_membership": [
            "shared_intelligence_only",
            "adapter_router_only",
            "full",
        ],
        "security_readiness_impact": "Adapter/accounting confidence affects readiness evidence quality.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            "tests/unit/test_contract_atlas.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "adapter_router",
        "purpose": "Classify adapter modes, route capabilities, health, context packets, and result normalization.",
        "owned_tables": [],
        "read_dependencies": ["adapter_authority_profiles", "shared_intelligence"],
        "write_dependencies": ["evidence capture only when explicitly authorized"],
        "emitted_events": ["adapter_status_checked", "context_packet_generated"],
        "api_routes": ["/api/shared-intelligence/adapter-router"],
        "dashboard_surfaces": ["Adapter Router Status"],
        "cli_commands": ["ds router", "ds adapters", "ds context-packet"],
        "required_modules": ["core", "shared_intelligence"],
        "optional_modules": ["dashboard", "adapter_projection"],
        "disabled_module_behavior": "Works without dashboard/frontend and without live adapter execution.",
        "empty_state_behavior": "Unsupported adapters are listed as unsupported or context-packet-only.",
        "install_runtime_profile_membership": ["adapter_router_only", "full"],
        "security_readiness_impact": "Adapter staleness and unsupported modes inform release attention.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            "tests/unit/test_installed_adapter_runtime.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "adapter_projection",
        "purpose": "Generate adapter-specific projected instructions without becoming source authority.",
        "owned_tables": [],
        "read_dependencies": ["adapter_authority_profiles", "shared_context_packets"],
        "write_dependencies": [
            "repo projection files only when projection generation is explicitly requested"
        ],
        "emitted_events": ["adapter_projection_rendered"],
        "api_routes": [],
        "dashboard_surfaces": ["Adapter Projection Status"],
        "cli_commands": ["ds adapters"],
        "required_modules": ["core", "shared_intelligence"],
        "optional_modules": ["adapter_router"],
        "disabled_module_behavior": "Adapters fall back to context packets or unsupported classification.",
        "empty_state_behavior": "No generated projection exists until adapter authority is configured.",
        "install_runtime_profile_membership": [
            "shared_intelligence_only",
            "adapter_router_only",
            "full",
        ],
        "security_readiness_impact": "Projection staleness can create dashboard attention.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            "tests/unit/test_shared_intelligence_adapter_config_projection.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "external_project",
        "purpose": "Represent imported or observed external projects without mutating them by default.",
        "owned_tables": ["reg_projects", "pi_components", "pi_dependencies"],
        "read_dependencies": ["validation_results", "findings", "readiness records"],
        "write_dependencies": [
            "Dream Studio SQLite authority; external repo writes require explicit approval"
        ],
        "emitted_events": ["external_project_registered", "project_authority_hydrated"],
        "api_routes": ["/api/v1/projects*", "/api/v1/projects/{project_id}/details"],
        "dashboard_surfaces": ["All Projects", "Project Details", "Stack Graph"],
        "cli_commands": ["ds status", "ds validate"],
        "required_modules": ["core"],
        "optional_modules": ["analytics_only", "security_only", "dashboard"],
        "disabled_module_behavior": "External projects stay evidence-only when mutation is not approved.",
        "empty_state_behavior": "Project detail shows missing evidence or manual-review flags honestly.",
        "install_runtime_profile_membership": ["analytics_only", "full"],
        "security_readiness_impact": "External onboarding and publication readiness consume project evidence.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            "tests/unit/test_project_portfolio_authority_security_hydration.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "capability_center",
        "purpose": "Show skills, workflows, agents, controls, evaluations, and hardening candidates from authority.",
        "owned_tables": [],
        "read_dependencies": [
            "skill_invocations",
            "workflow_invocations",
            "agent_invocations",
            "hardening_candidate_records",
            "production readiness controls",
        ],
        "write_dependencies": ["explicit capability evaluation imports only"],
        "emitted_events": ["capability_evaluation_recorded"],
        "api_routes": ["/api/shared-intelligence/capability-center"],
        "dashboard_surfaces": ["Capability Center"],
        "cli_commands": ["ds contract-atlas"],
        "required_modules": ["core", "shared_intelligence"],
        "optional_modules": ["dashboard"],
        "disabled_module_behavior": "Dashboard sections show unavailable with reasons when no records exist.",
        "empty_state_behavior": "No skill, workflow, agent, control, or hardening evidence has been recorded.",
        "install_runtime_profile_membership": ["shared_intelligence_only", "full"],
        "security_readiness_impact": "Capability evaluations and hardening candidates inform maturity/readiness.",
        "contract_atlas_maturity_level": "tested_only",
        "validation_tests": [
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "scoped_agents",
        "purpose": "Register scoped worker agents and constrain context, permissions, and result normalization.",
        "owned_tables": [
            "agent_registry_records",
            "agent_context_scope_policies",
        ],
        "read_dependencies": ["agent_invocations"],
        "write_dependencies": ["agent registry/setup commands and normalized agent results"],
        "emitted_events": ["agent_context_packet_generated", "agent_result_normalized"],
        "api_routes": [
            "/api/shared-intelligence/agents/registry",
            "/api/shared-intelligence/agents/context-packet",
        ],
        "dashboard_surfaces": ["Capability Center Agents"],
        "cli_commands": ["ds context-packet"],
        "required_modules": ["core", "shared_intelligence"],
        "optional_modules": ["adapter_router"],
        "disabled_module_behavior": "Agents remain unavailable for execution; context policy can still be inspected.",
        "empty_state_behavior": "Default scoped agent declarations are visible without recorded invocations.",
        "install_runtime_profile_membership": ["shared_intelligence_only", "full"],
        "security_readiness_impact": "Context minimization and approval boundaries reduce agent execution risk.",
        "contract_atlas_maturity_level": "tested_only",
        "validation_tests": [
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "github_repo_intake",
        "purpose": "Evaluate GitHub repositories before adopting code, patterns, dependencies, prompts, or workflows.",
        "owned_tables": [
            "github_repo_evaluations",
            "github_repo_license_findings",
            "github_repo_security_findings",
            "github_repo_dependency_findings",
            "github_repo_integration_candidates",
            "github_repo_pattern_references",
            "github_repo_adoption_decisions",
            "github_repo_attribution_records",
        ],
        "read_dependencies": [
            "Contract Atlas",
            "security/readiness controls",
            "skill/workflow overlap catalog",
        ],
        "write_dependencies": ["explicit repo intake evaluation only; no external repo mutation"],
        "emitted_events": ["github_repo_evaluation_recorded"],
        "api_routes": ["/api/shared-intelligence/github-repo-intake"],
        "dashboard_surfaces": ["GitHub Repo Intake"],
        "cli_commands": ["ds contract-atlas"],
        "required_modules": ["core", "shared_intelligence"],
        "optional_modules": ["security_only", "analytics_only", "external_project"],
        "disabled_module_behavior": "No external repo is inspected or adopted automatically.",
        "empty_state_behavior": "No external GitHub repositories have been evaluated.",
        "install_runtime_profile_membership": ["shared_intelligence_only", "full"],
        "security_readiness_impact": "License/security/dependency review gates dependency and code adoption.",
        "contract_atlas_maturity_level": "tested_only",
        "validation_tests": [
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "docker_optional",
        "purpose": "Provide optional isolated validation/runtime profiles without owning Dream Studio authority.",
        "owned_tables": [],
        "read_dependencies": ["repo source", "explicit injected SQLite path"],
        "write_dependencies": ["container-local temp state only"],
        "emitted_events": ["docker_profile_checked"],
        "api_routes": [],
        "dashboard_surfaces": ["Runtime Profile Status"],
        "cli_commands": ["scripts/dev.ps1 docker-runtime-check"],
        "required_modules": [],
        "optional_modules": ["security_only", "telemetry", "full"],
        "disabled_module_behavior": "Docker unavailable never disables core authority or analytics-only.",
        "empty_state_behavior": "Docker status is optional or unavailable, not failed core runtime.",
        "install_runtime_profile_membership": ["full"],
        "security_readiness_impact": "Docker changes trigger readiness review; Docker is not core authority.",
        "contract_atlas_maturity_level": "documented_optional",
        "validation_tests": [
            "tests/unit/test_docker_module_profiles.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
    {
        "module_id": "full",
        "purpose": "Enable all local read models and optional integrations while preserving module boundaries.",
        "owned_tables": [],
        "read_dependencies": ["core", "dashboard", "telemetry", "shared_intelligence"],
        "write_dependencies": ["only through explicit module-owned commands"],
        "emitted_events": ["full_profile_status_checked"],
        "api_routes": ["/dashboard", "/api/telemetry/*", "/api/shared-intelligence/*"],
        "dashboard_surfaces": ["All local dashboard surfaces"],
        "cli_commands": [
            "ds status",
            "ds dashboard",
            "ds validate",
            "ds contract-atlas",
            "ds contract-atlas-refresh",
            "ds adapters",
            "ds context-packet",
            "ds modules",
            "ds router",
        ],
        "required_modules": [
            "core",
            "dashboard",
            "telemetry",
            "shared_intelligence",
            "adapter_router",
        ],
        "optional_modules": ["docker_optional", "adapter_projection"],
        "disabled_module_behavior": "Optional integrations show empty or unavailable state honestly.",
        "empty_state_behavior": "No optional integrations are claimed until evidence exists.",
        "install_runtime_profile_membership": ["full"],
        "security_readiness_impact": "Full profile release gate aggregates module health and readiness.",
        "contract_atlas_maturity_level": "runtime_validated",
        "validation_tests": [
            "tests/unit/test_installed_platform_productization.py",
            "tests/unit/test_module_contracts.py",
        ],
    },
)


def module_contracts() -> dict[str, Any]:
    contracts = [dict(contract) for contract in MODULE_CONTRACTS]
    return {
        "schema": MODULE_CONTRACT_SCHEMA,
        "model_name": "dream_studio_module_contracts",
        "derived_view": True,
        "primary_authority": False,
        "db_write_authorized": False,
        "contract_count": len(contracts),
        "contracts": contracts,
        "validation_errors": validate_module_contracts(contracts),
    }


def module_contract_map() -> dict[str, dict[str, Any]]:
    return {contract["module_id"]: dict(contract) for contract in MODULE_CONTRACTS}


def validate_module_contracts(
    contracts: Iterable[Mapping[str, Any]] = MODULE_CONTRACTS,
) -> list[str]:
    errors: list[str] = []
    rows = [dict(contract) for contract in contracts]
    by_id = {str(contract.get("module_id")): contract for contract in rows}
    profile_ids = set(module_profile_map())
    required_fields = {
        "module_id",
        "purpose",
        "owned_tables",
        "read_dependencies",
        "write_dependencies",
        "emitted_events",
        "api_routes",
        "dashboard_surfaces",
        "cli_commands",
        "required_modules",
        "optional_modules",
        "disabled_module_behavior",
        "empty_state_behavior",
        "install_runtime_profile_membership",
        "security_readiness_impact",
        "contract_atlas_maturity_level",
        "validation_tests",
    }
    if set(MODULE_CONTRACT_IDS) != set(by_id):
        errors.append("module contract id set does not match required module boundaries")
    for contract in rows:
        module_id = str(contract.get("module_id") or "")
        for field in required_fields:
            value = contract.get(field)
            if value in (None, "", [], {}):
                if field in {
                    "owned_tables",
                    "read_dependencies",
                    "write_dependencies",
                    "emitted_events",
                    "api_routes",
                    "dashboard_surfaces",
                    "required_modules",
                    "optional_modules",
                }:
                    continue
                errors.append(f"module {module_id} missing {field}")
        for dependency in contract.get("required_modules", []):
            if dependency not in by_id:
                errors.append(f"module {module_id} requires unknown module {dependency}")
        for profile_id in contract.get("install_runtime_profile_membership", []):
            if profile_id not in profile_ids:
                errors.append(f"module {module_id} references unknown profile {profile_id}")
        if module_id in {"dashboard", "adapter_projection", "docker_optional"} and contract.get(
            "owned_tables"
        ):
            errors.append(f"module {module_id} must not own SQLite authority tables")
    analytics = by_id.get("analytics_only", {})
    for forbidden in ("hooks", "agents", "workflows", "claude", "codex", "docker"):
        if forbidden in analytics.get("required_modules", []):
            errors.append(f"analytics_only must not require {forbidden}")
    token = by_id.get("token_only", {})
    if "fake" in " ".join(str(value).lower() for value in token.get("write_dependencies", [])):
        errors.append("token_only write dependencies must not permit fake cost data")
    if "unknown" not in str(token.get("policy", "")).lower():
        errors.append("token_only policy must preserve unknown cost")
    docker = by_id.get("docker_optional", {})
    if docker.get("owned_tables"):
        errors.append("docker_optional must not own authority tables")
    return errors
