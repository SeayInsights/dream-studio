"""Contract registry and documentation drift mapping.

The registry maps meaningful code/schema/dashboard/workflow/adapter changes to
the public contracts and docs that must stay fresh. It is intentionally
repo-backed and deterministic so release gates can run without live DB writes.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable, Mapping
from datetime import datetime, timezone
from typing import Any

CONTRACT_REGISTRY_SCHEMA = "dream_studio.contract_registry.v1"
DOC_DRIFT_GATE_SCHEMA = "dream_studio.contract_docs_drift_gate.v1"

PRD_DOC = "docs/product/dream-studio-prd.md"
README_DOC = "README.md"
PUBLICATION_BOUNDARY_DOC = "docs/PUBLICATION_BOUNDARY.md"
CONTRACT_ATLAS_DOC = "docs/architecture/contract-atlas.md"

PRIVATE_ARTIFACT_PATTERNS: tuple[str, ...] = (
    ".dream-studio/**",
    "**/.dream-studio/**",
    "**/*.db",
    "**/*.sqlite",
    "**/*.sqlite3",
    "**/*-wal",
    "**/*-shm",
    "**/backups/**",
    "**/meta/work-orders/**",
    "**/meta/audit/**",
    "**/raw_telemetry/**",
    "**/operator_decisions/**",
)

PUBLICATION_RISK_PATTERNS: tuple[str, ...] = (
    "README.md",
    "LICENSE",
    "docs/**",
    ".github/**",
    "adapter-projections/**",
)


CONTRACT_DOMAINS: tuple[dict[str, Any], ...] = (
    {
        "domain_id": "contract_atlas",
        "domain_name": "Contract Atlas",
        "source_patterns": [
            "core/shared_intelligence/contract_atlas.py",
            "core/shared_intelligence/contract_atlas_lifecycle.py",
            "core/shared_intelligence/contract_registry.py",
            "core/shared_intelligence/maturity_ledger.py",
            "core/module_contracts.py",
            "interfaces/cli/contract_atlas_lifecycle_gate.py",
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            "docs/architecture/contract-atlas.md",
        ],
        "docs_refs": [
            "README.md",
            "docs/README.md",
            PRD_DOC,
            "docs/PUBLICATION_BOUNDARY.md",
            "docs/operations/lint-format-baseline-policy.md",
        ],
        "required_doc_refs": [
            "docs/architecture/contract-atlas.md",
            "docs/README.md",
            "docs/operations/lint-format-baseline-policy.md",
        ],
        "release_blocking": True,
        "freshness_policy": "source_changes_require_same_change_set_contract_or_docs_refresh",
        "public_export_boundary": "sanitized_public_export_only",
    },
    {
        "domain_id": "shared_intelligence_adapters",
        "domain_name": "Shared Intelligence And Adapter Projections",
        "source_patterns": [
            "core/shared_intelligence/adapter_*.py",
            "core/shared_intelligence/context_packets.py",
            "core/shared_intelligence/result_normalization.py",
            "adapter-projections/**",
            "AGENTS.md",
            "CLAUDE.md",
        ],
        "contract_refs": [
            "docs/contracts/adapter-contract.md",
            "docs/architecture/shared-authority-and-adapter-projections.md",
        ],
        "docs_refs": [
            "docs/operations/independent-configuration-model.md",
            PRD_DOC,
            "README.md",
        ],
        "required_doc_refs": [
            "docs/architecture/shared-authority-and-adapter-projections.md",
        ],
        "release_blocking": True,
        "freshness_policy": "adapter_surface_changes_require_adapter_boundary_doc_refresh",
        "public_export_boundary": "adapter_configs_are_projection_docs_only",
    },
    {
        "domain_id": "task_attribution_outcomes",
        "domain_name": "AI Adapter Task Attribution And Outcomes",
        "source_patterns": [
            "core/shared_intelligence/task_attribution.py",
            "core/shared_intelligence/usage_accounting.py",
            "core/shared_intelligence/capability_center.py",
            "core/event_store/migrations/045_task_attribution_authority.sql",
            "projections/api/routes/project_intelligence.py",
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            "docs/operations/task-attribution-and-outcomes.md",
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
        ],
        "docs_refs": [
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
            "docs/architecture/shared-authority-and-adapter-projections.md",
            PRD_DOC,
            "docs/README.md",
        ],
        "required_doc_refs": [
            "docs/operations/task-attribution-and-outcomes.md",
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
        ],
        "release_blocking": True,
        "freshness_policy": "attribution_schema_or_read_model_changes_require_dashboard_and_database_docs_refresh",
        "public_export_boundary": "attribution_examples_synthetic_live_evidence_private",
    },
    {
        "domain_id": "sqlite_schema_authority",
        "domain_name": "SQLite Schema And Authority",
        "source_patterns": [
            "core/event_store/migrations/**",
            "core/event_store/studio_db.py",
            "core/config/database.py",
        ],
        "contract_refs": [
            "docs/MIGRATION_AUTHORITY.md",
            "docs/DATABASE.md",
        ],
        "docs_refs": [
            "docs/architecture/dream-studio-structured-authority-projection-model.md",
            PRD_DOC,
        ],
        "required_doc_refs": [
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
        ],
        "release_blocking": True,
        "freshness_policy": "schema_or_path_changes_require_database_docs_refresh",
        "public_export_boundary": "schema_docs_public_live_db_private",
    },
    {
        "domain_id": "installed_adapter_runtime",
        "domain_name": "Installed Adapter Runtime And Global Router",
        "source_patterns": [
            "core/installed_runtime.py",
            "core/installed_productization.py",
            "core/module_contracts.py",
            "core/module_profiles.py",
            "core/release/local_dogfood_stability.py",
            "ds.cmd",
            "ds.ps1",
            "interfaces/cli/ds.py",
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            "docs/operations/installed-adapter-runtime.md",
            "docs/operations/installed-platform-productization.md",
            "docs/operations/long-run-multisession-operational-validation.md",
            "docs/operations/troubleshooting.md",
            "docs/architecture/shared-authority-and-adapter-projections.md",
        ],
        "docs_refs": [
            "docs/operations/independent-configuration-model.md",
            "docs/operations/installed-platform-productization.md",
            "docs/operations/long-run-multisession-operational-validation.md",
            "docs/operations/troubleshooting.md",
            "docs/README.md",
        ],
        "required_doc_refs": [
            "docs/operations/installed-adapter-runtime.md",
            "docs/operations/installed-platform-productization.md",
            "docs/operations/long-run-multisession-operational-validation.md",
            "docs/operations/troubleshooting.md",
            "docs/architecture/shared-authority-and-adapter-projections.md",
            "docs/operations/independent-configuration-model.md",
        ],
        "release_blocking": True,
        "freshness_policy": "installed_runtime_or_router_changes_require_runtime_docs_refresh",
        "public_export_boundary": "installed_runtime_paths_private_global_commands_public",
    },
    {
        "domain_id": "dashboard_runtime",
        "domain_name": "Dashboard Runtime And Read Models",
        "source_patterns": [
            "projections/api/routes/**",
            "projections/frontend/dashboard.html",
            "core/telemetry/read_models.py",
            "core/telemetry/dashboard_freshness.py",
        ],
        "contract_refs": [
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
            "docs/contracts/dashboard-projection-model-contract.md",
        ],
        "docs_refs": [
            "docs/operator-guide.md",
            PRD_DOC,
        ],
        "required_doc_refs": [
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
        ],
        "release_blocking": True,
        "freshness_policy": "dashboard_contract_changes_require_projection_mapping_refresh",
        "public_export_boundary": "dashboard_derived_not_primary_authority",
    },
    {
        "domain_id": "security_lifecycle_gate",
        "domain_name": "Security-By-Default Lifecycle Gate",
        "source_patterns": [
            "core/security/**",
            "skills/security/**",
            "guardrails/rules/security.yaml",
            "docs/contracts/security-review-*.md",
            "docs/contracts/security-review-*.yaml",
            "projections/api/routes/security.py",
            "projections/api/routes/project_intelligence.py",
            "projections/api/routes/shared_intelligence.py",
            "core/release/versioning.py",
        ],
        "contract_refs": [
            "docs/contracts/security-by-default-development-lifecycle-gate.md",
            "docs/contracts/security-review-source-47-enterprise-scans.md",
            "docs/contracts/security-review-47-scan-crosswalk.md",
            "docs/contracts/security-review-scan-catalog.yaml",
        ],
        "docs_refs": [
            "docs/contracts/security-review-profile-pack-contract.md",
            "docs/contracts/security-review-catalog-governance.md",
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
            "docs/operations/product-readiness.md",
        ],
        "required_doc_refs": [
            "docs/contracts/security-by-default-development-lifecycle-gate.md",
            "docs/contracts/security-review-profile-pack-contract.md",
            "docs/operations/product-readiness.md",
        ],
        "release_blocking": True,
        "freshness_policy": "security_lifecycle_changes_require_control_mapping_and_readiness_docs_refresh",
        "public_export_boundary": "security_findings_public_shape_live_evidence_private",
    },
    {
        "domain_id": "secure_production_readiness_gate",
        "domain_name": "Secure Production Readiness Gate",
        "source_patterns": [
            "core/production_readiness/**",
            "core/event_store/migrations/040_production_readiness_authority.sql",
            "core/release/versioning.py",
            "projections/api/routes/project_intelligence.py",
            "projections/api/routes/shared_intelligence.py",
            "docs/contracts/secure-production-readiness-gate.md",
            "docs/contracts/security-by-default-development-lifecycle-gate.md",
        ],
        "contract_refs": [
            "docs/contracts/secure-production-readiness-gate.md",
            "docs/contracts/security-by-default-development-lifecycle-gate.md",
        ],
        "docs_refs": [
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
            "docs/operations/product-readiness.md",
            "docs/README.md",
            PRD_DOC,
        ],
        "required_doc_refs": [
            "docs/contracts/secure-production-readiness-gate.md",
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
            "docs/operations/product-readiness.md",
        ],
        "release_blocking": True,
        "freshness_policy": "production_readiness_control_or_sqlite_changes_require_readiness_docs_refresh",
        "public_export_boundary": "readiness_scores_are_derived_private_evidence_not_public_claims",
    },
    {
        "domain_id": "workflow_and_hooks",
        "domain_name": "Workflow And Hook Runtime",
        "source_patterns": [
            "hooks/**",
            "runtime/hooks/**",
            "workflows/**",
            "control/execution/workflow/**",
        ],
        "contract_refs": [
            "docs/HOOK_RUNTIME.md",
            "docs/WORKFLOW_RUNTIME.md",
            "docs/WORKFLOWS.md",
            "docs/contracts/hook-contract.md",
            "docs/contracts/workflow-contract.md",
        ],
        "docs_refs": [
            "docs/operator-guide.md",
        ],
        "required_doc_refs": [
            "docs/HOOK_RUNTIME.md",
            "docs/WORKFLOW_RUNTIME.md",
        ],
        "release_blocking": True,
        "freshness_policy": "hook_or_workflow_changes_require_runtime_docs_refresh",
        "public_export_boundary": "runtime_hooks_public_secrets_private",
    },
    {
        "domain_id": "expert_workflow_system",
        "domain_name": "Expert Skills And Workflow System",
        "source_patterns": [
            "core/shared_intelligence/expert_workflows.py",
            "skills/**",
            "workflows/**",
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            "docs/operations/expert-workflow-systems.md",
            "docs/architecture/contract-atlas.md",
        ],
        "docs_refs": [
            "README.md",
            "docs/README.md",
            PRD_DOC,
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
        ],
        "required_doc_refs": [
            "docs/operations/expert-workflow-systems.md",
            "docs/architecture/contract-atlas.md",
            "docs/README.md",
        ],
        "release_blocking": True,
        "freshness_policy": "expert_skill_or_workflow_changes_require_overlap_matrix_and_docs_refresh",
        "public_export_boundary": (
            "career_data_private_by_default_public_outputs_sanitized_and_operator_approved"
        ),
    },
    {
        "domain_id": "release_publication_gate",
        "domain_name": "Release Gate And Publication Boundary",
        "source_patterns": [
            ".github/workflows/**",
            "core/release/github_pr_cicd_gate.py",
            "interfaces/cli/ci_gate.py",
            "interfaces/cli/repo_publication_readiness.py",
            "interfaces/cli/lint_baseline.py",
            "interfaces/cli/contract_docs_drift_gate.py",
            "interfaces/cli/contract_atlas_lifecycle_gate.py",
            "core/release/repo_publication_readiness.py",
            "core/projects/external_validation.py",
            "core/projects/dashboard_views.py",
            "core/telemetry/docker_profiles.py",
            "runtime/config/release-gates/**",
        ],
        "contract_refs": [
            "docs/operations/lint-format-baseline-policy.md",
            "docs/PUBLICATION_BOUNDARY.md",
            "docs/operations/repo-publication-privacy.md",
            "docs/operations/external-project-validation-pipeline.md",
            "docs/operations/docker-module-profiles.md",
        ],
        "docs_refs": [
            "README.md",
            "docs/operator-guide.md",
            PRD_DOC,
        ],
        "required_doc_refs": [
            "docs/operations/lint-format-baseline-policy.md",
            "docs/PUBLICATION_BOUNDARY.md",
            "docs/operations/repo-publication-privacy.md",
            "docs/operations/external-project-validation-pipeline.md",
            "docs/operations/docker-module-profiles.md",
            "README.md",
        ],
        "release_blocking": True,
        "freshness_policy": "release_gate_changes_require_release_docs_refresh",
        "public_export_boundary": "release_evidence_private_release_policy_public",
    },
    {
        "domain_id": "career_capability_agent_github_intake",
        "domain_name": "Career Ops, Capability Center, Scoped Agents, And GitHub Repo Intake",
        "source_patterns": [
            "core/career_ops.py",
            "core/shared_intelligence/capability_center.py",
            "core/shared_intelligence/scoped_agents.py",
            "core/shared_intelligence/github_repo_intake.py",
            "core/event_store/migrations/044_career_capability_agent_github_authority.sql",
            "core/module_contracts.py",
            "core/module_profiles.py",
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            "docs/operations/career-ops-capability-center.md",
            "docs/operations/github-repo-intake-evaluation.md",
            "docs/architecture/contract-atlas.md",
        ],
        "docs_refs": [
            "README.md",
            "docs/README.md",
            PRD_DOC,
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
            "docs/PUBLICATION_BOUNDARY.md",
        ],
        "required_doc_refs": [
            "docs/operations/career-ops-capability-center.md",
            "docs/operations/github-repo-intake-evaluation.md",
            "docs/architecture/contract-atlas.md",
            "docs/README.md",
            "docs/PUBLICATION_BOUNDARY.md",
        ],
        "release_blocking": True,
        "freshness_policy": (
            "private_career_capability_agent_or_github_intake_changes_require_docs_and_public_boundary_refresh"
        ),
        "public_export_boundary": (
            "career_data_private_by_default_github_evaluation_evidence_sanitized_before_public_export"
        ),
    },
    {
        "domain_id": "platform_hardening_sequence",
        "domain_name": "Platform Hardening Sequence",
        "source_patterns": [
            "core/shared_intelligence/platform_hardening.py",
            "core/event_store/migrations/046_platform_hardening_authority.sql",
            "interfaces/cli/ds.py",
            "projections/api/routes/shared_intelligence.py",
        ],
        "contract_refs": [
            "docs/operations/platform-hardening-sequence.md",
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
        ],
        "docs_refs": [
            "README.md",
            "docs/README.md",
            PRD_DOC,
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
            "docs/PUBLICATION_BOUNDARY.md",
            "docs/operations/installed-platform-productization.md",
            "docs/operations/task-attribution-and-outcomes.md",
        ],
        "required_doc_refs": [
            "docs/operations/platform-hardening-sequence.md",
            "docs/DATABASE.md",
            "docs/MIGRATION_AUTHORITY.md",
            "docs/PUBLICATION_BOUNDARY.md",
            "docs/architecture/contract-atlas.md",
            "docs/architecture/dream-studio-dashboard-projection-mapping.md",
        ],
        "release_blocking": True,
        "freshness_policy": "platform_hardening_authority_or_surface_changes_require_policy_privacy_installer_demo_docs_refresh",
        "public_export_boundary": "private_evidence_stays_private_sanitized_rollups_and_demo_packets_only",
    },
)


def contract_registry() -> dict[str, Any]:
    """Return the repo-backed contract registry."""

    return {
        "schema": CONTRACT_REGISTRY_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "db_write_authorized": False,
        "domain_count": len(CONTRACT_DOMAINS),
        "domains": [dict(domain) for domain in CONTRACT_DOMAINS],
        "tracking_mode": "changed_files_same_change_set",
        "empty_state": "No contract domains are registered.",
    }


def change_impact_report(
    changed_files: Iterable[str],
    *,
    reviewed_no_change_domains: Iterable[str] = (),
) -> dict[str, Any]:
    """Map changed files to contract/doc freshness obligations."""

    changed = sorted({_normalize(path) for path in changed_files if path})
    reviewed = sorted({item for item in reviewed_no_change_domains if item})
    private_hits = _matches_any(changed, PRIVATE_ARTIFACT_PATTERNS)
    publication_hits = _matches_any(changed, PUBLICATION_RISK_PATTERNS)
    domains: list[dict[str, Any]] = []
    blocking: list[dict[str, Any]] = []
    for domain in CONTRACT_DOMAINS:
        source_hits = _matches_any(changed, domain["source_patterns"])
        docs = list(dict.fromkeys(domain["contract_refs"] + domain["docs_refs"]))
        doc_hits = [path for path in changed if path in docs]
        required_docs = list(domain["required_doc_refs"])
        missing = [path for path in required_docs if path not in changed]
        impacted = bool(source_hits)
        reviewed_no_change = bool(impacted and domain["domain_id"] in reviewed)
        status = "not_impacted"
        if impacted:
            if reviewed_no_change:
                status = "docs_reviewed_no_change_needed"
                missing = []
            else:
                status = "fresh" if not missing else "stale_docs_required"
        required_actions = _required_actions(domain, impacted, missing, reviewed_no_change)
        item = {
            "domain_id": domain["domain_id"],
            "domain_name": domain["domain_name"],
            "impacted": impacted,
            "source_hits": source_hits,
            "doc_hits": doc_hits,
            "required_doc_refs": required_docs,
            "missing_required_doc_refs": missing if impacted else [],
            "freshness_status": status,
            "required_actions": required_actions,
            "docs_update_required": "docs_update_required" in required_actions,
            "docs_reviewed_no_change_needed": reviewed_no_change,
            "prd_update_required": "prd_update_required" in required_actions,
            "readme_update_required": "readme_update_required" in required_actions,
            "contract_atlas_update_required": (
                "contract_atlas_update_required" in required_actions
            ),
            "publication_boundary_review_required": (
                "publication_boundary_review_required" in required_actions
            ),
            "release_blocking": bool(domain["release_blocking"]),
            "freshness_policy": domain["freshness_policy"],
            "public_export_boundary": domain["public_export_boundary"],
        }
        domains.append(item)
        if impacted and missing and domain["release_blocking"]:
            blocking.append(item)

    private_artifact_risk_detected = bool(private_hits)
    publication_risk_detected = bool(publication_hits)
    publication_risk = {
        "publication_risk_detected": publication_risk_detected,
        "private_artifact_risk_detected": private_artifact_risk_detected,
        "publication_hits": publication_hits,
        "private_artifact_hits": private_hits,
        "release_blocking": private_artifact_risk_detected,
        "required_actions": _publication_required_actions(
            publication_risk_detected=publication_risk_detected,
            private_artifact_risk_detected=private_artifact_risk_detected,
        ),
    }
    status = "fail" if blocking or private_artifact_risk_detected else "pass"
    return {
        "schema": DOC_DRIFT_GATE_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "db_write_authorized": False,
        "changed_files": changed,
        "changed_file_count": len(changed),
        "reviewed_no_change_domains": reviewed,
        "tracking_mode": "changed_files_same_change_set",
        "status": status,
        "blocking_domain_count": len(blocking) + (1 if private_artifact_risk_detected else 0),
        "impacted_domain_count": sum(1 for domain in domains if domain["impacted"]),
        "domains": domains,
        "blocking_domains": blocking,
        "publication_risk": publication_risk,
        "gate_distinctions": [
            "docs_update_required",
            "docs_reviewed_no_change_needed",
            "prd_update_required",
            "contract_atlas_update_required",
            "publication_risk_detected",
            "private_artifact_risk_detected",
        ],
        "empty_state": "No changed files were supplied, so no docs drift is detected.",
    }


def validate_contract_registry(registry: Mapping[str, Any] | None = None) -> list[str]:
    """Validate registry shape and referenced docs."""

    payload = dict(registry or contract_registry())
    errors: list[str] = []
    seen: set[str] = set()
    for domain in payload.get("domains", []):
        domain_id = str(domain.get("domain_id") or "")
        if not domain_id:
            errors.append("domain_id is required")
        if domain_id in seen:
            errors.append(f"duplicate domain_id: {domain_id}")
        seen.add(domain_id)
        for key in ("source_patterns", "contract_refs", "required_doc_refs"):
            if not domain.get(key):
                errors.append(f"domain {domain_id} missing {key}")
        required = set(domain.get("required_doc_refs") or [])
        known_docs = set(domain.get("contract_refs") or []) | set(domain.get("docs_refs") or [])
        missing_known = sorted(required - known_docs)
        if missing_known:
            errors.append(f"domain {domain_id} required docs not declared: {missing_known}")
        if domain.get("release_blocking") is not True:
            errors.append(f"domain {domain_id} must be release blocking")
    return errors


def _matches_any(paths: list[str], patterns: Iterable[str]) -> list[str]:
    return [path for path in paths if any(_matches(path, pattern) for pattern in patterns)]


def _matches(path: str, pattern: str) -> bool:
    normalized = _normalize(path)
    normalized_pattern = _normalize(pattern)
    return fnmatch.fnmatchcase(normalized, normalized_pattern)


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lstrip("./")


def _required_actions(
    domain: Mapping[str, Any],
    impacted: bool,
    missing: list[str],
    reviewed_no_change: bool,
) -> list[str]:
    if not impacted:
        return []
    if reviewed_no_change:
        return ["docs_reviewed_no_change_needed"]
    actions: list[str] = []
    if missing:
        actions.append("docs_update_required")
    if PRD_DOC in missing:
        actions.append("prd_update_required")
    if README_DOC in missing:
        actions.append("readme_update_required")
    if CONTRACT_ATLAS_DOC in missing or domain.get("domain_id") == "contract_atlas":
        if missing:
            actions.append("contract_atlas_update_required")
    if PUBLICATION_BOUNDARY_DOC in missing:
        actions.append("publication_boundary_review_required")
    return actions


def _publication_required_actions(
    *,
    publication_risk_detected: bool,
    private_artifact_risk_detected: bool,
) -> list[str]:
    actions: list[str] = []
    if publication_risk_detected:
        actions.append("publication_boundary_review")
    if private_artifact_risk_detected:
        actions.append("remove_private_artifact_from_repo_change_set")
    return actions
