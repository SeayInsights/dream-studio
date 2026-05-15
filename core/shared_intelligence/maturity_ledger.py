"""Current Dream Studio maturity ledger.

The ledger is a derived, repo-backed status map. It does not create authority;
it explains which major areas are hardened, runtime validated, tested only,
designed but unproven, stale, blocked, not started, or manual-review scoped.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

MATURITY_LEDGER_SCHEMA = "dream_studio.maturity_ledger.v1"

MATURITY_STATUSES: frozenset[str] = frozenset(
    {
        "hardened",
        "runtime_validated",
        "tested_only",
        "designed_not_proven",
        "stale",
        "blocked",
        "not_started",
        "manual_review_required",
    }
)

REQUIRED_AREA_IDS: frozenset[str] = frozenset(
    {
        "route_first_engine",
        "work_orders",
        "handoffs_continuation_packets",
        "sqlite_authority",
        "telemetry_spine",
        "dashboard_api_frontend",
        "project_registry",
        "prd_authority",
        "security_analytics",
        "skill_workflow_hook_telemetry",
        "shared_intelligence",
        "claude_adapter",
        "codex_adapter",
        "model_provider_registry",
        "context_packets",
        "adapter_result_normalization",
        "contract_atlas",
        "documentation_drift_gate",
        "docker_runtime_profiles",
        "analytics_only_profile",
        "external_project_pipeline",
        "docker_module_runtime_boundary",
        "long_run_multisession_validation",
        "installed_productization_closeout",
        "github_pr_ci_release_gate",
        "publication_privacy_readiness",
        "expert_workflow_system",
        "career_ops_private_module",
        "capability_center_scoped_agents",
        "github_repo_intake_evaluation",
        "task_attribution_outcome_tracking",
    }
)

MATURITY_AREAS: tuple[dict[str, Any], ...] = (
    {
        "area_id": "route_first_engine",
        "area_name": "Route-first engine",
        "status": "runtime_validated",
        "owner_source": "core/work_orders + route decision tests",
        "evidence": ["tests/unit/test_work_order_milestones.py"],
        "validation": ["route-first/handoff regression tests"],
        "known_gaps": ["visual route-state explanation remains a dashboard maturity layer"],
        "next_action": "Expose route decision explainability through Contract Atlas/dashboard.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "work_orders",
        "area_name": "Work Orders",
        "status": "runtime_validated",
        "owner_source": "core/work_orders",
        "evidence": ["docs/contracts/work-order-contract.md"],
        "validation": ["tests/unit/test_work_order_contracts_static.py"],
        "known_gaps": ["SQLite-first canonical Work Order storage is still maturing"],
        "next_action": "Continue SQLite-first artifact authority maturation.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "handoffs_continuation_packets",
        "area_name": "Handoffs and continuation packets",
        "status": "runtime_validated",
        "owner_source": "docs/contracts/handoff-packet-contract.md",
        "evidence": ["tests/unit/test_handoff_prompt_eval.py"],
        "validation": ["handoff prompt and next-prompt contract tests"],
        "known_gaps": ["handoffs remain exceptional, not normal workflow transitions"],
        "next_action": "Keep route-first guardrails blocking prompt-chaining regressions.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "sqlite_authority",
        "area_name": "SQLite authority",
        "status": "runtime_validated",
        "owner_source": "core/event_store + core/config/database.py",
        "evidence": ["docs/DATABASE.md", "docs/MIGRATION_AUTHORITY.md"],
        "validation": ["tests/unit/test_install_bootstrap_sqlite_authority.py"],
        "known_gaps": ["not every historical artifact has been promoted to SQLite canonical form"],
        "next_action": "Finish SQLite-first artifact authority maturation.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "telemetry_spine",
        "area_name": "Telemetry spine",
        "status": "runtime_validated",
        "owner_source": "core/telemetry",
        "evidence": ["core/event_store/migrations/037_execution_telemetry_traceability_spine.sql"],
        "validation": ["tests/unit/test_end_to_end_traceability_loop.py"],
        "known_gaps": ["context completeness still has room to reduce null/unknown IDs"],
        "next_action": "Continue telemetry context completeness maturation.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "dashboard_api_frontend",
        "area_name": "Dashboard/API/frontend",
        "status": "runtime_validated",
        "owner_source": "projections/api + projections/frontend/dashboard.html",
        "evidence": ["docs/architecture/dream-studio-dashboard-projection-mapping.md"],
        "validation": ["tests/unit/test_actual_dashboard_telemetry_routes.py"],
        "known_gaps": ["full visual Contract Atlas dashboard remains a later maturity layer"],
        "next_action": "Build visual Contract Atlas dashboard after foundation is stable.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "project_registry",
        "area_name": "Project registry",
        "status": "runtime_validated",
        "owner_source": "core/projects + project dashboard views",
        "evidence": ["tests/unit/test_project_registry_paused_targets.py"],
        "validation": ["project portfolio authority/security hydration tests"],
        "known_gaps": ["external project mutation remains approval-scoped"],
        "next_action": "Keep external targets paused unless registry scope explicitly opens them.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "prd_authority",
        "area_name": "PRD authority",
        "status": "runtime_validated",
        "owner_source": "docs/product/dream-studio-prd.md",
        "evidence": ["docs/product/dream-studio-stage-gates.yaml"],
        "validation": ["tests/unit/test_operator_documentation_readiness.py"],
        "known_gaps": [
            "PRD must stay current through docs drift gate when product authority changes"
        ],
        "next_action": "Use the drift gate to block stale product-authority docs.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "security_analytics",
        "area_name": "Security analytics",
        "status": "runtime_validated",
        "owner_source": "core/telemetry + projections/api/routes/security.py",
        "evidence": ["docs/contracts/security-review-source-47-enterprise-scans.md"],
        "validation": ["tests/unit/test_validation_security_telemetry_emitters.py"],
        "known_gaps": ["project-wide scanner execution remains bounded by scope and approval"],
        "next_action": "Mature security drilldowns and remediation work-order generation.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "skill_workflow_hook_telemetry",
        "area_name": "Skill, workflow, and hook telemetry",
        "status": "runtime_validated",
        "owner_source": "core/telemetry + runtime/hooks",
        "evidence": ["tests/unit/test_hook_runtime_reliability.py"],
        "validation": ["skill/token, workflow/research/decision, and hook route tests"],
        "known_gaps": ["component performance analytics can be deepened"],
        "next_action": "Continue component hardening intelligence.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "shared_intelligence",
        "area_name": "Shared intelligence",
        "status": "runtime_validated",
        "owner_source": "core/shared_intelligence",
        "evidence": ["docs/architecture/shared-authority-and-adapter-projections.md"],
        "validation": ["tests/unit/test_actual_shared_intelligence_routes.py"],
        "known_gaps": ["live multi-adapter execution is not fully proven"],
        "next_action": "Validate agent/model independence and multi-agent demo boundaries.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "claude_adapter",
        "area_name": "Claude adapter",
        "status": "tested_only",
        "owner_source": "CLAUDE.md + local Claude hook surface",
        "evidence": ["core/shared_intelligence/adapter_staleness.py"],
        "validation": ["command-level UserPromptSubmit smoke"],
        "known_gaps": ["real Claude process execution consuming the projection is unproven"],
        "next_action": "Run an explicitly approved live Claude adapter execution validation.",
        "can_claim_publicly": False,
        "can_use_operationally": True,
    },
    {
        "area_id": "codex_adapter",
        "area_name": "Codex adapter",
        "status": "tested_only",
        "owner_source": "AGENTS.md + local Codex hook surface",
        "evidence": ["core/shared_intelligence/adapter_staleness.py"],
        "validation": ["command-level UserPromptSubmit smoke"],
        "known_gaps": [
            "real Codex hook execution on fresh message submission is not independently proven here"
        ],
        "next_action": "Keep Codex hook compatibility monitored during local dogfood.",
        "can_claim_publicly": False,
        "can_use_operationally": True,
    },
    {
        "area_id": "model_provider_registry",
        "area_name": "Model/provider registry",
        "status": "tested_only",
        "owner_source": "core/shared_intelligence/model_registry.py",
        "evidence": ["tests/unit/test_shared_intelligence_model_registry.py"],
        "validation": ["model-provider route and capability matrix tests"],
        "known_gaps": ["provider costs and quality signals require ongoing real usage evidence"],
        "next_action": "Correlate model/provider outcomes with token and validation data.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "context_packets",
        "area_name": "Context packets",
        "status": "tested_only",
        "owner_source": "core/shared_intelligence/context_packets.py",
        "evidence": ["tests/unit/test_shared_intelligence_context_packets.py"],
        "validation": ["context packet preview tests"],
        "known_gaps": [
            "cross-model live resume remains dry-run/simulated unless separately approved"
        ],
        "next_action": "Prove agent/model independence with a real adapter handoff when safe.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "adapter_result_normalization",
        "area_name": "Adapter result normalization",
        "status": "tested_only",
        "owner_source": "core/shared_intelligence/result_normalization.py",
        "evidence": ["tests/unit/test_shared_intelligence_result_normalization.py"],
        "validation": ["normalized adapter result tests"],
        "known_gaps": ["more real adapter result shapes should be sampled during dogfood"],
        "next_action": "Capture real adapter outputs as normalized result fixtures.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "task_attribution_outcome_tracking",
        "area_name": "Task attribution and execution outcomes",
        "status": "runtime_validated",
        "owner_source": "core/shared_intelligence/task_attribution.py",
        "evidence": ["core/event_store/migrations/045_task_attribution_authority.sql"],
        "validation": ["tests/unit/test_task_attribution.py"],
        "known_gaps": [
            "Real adapter runs must keep supplying complete source refs to reduce unknown fields"
        ],
        "next_action": "Use attribution records in Work Order and Project Details dogfood cycles.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "contract_atlas",
        "area_name": "Contract Atlas",
        "status": "runtime_validated",
        "owner_source": "core/shared_intelligence/contract_atlas.py",
        "evidence": ["docs/architecture/contract-atlas.md"],
        "validation": ["tests/unit/test_contract_atlas.py"],
        "known_gaps": ["full visual dashboard layer is intentionally deferred"],
        "next_action": "Build the visual Contract Atlas dashboard layer.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "documentation_drift_gate",
        "area_name": "Documentation drift gate",
        "status": "hardened",
        "owner_source": "interfaces/cli/contract_docs_drift_gate.py",
        "evidence": ["docs/operations/lint-format-baseline-policy.md"],
        "validation": ["full ci_gate.py including contract-docs-drift"],
        "known_gaps": ["reviewed-no-change decisions require explicit gate input"],
        "next_action": "Keep source-to-doc impact matrix current as new domains appear.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "docker_runtime_profiles",
        "area_name": "Docker/runtime profiles",
        "status": "tested_only",
        "owner_source": "core/telemetry/docker_profiles.py",
        "evidence": ["docs/operations/docker-module-profiles.md"],
        "validation": ["tests/unit/test_docker_module_profiles.py"],
        "known_gaps": [
            "Docker profile contracts are static-tested; containers are not started or required"
        ],
        "next_action": "Run optional Docker runtime validation only after explicit approval.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "analytics_only_profile",
        "area_name": "Analytics-only profile",
        "status": "runtime_validated",
        "owner_source": "core/analytics_ingestion.py + core/module_profiles.py",
        "evidence": ["docs/operations/installed-platform-productization.md"],
        "validation": [
            "tests/unit/test_analytics_only_deployment_profile.py",
            "tests/unit/test_installed_platform_productization.py",
        ],
        "known_gaps": ["analytics import quality depends on normalized source evidence"],
        "next_action": "Keep ingestion contracts aligned with current authority tables.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "external_project_pipeline",
        "area_name": "External project pipeline",
        "status": "runtime_validated",
        "owner_source": "core/projects/external_validation.py",
        "evidence": ["tests/unit/test_external_project_validation_pipeline.py"],
        "validation": ["paused target, read-only intake, and external dashboard tests"],
        "known_gaps": ["external project mutation remains approval-scoped and not auto-resumed"],
        "next_action": "Use explicit target selection before any read-only external intake.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "docker_module_runtime_boundary",
        "area_name": "Docker module runtime boundary",
        "status": "tested_only",
        "owner_source": "core/telemetry/docker_profiles.py",
        "evidence": ["docs/operations/docker-module-profiles.md"],
        "validation": ["tests/unit/test_docker_module_profiles.py"],
        "known_gaps": ["container execution is intentionally not proven without approval"],
        "next_action": "Keep Docker optional and non-authoritative unless a profile is approved.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "long_run_multisession_validation",
        "area_name": "Long-run multisession validation",
        "status": "tested_only",
        "owner_source": "core/release/local_dogfood_stability.py",
        "evidence": ["tests/unit/test_long_run_multisession_operational_validation.py"],
        "validation": ["multisession cycle and live SQLite hash guard tests"],
        "known_gaps": ["full dogfood evidence must be refreshed before each release decision"],
        "next_action": "Run live evidence cycles before public release or external use decisions.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "installed_productization_closeout",
        "area_name": "Installed productization closeout",
        "status": "tested_only",
        "owner_source": "core/installed_productization.py",
        "evidence": ["docs/operations/installed-platform-productization.md"],
        "validation": ["tests/unit/test_installed_platform_productization.py"],
        "known_gaps": ["public release requires explicit operator decision after closeout"],
        "next_action": "Route to operator decision on private dogfood, public release, or external use.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "github_pr_ci_release_gate",
        "area_name": "GitHub PR/CI release gate",
        "status": "tested_only",
        "owner_source": "core/release/github_pr_cicd_gate.py",
        "evidence": [
            "runtime/config/release-gates/dream-studio.json",
            ".github/workflows/ci.yml",
            ".github/workflows/full-ci.yml",
            ".github/workflows/release-validation.yml",
        ],
        "validation": [
            "tests/unit/test_github_pr_cicd_release_gate.py",
            "Contract Atlas github_cicd_profile",
        ],
        "known_gaps": [
            "live GitHub polling/merge remains approval and CI-state dependent",
            "full remote CI is manual to preserve Actions minutes",
        ],
        "next_action": "Use PR smoke as remote confidence and local ci_gate.py as the heavy release gate.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "publication_privacy_readiness",
        "area_name": "Publication/privacy readiness",
        "status": "runtime_validated",
        "owner_source": "core/release/repo_publication_readiness.py",
        "evidence": [
            "docs/PUBLICATION_BOUNDARY.md",
            "docs/operations/repo-publication-privacy.md",
            "docs/publication/repo_publication_cleanliness_certificate.yaml",
        ],
        "validation": [
            "python interfaces/cli/repo_publication_readiness.py --strict",
            "publication boundary and private-path scans",
        ],
        "known_gaps": [
            "history rewrite remains a separate explicit approval boundary if a future scan finds blockers"
        ],
        "next_action": "Run publication readiness before push/tag/release decisions.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "expert_workflow_system",
        "area_name": "Expert workflow system",
        "status": "tested_only",
        "owner_source": "core/shared_intelligence/expert_workflows.py",
        "evidence": ["docs/operations/expert-workflow-systems.md"],
        "validation": ["tests/unit/test_expert_workflow_catalog.py"],
        "known_gaps": [
            "dashboard rendering can be deepened after the catalog and API route are stable"
        ],
        "next_action": "Use the catalog to drive scored workflow outputs during dogfood.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "career_ops_private_module",
        "area_name": "Career Ops private module",
        "status": "tested_only",
        "owner_source": "core/career_ops.py",
        "evidence": ["docs/operations/career-ops-capability-center.md"],
        "validation": ["tests/unit/test_career_ops_capability_agent_github.py"],
        "known_gaps": ["live profile editing UX remains a private dashboard maturity layer"],
        "next_action": "Dogfood private profile/application records only after explicit operator opt-in.",
        "can_claim_publicly": False,
        "can_use_operationally": True,
    },
    {
        "area_id": "capability_center_scoped_agents",
        "area_name": "Capability Center and scoped agents",
        "status": "tested_only",
        "owner_source": "core/shared_intelligence/capability_center.py",
        "evidence": ["docs/operations/career-ops-capability-center.md"],
        "validation": ["tests/unit/test_career_ops_capability_agent_github.py"],
        "known_gaps": ["invocation quality scoring improves as more real dogfood evidence accrues"],
        "next_action": "Record capability evaluations during future Work Orders.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
    {
        "area_id": "github_repo_intake_evaluation",
        "area_name": "GitHub repo intake evaluation",
        "status": "tested_only",
        "owner_source": "core/shared_intelligence/github_repo_intake.py",
        "evidence": ["docs/operations/github-repo-intake-evaluation.md"],
        "validation": ["tests/unit/test_career_ops_capability_agent_github.py"],
        "known_gaps": ["live GitHub metadata fetch remains a future approval-scoped producer"],
        "next_action": "Use repo intake before adopting third-party code, dependencies, prompts, or patterns.",
        "can_claim_publicly": True,
        "can_use_operationally": True,
    },
)


def maturity_ledger(*, project_id: str | None = None) -> dict[str, Any]:
    """Return the current evidence-backed maturity ledger."""

    areas = [dict(area) for area in MATURITY_AREAS]
    counts = Counter(area["status"] for area in areas)
    return {
        "schema": MATURITY_LEDGER_SCHEMA,
        "model_name": "dream_studio_current_maturity_ledger",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "db_write_authorized": False,
        "source": "repo_backed_maturity_ledger",
        "area_count": len(areas),
        "status_counts": dict(sorted(counts.items())),
        "areas": areas,
        "public_claim_boundary": (
            "Areas with can_claim_publicly=false must not be marketed as live-proven."
        ),
        "operational_use_boundary": (
            "Areas with can_use_operationally=false remain design or future-work surfaces."
        ),
        "empty_state": "No maturity areas are registered.",
    }


def validate_maturity_ledger(ledger: Mapping[str, Any] | None = None) -> list[str]:
    """Validate the maturity ledger is complete and evidence-backed."""

    payload = dict(ledger or maturity_ledger())
    errors: list[str] = []
    if payload.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if payload.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if payload.get("db_write_authorized") is not False:
        errors.append("db_write_authorized must be false")
    areas = payload.get("areas") or []
    seen = {str(area.get("area_id")) for area in areas}
    missing = sorted(REQUIRED_AREA_IDS - seen)
    if missing:
        errors.append(f"missing maturity areas: {missing}")
    for area in areas:
        area_id = str(area.get("area_id") or "")
        status = area.get("status")
        if status not in MATURITY_STATUSES:
            errors.append(f"area {area_id} has invalid status: {status}")
        for key in (
            "evidence",
            "validation",
            "owner_source",
            "known_gaps",
            "next_action",
        ):
            if not area.get(key):
                errors.append(f"area {area_id} missing {key}")
        if not isinstance(area.get("can_claim_publicly"), bool):
            errors.append(f"area {area_id} missing public claim flag")
        if not isinstance(area.get("can_use_operationally"), bool):
            errors.append(f"area {area_id} missing operational use flag")
    return errors
