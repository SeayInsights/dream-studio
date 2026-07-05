# Expert Workflow Systems

Lifecycle status: foundation_active

Dream Studio expert workflows formalize how existing skills, workflows,
readiness gates, dashboard views, and Contract Atlas signals cooperate. The
catalog is repo-backed and deterministic. It does not create a competing skill
database, execute work, write SQLite by itself, or replace existing debugging,
design, quality, documentation, or fullstack skills.

## Authority Boundary

Current implementation:

- `core/shared_intelligence/expert_workflows.py` declares the expert workflow
  catalog, overlap matrix, and scoring rubrics.
- `/api/shared-intelligence/expert-workflows` exposes the catalog as a derived
  dashboard-consumable view.
- Contract Atlas exposes an `expert_workflow_system` summary, maturity
  scorecard row, and confirmed dependency edges to the existing skill/workflow
  owners.
- Workflow outputs should persist through existing authority tables such as
  `workflow_invocations`, `skill_invocations`,
  `research_evidence_records`, `validation_results`, `artifact_records`,
  and Work Order records when an executing runtime
  is explicitly authorized to write. (`decision_records` and
  `dashboard_attention_items` were dropped in migration 139, WO-AI-SPINE — pure
  duplication of the execution_events dual-write already performed by these
  writers.)

The catalog is a read model. It does not authorize database writes, browser
automation, external project mutation, publishing, push, deploy, Docker, or
cleanup.

## Overlap Policy

Dream Studio audits existing skills before adding new responsibilities. The
allowed decisions are:

- `keep_existing`
- `strengthen_existing`
- `split_existing`
- `merge_duplicate`
- `create_new`
- `supersede_existing`
- `deprecate_existing`
- `manual_review_required`

New skills are not created when an existing skill already owns the work. The
current expert catalog mostly strengthens existing owners:

| Workflow | Canonical owner | Decision |
| --- | --- | --- |
| `intentional_implementation_workflow` | `core:build` | `strengthen_existing` |
| `code_quality_architecture_workflow` | `quality:review+structure-audit` | `strengthen_existing` |
| `root_cause_debugging_workflow` | `quality:debug` | `keep_existing` |
| `performance_efficiency_workflow` | `quality:debug/performance` | `strengthen_existing` |
| `frontend_design_excellence_workflow` | `quality:polish+domains:design` | `split_existing` |
| `seo_content_growth_workflow` | `domains:website/content` | `strengthen_existing` |
| `documentation_quality_workflow` | `docs:quality` | `strengthen_existing` |
| `data_modeling_authority_workflow` | `core:sqlite_authority` | `strengthen_existing` |
| `api_integration_design_workflow` | `domains:fullstack/spec+integrate` | `strengthen_existing` |
| `product_demo_and_case_study_workflow` | `docs:portfolio_case_study` | `strengthen_existing` |

## Workflow Contracts

Every expert workflow declares:

- purpose;
- when to run;
- when not to run;
- input contract;
- output contract;
- evidence requirements;
- validation requirements;
- evidence-backed scoring rubric;
- dashboard or Project Details visibility;
- Contract Atlas impact;
- remediation Work Order behavior;
- privacy/publication boundary;
- overlap or supersession status.

Scores must be evidence-backed. Missing evidence is `unavailable` or `partial`
with a reason, never fake precision.

## Intentional Implementation

Implementation work must record a lightweight contract before code changes when
applicable:

- why code is needed;
- problem solved;
- affected layer, module, or contract;
- alternatives considered;
- best-practice basis;
- smallest safe implementation;
- expected side effects;
- validation plan;
- rollback plan;
- post-change correctness review.

This strengthens `ds-core` build and Work Orders rather than creating a new
implementation skill.

## Design Workflow

Frontend design excellence is not one monolithic skill. It maps existing
`quality:polish` and `domains:design` behavior into specialized review lenses:

- `product_ux_review`
- `information_architecture_review`
- `visual_design_system_review`
- `responsive_layout_review`
- `component_architecture_review`
- `accessibility_review`
- `interaction_motion_review`
- `data_visualization_review`
- `implementation_feasibility_review`
- `design_to_code_contract`

