# Expert Workflow Systems

Lifecycle status: foundation_active

Dream Studio expert workflows formalize how existing skills, workflows,
readiness gates, dashboard views, and Contract Atlas signals cooperate. The
catalog is repo-backed and deterministic. It does not create a competing skill
database, execute work, write SQLite by itself, or replace existing career,
debugging, design, quality, documentation, or fullstack skills.

## Authority Boundary

Current implementation:

- `core/shared_intelligence/expert_workflows.py` declares the expert workflow
  catalog, overlap matrix, scoring rubrics, career privacy boundaries, and
  application automation rules.
- `/api/shared-intelligence/expert-workflows` exposes the catalog as a derived
  dashboard-consumable view.
- Contract Atlas exposes an `expert_workflow_system` summary, maturity
  scorecard row, and confirmed dependency edges to the existing skill/workflow
  owners.
- Workflow outputs should persist through existing authority tables such as
  `workflow_invocations`, `skill_invocations`, `decision_records`,
  `research_evidence_records`, `validation_results`, `artifact_records`,
  `dashboard_attention_items`, and Work Order records when an executing runtime
  is explicitly authorized to write.

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
| `career_strategy_and_portfolio_ops_workflow` | `career:ops` | `strengthen_existing` |

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

## Career And Portfolio Boundary

The career workflow preserves existing career functionality:

- interactive resume/profile questions;
- private local profile storage;
- tailored resumes;
- tailored cover letters;
- LinkedIn/profile positioning;
- job-description tailoring;
- Playwright field filling when configured;
- reusable application field profiles;
- job/application tracking;
- no account creation;
- operator approval before submission.

Career claims must be evidence-backed. Missing claims are marked
`needs_evidence`, `estimate_candidate`, or `operator_confirmation_required`.
Dream Studio must not invent titles, metrics, compensation, employer details,
deployment outcomes, business impact, or adoption claims.

Application automation boundaries:

- do not create accounts;
- do not bypass CAPTCHAs;
- do not misrepresent the operator;
- do not submit applications without explicit approval or an approved
  per-application submission policy;
- pause on ambiguous questions;
- store sensitive personal fields only in approved private storage;
- do not print secrets or private identifiers unnecessarily;
- record what was filled, skipped, and needs operator input.

Career data, compensation strategy, application materials, browser traces, and
private portfolio notes are private by default. Public case studies, resumes,
portfolio pages, or social content require sanitization and operator approval.

## Capability Center Integration

Expert workflow definitions feed Capability Center as workflow capability
records. Capability Center can show invocation counts, scorecard availability,
validation requirements, hardening candidates, and task-attributed outcomes,
but it does not create a parallel workflow system or authorize execution.
Missing invocation/evaluation or attribution evidence stays `unavailable`
instead of becoming a fake success rate.

Career-related expert workflows map into the optional private Career Ops
module. Career data remains local/private authority and is excluded from public
exports by default.

## Validation

The expert workflow system is validated by:

- `tests/unit/test_expert_workflow_catalog.py`;
- Contract Atlas validation;
- Contract Atlas docs drift gate;
- release gate checks.

The validation proves the overlap matrix exists, existing owners are mapped
instead of duplicated, scoring rubrics require evidence, design specializations
are declared, career automation behavior is preserved, and application
automation boundaries are explicit.
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
