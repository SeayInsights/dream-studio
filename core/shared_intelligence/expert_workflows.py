"""Expert workflow catalog and overlap decisions.

The catalog formalizes Dream Studio's expert workflow system without creating
duplicate skills. It is a deterministic read model over repo-owned skills,
workflows, and authority tables. Runtime execution can persist results through
existing SQLite authority tables, but this module does not write to SQLite.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any

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


def expert_workflow_catalog(*, project_id: str | None = None) -> dict[str, Any]:
    """Return the repo-backed expert workflow catalog."""

    workflows = [_workflow_definition(workflow_id) for workflow_id in sorted(REQUIRED_WORKFLOW_IDS)]
    overlap = _overlap_matrix(workflows)
    decision_counts = Counter(row["decision"] for row in overlap)
    return {
        "schema": EXPERT_WORKFLOW_CATALOG_SCHEMA,
        "model_name": "dream_studio_expert_workflow_catalog",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "project_id": project_id,
        "derived_view": True,
        "primary_authority": False,
        "routing_authority": False,
        "db_write_authorized": False,
        "execution_authorized": False,
        "policy_mutation_authorized": False,
        "workflow_count": len(workflows),
        "required_workflow_count": len(REQUIRED_WORKFLOW_IDS),
        "workflows": workflows,
        "overlap_matrix": overlap,
        "overlap_decision_counts": dict(sorted(decision_counts.items())),
        "specialized_skill_families": {
            "frontend_design_excellence_workflow": list(DESIGN_SPECIALIZED_SKILLS),
        },
        "application_automation_boundaries": list(APPLICATION_AUTOMATION_BOUNDARIES),
        "authority_write_targets": list(AUTHORITY_WRITE_TARGETS),
        "sqlite_authority_mode": (
            "workflow outputs should persist through current authority tables; "
            "this catalog does not create a competing skill database"
        ),
        "no_duplicate_skill_policy": (
            "strengthen or map existing skills when responsibilities overlap; create only "
            "when no owner exists or the responsibility is clearly separate"
        ),
        "empty_state": "No expert workflows are registered.",
    }


def workflow_by_id(workflow_id: str) -> dict[str, Any]:
    """Return a single workflow definition by id."""

    catalog = expert_workflow_catalog()
    for workflow in catalog["workflows"]:
        if workflow["workflow_id"] == workflow_id:
            return workflow
    raise ValueError(f"unknown expert workflow: {workflow_id}")


def validate_expert_workflow_catalog(catalog: Mapping[str, Any] | None = None) -> list[str]:
    """Validate catalog completeness, overlap decisions, and privacy boundaries."""

    payload = dict(catalog or expert_workflow_catalog())
    errors: list[str] = []
    if payload.get("derived_view") is not True:
        errors.append("derived_view must be true")
    if payload.get("primary_authority") is not False:
        errors.append("primary_authority must be false")
    if payload.get("db_write_authorized") is not False:
        errors.append("db_write_authorized must be false")
    workflow_ids = {str(item.get("workflow_id")) for item in payload.get("workflows", [])}
    missing = sorted(REQUIRED_WORKFLOW_IDS - workflow_ids)
    if missing:
        errors.append(f"missing workflows: {missing}")
    for workflow in payload.get("workflows", []):
        workflow_id = str(workflow.get("workflow_id") or "")
        for key in (
            "purpose",
            "when_to_run",
            "when_not_to_run",
            "input_contract",
            "output_contract",
            "scoring_rubric",
            "evidence_requirements",
            "validation_requirements",
            "dashboard_project_details_visibility",
            "contract_atlas_impact",
            "remediation_work_order_behavior",
            "privacy_publication_boundary",
            "skill_overlap_supersession_status",
            "authority_write_targets",
        ):
            if not workflow.get(key):
                errors.append(f"workflow {workflow_id} missing {key}")
        for score in workflow.get("scoring_rubric", []):
            if score.get("evidence_required") is not True:
                errors.append(f"workflow {workflow_id} score lacks evidence requirement")
            if "unavailable" not in str(score.get("missing_evidence_behavior", "")):
                errors.append(f"workflow {workflow_id} score lacks unavailable state")
    for row in payload.get("overlap_matrix", []):
        decision = row.get("decision")
        owner = row.get("proposed_canonical_owner")
        if decision not in DECISION_VALUES:
            errors.append(f"invalid overlap decision: {decision}")
        if not owner:
            errors.append(f"overlap row {row.get('workflow_id')} missing owner")
        if (
            decision == "create_new"
            and row.get("existing_surfaces")
            and not row.get("separate_responsibility")
        ):
            errors.append(f"overlap row {row.get('workflow_id')} creates duplicate owner")
    design_skills = set(
        payload.get("specialized_skill_families", {}).get("frontend_design_excellence_workflow", [])
    )
    missing_design = sorted(set(DESIGN_SPECIALIZED_SKILLS) - design_skills)
    if missing_design:
        errors.append(f"missing design specialized skills: {missing_design}")
    missing_boundaries = sorted(
        set(APPLICATION_AUTOMATION_BOUNDARIES)
        - set(payload.get("application_automation_boundaries", []))
    )
    if missing_boundaries:
        errors.append(f"application automation boundaries missing: {missing_boundaries}")
    return errors


def _workflow_definition(workflow_id: str) -> dict[str, Any]:
    base = _WORKFLOW_BASES[workflow_id]
    return {
        "workflow_id": workflow_id,
        "workflow_owner": base["workflow_owner"],
        "skill_owner": base["skill_owner"],
        "purpose": base["purpose"],
        "when_to_run": base["when_to_run"],
        "when_not_to_run": base["when_not_to_run"],
        "input_contract": base["input_contract"],
        "output_contract": base["output_contract"],
        "scoring_rubric": _score_rubric(base["scores"]),
        "evidence_requirements": base["evidence_requirements"],
        "validation_requirements": base["validation_requirements"],
        "dashboard_project_details_visibility": base["dashboard_visibility"],
        "contract_atlas_impact": base["contract_atlas_impact"],
        "remediation_work_order_behavior": (
            "Create scoped remediation Work Orders only for evidence-backed findings; "
            "manual-review or missing-evidence items become dashboard attention."
        ),
        "privacy_publication_boundary": base["privacy_boundary"],
        "authority_write_targets": list(AUTHORITY_WRITE_TARGETS),
        "structured_output_contract": {
            "status_values": [
                "pass",
                "warn",
                "fail",
                "not_applicable",
                "manual_review_required",
                "unavailable",
            ],
            "required_fields": [
                "project_id",
                "workflow_id",
                "assessment_id",
                "status",
                "evidence_refs",
                "source_refs",
                "findings",
                "remediation_work_orders",
                "missing_evidence",
            ],
        },
        "skill_overlap_supersession_status": base["overlap_status"],
        "existing_owners": base["existing_owners"],
        "specialized_skills": base.get("specialized_skills", []),
    }


def _score_rubric(score_ids: tuple[str, ...]) -> list[dict[str, Any]]:
    return [
        {
            "score_id": score_id,
            "scale": "0_to_5_or_unavailable",
            "evidence_required": True,
            "confidence_required": True,
            "missing_evidence_behavior": "mark_unavailable_or_partial_with_reason",
            "fake_precision_allowed": False,
        }
        for score_id in score_ids
    ]


def _overlap_matrix(workflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for workflow in workflows:
        status = workflow["skill_overlap_supersession_status"]
        rows.append(
            {
                "workflow_id": workflow["workflow_id"],
                "existing_skill_or_workflow": ", ".join(workflow["existing_owners"]),
                "proposed_canonical_owner": workflow["workflow_owner"],
                "overlap_reason": status["overlap_reason"],
                "decision": status["decision"],
                "evidence": status["evidence"],
                "validation_requirement": status["validation_requirement"],
                "rollback_supersession_plan": status["rollback_supersession_plan"],
                "dashboard_project_health_impact": status["dashboard_project_health_impact"],
                "contract_atlas_impact": workflow["contract_atlas_impact"],
                "existing_surfaces": workflow["existing_owners"],
                "separate_responsibility": status.get("separate_responsibility", False),
            }
        )
    return rows


_WORKFLOW_BASES: dict[str, dict[str, Any]] = {
    "api_integration_design_workflow": {
        "workflow_owner": "domains:fullstack/spec+integrate",
        "skill_owner": "ds-domains/fullstack",
        "purpose": "Design API and integration boundaries before client/server drift appears.",
        "when_to_run": [
            "new or changed routes",
            "client/server contract changes",
            "integration or auth boundary work",
        ],
        "when_not_to_run": ["pure copy changes", "offline docs with no API surface"],
        "input_contract": [
            "route shape",
            "auth/authz model",
            "schema/versioning needs",
            "client compatibility constraints",
        ],
        "output_contract": [
            "API contract",
            "risk findings",
            "validation plan",
            "client compatibility notes",
        ],
        "scores": ("api_contract_quality", "integration_resilience", "auth_boundary_confidence"),
        "evidence_requirements": [
            "route files",
            "schema/contracts",
            "auth middleware",
            "tests or API smoke evidence",
        ],
        "validation_requirements": ["contract tests", "authz checks", "error contract checks"],
        "dashboard_visibility": "Project Details API readiness and release blockers.",
        "contract_atlas_impact": "expert_workflow_system.api_integration_design",
        "privacy_boundary": "Do not expose private endpoint data or credentials in public docs.",
        "existing_owners": ["skills/domains/modes/fullstack", "core/production_readiness"],
        "overlap_status": {
            "decision": "strengthen_existing",
            "overlap_reason": "Fullstack spec mode already owns API contracts; readiness controls cover resilience.",
            "evidence": ["skills/domains/modes/fullstack/SKILL.md", "core/production_readiness"],
            "validation_requirement": "catalog test plus API readiness representative check",
            "rollback_supersession_plan": "Revert catalog mapping; fullstack skill remains unchanged.",
            "dashboard_project_health_impact": "API findings can affect readiness/release blockers.",
        },
    },
    "code_quality_architecture_workflow": {
        "workflow_owner": "quality:review+structure-audit",
        "skill_owner": "ds-quality",
        "purpose": "Evaluate maintainability, architecture boundaries, and correctness beyond lint and format.",
        "when_to_run": [
            "shared code changes",
            "architecture changes",
            "release readiness",
            "quality reviews",
        ],
        "when_not_to_run": ["single documentation typo", "non-code evidence-only update"],
        "input_contract": [
            "changed files",
            "module contracts",
            "test/lint evidence",
            "architecture constraints",
        ],
        "output_contract": [
            "quality scorecard",
            "findings",
            "remediation Work Orders",
            "missing evidence",
        ],
        "scores": (
            "readability",
            "duplication",
            "type_safety",
            "boundary_alignment",
            "testability",
        ),
        "evidence_requirements": [
            "diff",
            "tests",
            "module contracts",
            "imports/routes",
            "lint/type output",
        ],
        "validation_requirements": [
            "focused tests",
            "boundary checks where available",
            "review findings",
        ],
        "dashboard_visibility": "Project Details quality and release-readiness signals.",
        "contract_atlas_impact": "expert_workflow_system.code_quality_architecture",
        "privacy_boundary": "No private source snippets in public exports unless source is public.",
        "existing_owners": ["skills/core/modes/review", "skills/quality/modes/structure-audit"],
        "overlap_status": {
            "decision": "strengthen_existing",
            "overlap_reason": "Review and structure-audit already cover correctness and architecture shape.",
            "evidence": [
                "skills/core/modes/review/SKILL.md",
                "skills/quality/modes/structure-audit",
            ],
            "validation_requirement": "catalog scorecard test plus release-gate coverage",
            "rollback_supersession_plan": "Revert catalog mapping; review modes remain unchanged.",
            "dashboard_project_health_impact": "Quality blockers can lower health confidence and release readiness.",
        },
    },
    "data_modeling_authority_workflow": {
        "workflow_owner": "core:sqlite_authority",
        "skill_owner": "ds-quality/harden",
        "purpose": "Protect SQLite authority, read models, migrations, backfills, and projection boundaries.",
        "when_to_run": [
            "schema changes",
            "backfills",
            "read model changes",
            "authority/projection changes",
        ],
        "when_not_to_run": ["frontend-only copy updates", "non-authoritative markdown edits"],
        "input_contract": [
            "table ownership",
            "migration/backfill plan",
            "source refs",
            "rollback path",
        ],
        "output_contract": [
            "authority design review",
            "migration safety result",
            "manual-review flags",
        ],
        "scores": (
            "authority_fit",
            "migration_safety",
            "source_ref_coverage",
            "projection_boundary",
        ),
        "evidence_requirements": [
            "migrations",
            "schema pragma",
            "source refs",
            "read-model callers",
        ],
        "validation_requirements": [
            "migration tests",
            "idempotency checks",
            "live SQLite guard when applicable",
        ],
        "dashboard_visibility": "Project Details database/read-model readiness.",
        "contract_atlas_impact": "expert_workflow_system.data_modeling_authority",
        "privacy_boundary": "Do not print live DB contents or secrets; use schema and counts when possible.",
        "existing_owners": ["docs/DATABASE.md", "core/event_store", "core/analytics_ingestion.py"],
        "overlap_status": {
            "decision": "strengthen_existing",
            "overlap_reason": "SQLite and analytics ingestion already define authority tables and import paths.",
            "evidence": ["docs/DATABASE.md", "core/event_store/migrations"],
            "validation_requirement": "migration/idempotency tests and catalog validation",
            "rollback_supersession_plan": "Revert catalog mapping; schema authority remains migration-backed.",
            "dashboard_project_health_impact": "Unsafe migrations block readiness and release.",
        },
    },
    "documentation_quality_workflow": {
        "workflow_owner": "docs:quality",
        "skill_owner": "ds-core/explain",
        "purpose": "Evaluate whether docs are useful, current, installable, recoverable, and honest.",
        "when_to_run": ["docs changes", "product behavior changes", "release/publication checks"],
        "when_not_to_run": ["internal code-only change with docs reviewed no-change evidence"],
        "input_contract": ["changed docs", "product behavior", "commands", "known limitations"],
        "output_contract": ["docs usefulness scorecard", "drift findings", "examples to fix"],
        "scores": (
            "new_user_installability",
            "developer_contribution_clarity",
            "operator_recovery_clarity",
        ),
        "evidence_requirements": ["docs refs", "command validation", "README/PRD alignment"],
        "validation_requirements": ["docs drift gate", "command smoke where applicable"],
        "dashboard_visibility": "Contract Atlas docs freshness and Project Details docs gaps.",
        "contract_atlas_impact": "expert_workflow_system.documentation_quality",
        "privacy_boundary": "Public docs must not include private paths, telemetry, Work Orders, or career data.",
        "existing_owners": ["core/shared_intelligence/contract_registry.py", "docs/README.md"],
        "overlap_status": {
            "decision": "strengthen_existing",
            "overlap_reason": "Docs drift already tracks freshness; this adds usefulness criteria.",
            "evidence": ["interfaces/cli/contract_docs_drift_gate.py", "docs/README.md"],
            "validation_requirement": "contract docs drift gate plus catalog validation",
            "rollback_supersession_plan": "Revert catalog mapping; drift gate continues freshness checks.",
            "dashboard_project_health_impact": "Docs blockers affect publication readiness, not runtime health unless operator recovery is missing.",
        },
    },
    "frontend_design_excellence_workflow": {
        "workflow_owner": "quality:polish+domains:design",
        "skill_owner": "ds-quality/polish",
        "purpose": "Diagnose and improve UX, visual hierarchy, accessibility, responsive behavior, components, and design-to-code fit.",
        "when_to_run": [
            "UI changes",
            "dashboard changes",
            "public/portfolio pages",
            "design review",
        ],
        "when_not_to_run": ["backend-only work", "private CLI-only changes"],
        "input_contract": [
            "screens/routes",
            "design intent",
            "target users",
            "component/state evidence",
        ],
        "output_contract": [
            "design diagnosis",
            "scorecard",
            "frontend implementation contract",
            "validation checklist",
        ],
        "scores": (
            "ux_clarity",
            "visual_hierarchy",
            "accessibility",
            "responsive_behavior",
            "component_consistency",
            "data_visualization",
            "implementation_feasibility",
        ),
        "evidence_requirements": [
            "screenshots",
            "DOM/routes",
            "CSS/components",
            "a11y/responsive checks",
        ],
        "validation_requirements": [
            "browser screenshot or Playwright when approved",
            "accessibility checklist",
        ],
        "dashboard_visibility": "Project Details design/readiness and dashboard attention for visual blockers.",
        "contract_atlas_impact": "expert_workflow_system.frontend_design_excellence",
        "privacy_boundary": "Screenshots may expose private data; sanitize before publication.",
        "existing_owners": ["skills/quality/modes/polish", "skills/domains/modes/design"],
        "specialized_skills": list(DESIGN_SPECIALIZED_SKILLS),
        "overlap_status": {
            "decision": "split_existing",
            "overlap_reason": "Polish remains the execution skill; specialized review lenses make results reusable without new monolith.",
            "evidence": [
                "skills/quality/modes/polish/SKILL.md",
                "skills/domains/modes/design/SKILL.md",
            ],
            "validation_requirement": "specialized design skill coverage and score rubric tests",
            "rollback_supersession_plan": "Remove catalog specializations; polish/design skills remain active.",
            "dashboard_project_health_impact": "Accessibility and responsive blockers affect readiness.",
        },
    },
    "intentional_implementation_workflow": {
        "workflow_owner": "core:build",
        "skill_owner": "ds-core",
        "purpose": "Require a lightweight implementation contract before code changes.",
        "when_to_run": ["code changes", "schema changes", "workflow changes", "runtime changes"],
        "when_not_to_run": ["read-only inspection", "status reporting", "pure validation"],
        "input_contract": [
            "why code is needed",
            "problem solved",
            "affected layer/module/contract",
            "alternatives considered",
            "best-practice basis",
            "expected impact",
            "validation plan",
            "rollback plan",
        ],
        "output_contract": [
            "implementation contract",
            "changed-file scope",
            "validation evidence",
            "post-change review",
        ],
        "scores": ("implementation_intent_clarity", "scope_fit", "rollback_confidence"),
        "evidence_requirements": [
            "problem statement",
            "affected contracts",
            "test plan",
            "rollback note",
        ],
        "validation_requirements": [
            "post-change correctness review",
            "focused tests",
            "docs drift if impacted",
        ],
        "dashboard_visibility": "Work Order details and release readiness evidence.",
        "contract_atlas_impact": "expert_workflow_system.intentional_implementation",
        "privacy_boundary": "Implementation evidence may remain private when it references local state.",
        "existing_owners": ["skills/core/modes/build", "core/work_orders"],
        "overlap_status": {
            "decision": "strengthen_existing",
            "overlap_reason": "Build and Work Orders already own implementation scope; this formalizes the pre-change contract.",
            "evidence": ["skills/core/modes/build/SKILL.md", "core/work_orders"],
            "validation_requirement": "catalog test asserts required implementation contract fields",
            "rollback_supersession_plan": "Revert catalog mapping; existing build mode continues.",
            "dashboard_project_health_impact": "Missing implementation contract becomes release-readiness attention.",
        },
    },
    "performance_efficiency_workflow": {
        "workflow_owner": "quality:debug/performance",
        "skill_owner": "ds-quality",
        "purpose": "Improve runtime, query, frontend, API, validation, and adapter/tool efficiency.",
        "when_to_run": [
            "slow paths",
            "large payloads",
            "token inefficiency",
            "repeated retries",
            "release hardening",
        ],
        "when_not_to_run": ["unmeasured aesthetic preference", "no performance-sensitive surface"],
        "input_contract": [
            "symptom/metric",
            "trace or profile evidence",
            "affected surface",
            "success target",
        ],
        "output_contract": ["bottleneck diagnosis", "efficiency scorecard", "minimal fix plan"],
        "scores": (
            "latency_confidence",
            "query_efficiency",
            "frontend_render_cost",
            "adapter_efficiency",
        ),
        "evidence_requirements": [
            "profile/logs",
            "query plans if relevant",
            "payload sizes",
            "adapter usage records",
        ],
        "validation_requirements": ["before/after measurement or unavailable reason"],
        "dashboard_visibility": "Project Details performance/readiness and AI operational value telemetry.",
        "contract_atlas_impact": "expert_workflow_system.performance_efficiency",
        "privacy_boundary": "Do not publish private traces or provider billing credentials.",
        "existing_owners": [
            "skills/quality/modes/debug/references/performance-issues.md",
            "core/shared_intelligence/usage_accounting.py",
        ],
        "overlap_status": {
            "decision": "strengthen_existing",
            "overlap_reason": "Debug references cover performance diagnosis; usage accounting covers adapter efficiency.",
            "evidence": [
                "skills/quality/modes/debug/references/performance-issues.md",
                "core/shared_intelligence/usage_accounting.py",
            ],
            "validation_requirement": "performance score rubric and usage-accounting policy tests",
            "rollback_supersession_plan": "Revert catalog mapping; debug performance references remain.",
            "dashboard_project_health_impact": "Measured performance blockers can affect readiness.",
        },
    },
    "product_demo_and_case_study_workflow": {
        "workflow_owner": "docs:portfolio_case_study",
        "skill_owner": "ds-core/explain",
        "purpose": "Turn real project evidence into sanitized demos, scripts, and case-study material.",
        "when_to_run": ["portfolio/demo planning", "publication readiness", "case-study drafting"],
        "when_not_to_run": [
            "no evidence refs",
            "private project details without sanitization approval",
        ],
        "input_contract": [
            "project evidence refs",
            "audience",
            "before/after proof",
            "privacy boundary",
        ],
        "output_contract": [
            "positioning",
            "demo script",
            "case-study outline",
            "sanitization checklist",
        ],
        "scores": ("proof_strength", "demo_readiness", "public_sanitization_readiness"),
        "evidence_requirements": [
            "validation refs",
            "screenshots needed",
            "metrics evidence or missing flags",
        ],
        "validation_requirements": [
            "sanitized export review",
            "operator approval before public use",
        ],
        "dashboard_visibility": "Portfolio/case-study readiness and publication boundary attention.",
        "contract_atlas_impact": "expert_workflow_system.product_demo_case_study",
        "privacy_boundary": "Public case studies require explicit sanitization and approval.",
        "existing_owners": ["docs/demo-script.md", "docs/portfolio-case-study.md"],
        "overlap_status": {
            "decision": "strengthen_existing",
            "overlap_reason": "Demo and portfolio docs already exist; this makes them evidence-backed workflows.",
            "evidence": ["docs/demo-script.md", "docs/portfolio-case-study.md"],
            "validation_requirement": "catalog test plus publication boundary check",
            "rollback_supersession_plan": "Revert catalog mapping; docs remain reference material.",
            "dashboard_project_health_impact": "Does not affect project health unless used for publication readiness.",
        },
    },
    "root_cause_debugging_workflow": {
        "workflow_owner": "quality:debug",
        "skill_owner": "ds-quality",
        "purpose": "Prevent random trial-and-error debugging through hypothesis-ranked root cause analysis.",
        "when_to_run": ["bug reports", "failing validation", "unexpected runtime behavior"],
        "when_not_to_run": ["known simple typo with direct fix and validation", "feature planning"],
        "input_contract": ["symptom", "reproduction plan", "logs/traces", "hypotheses"],
        "output_contract": [
            "root cause",
            "minimal fix",
            "regression test",
            "verification evidence",
        ],
        "scores": ("reproduction_quality", "root_cause_confidence", "regression_protection"),
        "evidence_requirements": [
            "error output",
            "repro steps",
            "hypothesis log",
            "fix verification",
        ],
        "validation_requirements": ["regression test when feasible", "post-fix verification"],
        "dashboard_visibility": "Debug findings, validation failures, and remediation Work Orders.",
        "contract_atlas_impact": "expert_workflow_system.root_cause_debugging",
        "privacy_boundary": "Logs may contain private data; redact before public export.",
        "existing_owners": ["skills/quality/modes/debug/SKILL.md"],
        "overlap_status": {
            "decision": "keep_existing",
            "overlap_reason": "Debug skill already implements disciplined hypothesis testing.",
            "evidence": ["skills/quality/modes/debug/SKILL.md"],
            "validation_requirement": "catalog maps existing debug behavior without duplicate skill",
            "rollback_supersession_plan": "No supersession; keep debug mode as canonical owner.",
            "dashboard_project_health_impact": "Unresolved root cause affects health and release readiness.",
        },
    },
    "seo_content_growth_workflow": {
        "workflow_owner": "domains:website/content",
        "skill_owner": "ds-domains/website",
        "purpose": "Support public-facing sites, docs, portfolio pages, product pages, and marketing surfaces.",
        "when_to_run": ["public/content/marketing surfaces", "portfolio pages", "product pages"],
        "when_not_to_run": ["backend-only work", "private dashboards", "no public content surface"],
        "input_contract": [
            "page intent",
            "audience",
            "metadata/schema",
            "content structure",
            "performance evidence",
        ],
        "output_contract": [
            "SEO/content findings",
            "snippet recommendations",
            "content gap analysis",
        ],
        "scores": (
            "technical_seo",
            "content_intent_fit",
            "conversion_copy_quality",
            "brand_alignment",
        ),
        "evidence_requirements": [
            "routes/pages",
            "metadata",
            "structured data",
            "content copy",
            "performance signals",
        ],
        "validation_requirements": [
            "only run when public/content surface is present",
            "source refs for market claims",
        ],
        "dashboard_visibility": "Publication/readiness and content-surface attention.",
        "contract_atlas_impact": "expert_workflow_system.seo_content_growth",
        "privacy_boundary": "Do not publish private project details, career data, or unsupported claims.",
        "existing_owners": ["skills/domains/modes/website", "docs/PUBLICATION_BOUNDARY.md"],
        "overlap_status": {
            "decision": "strengthen_existing",
            "overlap_reason": "Website domain owns public surfaces; publication boundary owns privacy limits.",
            "evidence": ["skills/domains/modes/website", "docs/PUBLICATION_BOUNDARY.md"],
            "validation_requirement": "catalog validates when-not-to-run backend-only boundary",
            "rollback_supersession_plan": "Revert catalog mapping; website skill remains.",
            "dashboard_project_health_impact": "SEO affects public readiness, not backend health.",
        },
    },
}