Evidence can include screenshots, routes, components, CSS, tokens, accessibility
checks, responsive checks, and implementation feasibility notes. Screenshots and
design artifacts that expose private data must be sanitized before publication.

## Capability Center Integration

Expert workflow definitions feed Capability Center as workflow capability
records. Capability Center can show invocation counts, scorecard availability,
validation requirements, hardening candidates, and task-attributed outcomes,
but it does not create a parallel workflow system or authorize execution.
Missing invocation/evaluation or attribution evidence stays `unavailable`
instead of becoming a fake success rate.

## Validation

The expert workflow system is validated by:

- `tests/unit/test_expert_workflow_catalog.py`;
- Contract Atlas validation;
- Contract Atlas docs drift gate;
- release gate checks.

The validation proves the overlap matrix exists, existing owners are mapped
instead of duplicated, scoring rubrics require evidence, and design
specializations are declared.
## Platform Hardening Refresh

The skill evaluation harness gives expert workflows a measurable promotion path: golden fixtures, expected-output contracts, rubric scores, pass/warn/fail/manual-review states, promotion thresholds, rollback thresholds, and known limitations. A workflow should not be marked improved unless an evaluation run records evidence in current authority.

## PRD Lifecycle Interaction

Intentional implementation, code quality, debugging, design, data modeling,
API integration, documentation, and release workflows should consume the
current PRD version, milestone, Work Order, assumptions, change orders, and
stop gates before recommending implementation. Workflow outputs may create
remediation Work Orders or evidence refs, but they do not silently rewrite PRD
authority.

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. Removed the `career_strategy_and_portfolio_ops_workflow` overlap-matrix row, the entire "Career And Portfolio Boundary" section, the Career-Ops-module mapping paragraph under Capability Center Integration, and career clauses from the intro, authority-boundary, and validation lists; the surrounding skill/workflow catalog text stays intact. -->

<!-- 2026-06-06: Wave 6 — 13 verified-dead tables dropped (migration 101). dropped workflow_agent_skill_mappings was 0-row metadata only; expert workflow system unchanged. No semantic change required. -->

<!-- Last reviewed 2026-06-07 — WO-F prd_* cluster drop (migration 103): migration 103 drops the entire prd_* cluster (prd_documents, prd_plans, prd_tasks, prd_sessions, prd_handoffs, session_tasks, prd_version_records, prd_amendment_records, prd_route_reconciliation_records) and the views vw_prd_progress and vw_task_details. AD-10 decision: business_projects IS what PRD was. All prd_* callers removed from studio_db.py, prd_authority.py (deleted), routes/prd.py (deleted), analytics_ingestion.py, module_contracts.py, dashboard_freshness.py, contract_atlas.py, contract_registry.py, project_intelligence.py, shared_intelligence.py, resume_from_handoff.py, and migrate_prd_schema.py (deleted). -->

<!-- reviewed 2026-06-26: migration 128 dead-tables removal — no content changes required -->

<!-- reviewed 2026-06-27: Wave 1 migration 130 — expert_workflows.py AUTHORITY_WRITE_TARGETS updated: removed artifact_records (dropped migration 130; 0 rows, aspirational telemetry, no production writer). Expert workflow system behavior and overlap matrix unchanged. No semantic change required. -->

<!-- Last reviewed 2026-06-27 — Wave 2 substrate realignment (migration 131, worktree-agent-a910d590fedb5c672): no expert-workflow-system change. expert_workflow_catalog() is static/policy data; migration 131 only removed retired dormant-table references (task_attribution_records, github_repo_* intake) from the surrounding contract-atlas assembly. -->

<!-- Last reviewed 2026-06-28 — Batch 1 canonical-first migration (migration 133): shared_intelligence route source_tables list cleaned of dropped-table references. Expert workflow system (expert_workflow_catalog, ds system, capability routes) unchanged. -->

<!-- Reviewed 2026-07-05 — WO 6d978483 (PEP 585/604 modernization [2/2]): source files in this domain received mechanical type-annotation modernization only (PEP 585 builtin generics, PEP 604 unions, datetime.UTC) via ruff UP safe autofixes. No contract, behavior, schema, routing, API-shape, or CLI-surface change — reviewed, no doc content change needed. -->
