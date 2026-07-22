"""Contract Atlas static section builders.

WO-GF-SHARED-INTEL-SPLIT: extracted from contract_atlas.py. Holds the section
builders with no cross-sibling dependency (system/layer/interface/runtime
contracts, docs-freshness tracking, and the derived source-table set).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from core.shared_intelligence.authority import REQUIRED_SHARED_INTELLIGENCE_TABLES
from core.telemetry.docker_profiles import DOCKER_MODULE_PROFILES
from core.telemetry.execution_spine import DASHBOARD_MODULES


def _whole_system_contract() -> dict[str, Any]:
    return {
        "contract_id": "dream-studio-system",
        "name": "Dream Studio Local-First AI Orchestration",
        "canonical_authority": [
            "repo source for product code and public contracts",
            "operator-local SQLite for structured runtime authority",
            "operator-local evidence packets for private audit exports",
        ],
        "derived_surfaces": ["dashboard", "API read models", "adapter projections"],
        "non_authority_surfaces": [
            "private model memory",
            "adapter-local config",
            "Docker runtime",
        ],
        "required_boundaries": [
            "dashboard is derived_view=true and primary_authority=false",
            "adapters do not own canonical state",
            "Docker profiles must not create a competing authority DB",
            "public exports are sanitized",
        ],
    }


def _layer_contracts() -> list[dict[str, Any]]:
    return [
        {
            "layer_id": "repo_source",
            "role": "product_source_and_public_contracts",
            "canonical_for": ["source code", "tests", "docs", "schemas", "repo adapter surfaces"],
            "not_canonical_for": ["operator runtime state", "private evidence", "live DB rows"],
            "boundary": "Repo files must not embed operator-local secrets or live state.",
        },
        {
            "layer_id": "sqlite_authority",
            "role": "local_structured_authority",
            "canonical_for": sorted(REQUIRED_SHARED_INTELLIGENCE_TABLES),
            "not_canonical_for": ["public docs", "source code"],
            "boundary": "SQLite writes require explicit runtime/tooling authorization.",
        },
        {
            "layer_id": "telemetry_read_models",
            "role": "derived_operational_intelligence",
            "canonical_for": [],
            "not_canonical_for": ["routing authority", "primary authority decisions"],
            "boundary": "Read models summarize facts and must keep authority metadata.",
        },
        {
            "layer_id": "dashboard_api",
            "role": "local_human_loop_surface",
            "canonical_for": [],
            "not_canonical_for": ["source of truth", "cleanup execution", "deployment"],
            "boundary": "Dashboard output is derived and non-authoritative.",
        },
        {
            "layer_id": "adapter_projection",
            "role": "tool_specific_context_surface",
            "canonical_for": [],
            "not_canonical_for": ["Dream Studio authority", "private model memory"],
            "boundary": "Claude, Codex, and other adapters consume projections only.",
        },
        {
            "layer_id": "runtime_profiles",
            "role": "execution_boundary_descriptions",
            "canonical_for": [],
            "not_canonical_for": ["SQLite authority DB creation"],
            "boundary": "Optional profiles must receive explicit SQLite paths.",
        },
    ]


def _interface_contracts() -> list[dict[str, Any]]:
    return [
        {
            "interface_id": "telemetry_api",
            "path_family": "/api/telemetry/*",
            "consumer": "dashboard",
            "source": "core.telemetry.read_models",
            "authority": "derived",
            "writes_authorized": False,
        },
        {
            "interface_id": "shared_intelligence_api",
            "path_family": "/api/shared-intelligence/*",
            "consumer": "dashboard and local tools",
            "source": "core.shared_intelligence.*",
            "authority": "derived",
            "writes_authorized": False,
        },
        {
            "interface_id": "legacy_dashboard_api",
            "path_family": "/api/v1/*",
            "consumer": "legacy dashboard sections",
            "source": "projections.api.routes.*",
            "authority": "compatibility_read_surface",
            "writes_authorized": False,
        },
        {
            "interface_id": "hook_launcher",
            "path_family": "hooks/run.py, hooks/run.cmd, hooks/run.sh",
            "consumer": "Claude/Codex hook surfaces",
            "source": "runtime/hooks/*",
            "authority": "execution_projection",
            "writes_authorized": False,
        },
        {
            "interface_id": "active_repo_adapter_surfaces",
            "path_family": "CLAUDE.md and AGENTS.md",
            "consumer": "Claude/Codex when loading repo context",
            "source": "repo-root files",
            "authority": "projection",
            "writes_authorized": False,
        },
    ]


def _runtime_profiles() -> list[dict[str, Any]]:
    native = {
        "profile": "native-local",
        "role": "default_local_runtime",
        "optional": False,
        "runtime_authority": "canonical_path_or_injected_sqlite_path",
        "creates_authority_db": False,
        "fallback_execution_mode": "not_applicable",
    }
    profiles = [native]
    profiles.extend(dict(profile) for profile in DOCKER_MODULE_PROFILES)
    return profiles


def _analytics_only_profile() -> dict[str, Any]:
    return {
        "profile": "analytics-only",
        "role": "standalone_dashboard_reporting_and_explicit_ingestion",
        "db_mode": "read_only_by_default_explicit_ingestion_only",
        "writes_authorized": False,
        "ingestion_write_authorization": "ds analytics-ingest --execute",
        "execution_authorized": False,
        "hooks_required": False,
        "agents_required": False,
        "workflows_required": False,
        "claude_required": False,
        "codex_required": False,
        "docker_required": False,
        "repo_mutation_required": False,
        "allowed_surfaces": [
            "/api/telemetry/*",
            "/api/v1/projects*",
            "/api/v1/metrics/*",
            "/api/shared-intelligence/*",
        ],
        "disallowed_surfaces": [
            "adapter config writes",
            "cleanup execution",
            "live migrations",
            "hook_required_ingestion",
            "agent_required_ingestion",
        ],
        "empty_state_policy": "show honest empty states from current authority",
    }


def _adapter_projection_contracts(
    projection_report: Mapping[str, Any],
    staleness_report: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checks = {check["adapter_id"]: check for check in staleness_report.get("checks", [])}
    contracts: list[dict[str, Any]] = []
    for projection in projection_report.get("projections", []):
        adapter_id = str(projection["adapter_id"])
        check = checks.get(adapter_id, {})
        contracts.append(
            {
                "adapter_id": adapter_id,
                "adapter_type": projection["adapter_type"],
                "projection_path": projection["projection_path"],
                "projection_sha256": projection["content_sha256"],
                "source_authority": projection["source_authority"],
                "adapter_owns_source_of_truth": False,
                "config_write_authorized": False,
                "generated_projection": check.get("generated_projection"),
                "active_repo_surface": check.get("active_repo_surface"),
                "local_user_surface": check.get("local_user_surface"),
                "local_hook_surface": check.get("local_hook_surface"),
                "state_classifications": check.get("state_classifications", []),
                "live_execution_state": check.get("live_execution_state"),
            }
        )
    return contracts


def _dashboard_private_export_boundaries() -> dict[str, Any]:
    return {
        "dashboard_authority": "derived_view_only",
        "private_default": True,
        "public_exports_allowed": True,
        "public_export_policy": "sanitize local paths, local user surfaces, and sensitive metadata",
        "private_surfaces": [
            "operator-local evidence",
            "live SQLite rows",
            "local adapter configs",
            "backup and rollback paths",
            "career profiles, resumes, applications, contacts, automation evidence, and scorecards",
            "GitHub repo evaluation evidence until explicitly sanitized",
        ],
        "public_surfaces": ["sanitized docs", "source-level contracts", "non-sensitive examples"],
    }


def _docs_freshness_tracking() -> dict[str, Any]:
    return {
        "tracking_mode": "changed_files_same_change_set",
        "release_gate": "interfaces/cli/contract_docs_drift_gate.py",
        "blocking_policy": (
            "Meaningful source/schema/dashboard/workflow/adapter/release-gate "
            "changes must include the required impacted contract or docs refs in "
            "the same change set."
        ),
        "stale_states": ["stale_docs_required", "registry_validation_error"],
        "non_blocking_states": ["not_impacted", "fresh"],
        "rewrite_every_doc_required": False,
    }


def _source_tables() -> list[str]:
    tables = set(REQUIRED_SHARED_INTELLIGENCE_TABLES)
    # findings_current_status dropped migration 140 (WO dff23cb0) — derived
    # from security_events at read time, not a schema object.
    tables.add("security_events")
    tables.update(
        {
            "ai_adapter_accounting_profiles",
            "ai_usage_operational_records",
            "token_usage_records",
            "reg_projects",
            # release_readiness_records: dropped migration 133
            "validation_results",
            "agent_registry_records",
            "agent_context_scope_policies",
            "github_repo_evaluations",
            "github_repo_adoption_decisions",
            "task_attribution_records",
            "skill_evaluation_runs",
            # policy_decision_records: dropped migration 133
            "connector_ingestion_runs",
            # github_repo_license_findings, github_repo_security_findings,
            # github_repo_dependency_findings, github_repo_integration_candidates,
            # github_repo_pattern_references, github_repo_attribution_records,
            # privacy_redaction_export_records, local_watch_schedule_records,
            # team_rollup_records, installer_distribution_checks,
            # demo_case_study_packets — dropped in migration 128 (dead tables).
        }
    )
    for module in DASHBOARD_MODULES:
        tables.update(module["source_tables"])
    return sorted(tables)
