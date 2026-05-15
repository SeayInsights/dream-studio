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
