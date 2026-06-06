# GitHub Repo Intake And Integration Evaluation

Dream Studio must evaluate a GitHub repository before adopting code, prompts,
dependencies, skills, workflows, hooks, adapters, docs, architecture ideas, or
implementation ideas from it.

The default preference order is:

1. learn the pattern or concept;
2. write an original Dream Studio implementation;
3. use a dependency only after license, security, and maintenance review;
4. fork or vendor only with explicit approval;
5. copy code only with license, attribution, legal, and operator approval.

## Workflow

The `github_repo_intake_and_integration_evaluation_workflow` includes:

- repo metadata review;
- license and attribution review;
- security and supply-chain review;
- dependency health review;
- architecture pattern review;
- code quality and integration-fit review;
- duplication/overlap review against existing Dream Studio modules, skills,
  workflows, and adapters;
- extraction strategy review;
- implementation Work Order generation only after the decision is evidence-backed.

Outcome classes are `reject`, `reference_only`, `learn_pattern_only`,
`create_design_note`, `create_skill_candidate`, `create_workflow_candidate`,
`create_adapter_candidate`, `create_dependency_candidate`,
`fork_or_vendor_candidate`, `manual_review_required`,
`legal_review_required`, `security_review_required`, and
`integration_work_order_ready`.

Unclear licensing routes to `legal_review_required`. Unclear security or
supply-chain posture routes to `security_review_required`. Overlap with
existing Dream Studio capabilities routes to manual overlap review before new
skills, workflows, or adapters are created.

## Authority And Dashboard

Migration 044 adds SQLite authority tables for repo evaluations, license
findings, security findings, dependency findings, integration candidates,
pattern references, adoption decisions, and attribution records.

The dashboard route `/api/shared-intelligence/github-repo-intake` exposes the
workflow and recorded evaluation summaries. It does not fetch remote repos,
copy code, add dependencies, fork, vendor, mutate external projects, or approve
adoption by itself.

The installed dashboard command can make this derived route visible when the
dashboard module is enabled. `ds dashboard --serve`, `--open`, and `--check`
only start or validate the local dashboard/API surface; they do not inspect
GitHub repositories or promote intake decisions.

GitHub repo evaluation evidence is private by default until explicitly
sanitized for publication.

If a GitHub repo evaluation later becomes implementation work, the resulting
task should be linked through task attribution rather than hidden in the intake
record. Attribution can reference the Work Order, adapter, skills/workflows,
files, validations, outcome, and evidence refs while preserving the intake
decision as private evaluation authority.
## Platform Hardening Refresh

GitHub repo intake can feed the connector ingestion framework and policy engine, but adoption remains gated: reference-only, pattern-only, dependency candidate, fork/vendor candidate, legal review, security review, and manual review decisions must be evidence-backed before Dream Studio uses external code, dependencies, workflows, prompts, or architecture patterns.

## PRD Lifecycle Boundary

GitHub repo intake can inform PRD formalization when a repository is explicitly
selected and approved for read-only intake. It must not mutate the external
repo, copy PRD files into that repo, or adopt code/dependencies. Any adoption
path becomes a Project Change Order or Work Order with license, security,
overlap, and attribution evidence.

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-05: Phase 18.6.2 reviewed — module_contracts.py removed project_health_scorecards and project_readiness_scorecards from analytics_only read_dependencies (tables dropped in migration 099). No semantic change to this document required. -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. No career content in this doc (github_repo_intake module is unaffected); no semantic change required. -->

<!-- 2026-06-06: Wave 6 — 13 verified-dead tables dropped (migration 101). github_repo_* intake tables NOT dropped; only the adjacent shared-intelligence source_tables metadata changed. No semantic change required. -->

<!-- reviewed: 2026-06-06, WO-C orphan rot sweep. core/module_contracts.py: removed dead test file reference from github_repo_intake module's validation_tests list. github_repo_intake module itself unchanged. No intake evaluation contract change. No semantic change required. -->
