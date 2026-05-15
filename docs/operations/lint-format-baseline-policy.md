# Lint And Format Baseline Policy

Status: active release-gate policy

Dream Studio uses formatting and linting as release signals without confusing historical style debt with new release regressions.

## Formatting

Black is the formatter of record for Python code. After the repo-wide cleanup, `python -m black --check .` is blocking in the release gate.

Formatting changes must be mechanical. They should be committed separately from semantic fixes.

## Lint Baseline

Flake8 remains a correctness and style signal, but existing repo-wide debt is tracked in:

```text
runtime/config/release-gates/flake8-baseline.txt
```

The baseline stores normalized flake8 findings for known historical debt. The gate compares current findings against that baseline by file, rule code, and message so line-number movement from formatting does not automatically create false positives.

## Blocking Rules

The release gate blocks:

- new flake8 findings that are not in the committed baseline;
- increased counts for a baseline finding identity;
- Black formatting drift;
- Contract Atlas documentation drift when meaningful source, schema, dashboard, workflow, hook, adapter, or release-gate changes do not refresh the required impacted contracts/docs;
- Contract Atlas lifecycle drift when private refresh, sanitized public export,
  maturity ledger, docs/PRD/README impact detection, dashboard/API freshness,
  or public-export leakage checks fail;
- failing tests;
- dependency audit failures;
- correctness, security, route, dashboard, SQLite, live-state, or release-policy failures.

The release gate does not block:

- unchanged flake8 findings already recorded in the baseline;
- resolved baseline findings, which are reported as debt reduction;
- historical lint debt that has not worsened.
- unrelated docs that are not impacted by the current change set.
- adapter scratch/worktree/session folders such as `.claude`, `.codex`,
  `.adapter-scratch`, and `.ai-scratch`, which are runtime artifacts and not
  product source.
- unavailable or disabled GitHub Actions for ordinary development, provided
  the remote-confidence gap is recorded and local release-gate evidence remains
  available before merge/release approval.

## Contract And Docs Drift Gate

The Contract Atlas drift gate is:

```text
python interfaces/cli/contract_docs_drift_gate.py
```

The Contract Atlas lifecycle gate is:

```text
python interfaces/cli/contract_atlas_lifecycle_gate.py
```

The gate reads `core/shared_intelligence/contract_registry.py`, maps changed
files to contract domains, and fails when required docs for an impacted domain
are not refreshed in the same change set. CI can provide changed files through
`DREAM_STUDIO_CHANGED_FILES`, `--changed-file`, or a base ref. Local runs with
no pending diff pass as an honest empty state.

If a domain is reviewed and no docs need to change, the gate can record that
explicitly with `--docs-reviewed-no-change <domain_id>`. That path is for
evidence-backed review decisions, not a shortcut around stale documentation.

Contract Atlas behavior changes must refresh the atlas contract doc, this
operations policy, and the docs index together so the release gate, human docs
surface, lifecycle manifest, sanitized export boundary, and derived atlas view
describe the same freshness boundary.

Installed runtime and productization changes are release-gate relevant. If code
changes affect `core/installed_runtime.py`, `core/installed_productization.py`,
module profile selection, repo-owned launchers such as `ds.cmd` or `ds.ps1`,
`ds install-command`, or the global `ds` command surface, the same change set
must refresh installed runtime/productization docs,
troubleshooting docs, adapter-boundary docs, and independent configuration docs
required by the drift report.

Analytics-only ingestion changes are release-gate relevant. If code changes
affect `core.analytics_ingestion`, `ds analytics-ingest`, analytics-only module
profile declarations, shared-intelligence analytics-only routes, or the
dashboard/API surfaces that consume imported analytics records, the same change
set must refresh Contract Atlas, dashboard mapping, installed runtime,
productization, troubleshooting, and independent configuration docs required by
the drift report. Tests should prove dry-run behavior, explicit write
authorization, idempotent current-authority imports, and honest empty states.

Module contract changes are release-gate relevant. If code changes affect
`core.module_contracts`, installed profile declarations, module/profile
Contract Atlas sections, or module dependency boundaries, the same change set
must refresh Contract Atlas, installed runtime/productization docs,
troubleshooting, and independent configuration docs. Tests should prove
required module contracts exist, optional dependencies remain optional,
token-only cost honesty is preserved, and standalone modules do not import
unrelated hook/agent/workflow/Docker surfaces.

Security lifecycle changes are release-gate relevant. If code changes affect
`core/security`, security review contracts, project health security hydration,
shared-intelligence security routes, or release readiness security status, the
same change set must refresh the lifecycle contract and product-readiness docs.

Secure production readiness changes are release-gate relevant too. If code,
SQLite migrations, shared-intelligence routes, project detail views, release
readiness, workflow templates, or Contract Atlas sections affect production
readiness controls or scorecards, the same change set must refresh the
production readiness contract, dashboard mapping, product-readiness operations
doc, and any schema/workflow docs required by the drift report.

Expert workflow changes are release-gate relevant. If code changes affect
`core.shared_intelligence.expert_workflows`, shared-intelligence expert
workflow routes, skill/workflow overlap decisions, scoring rubrics, or
career/application automation boundaries, the same change set must refresh the
expert workflow operations doc, Contract Atlas doc, docs index, and any
dashboard/readiness docs required by the drift report. Tests should prove the
overlap matrix exists, existing skills are mapped instead of duplicated,
scoring remains evidence-backed, and private career automation boundaries are
preserved.

Task attribution changes are release-gate relevant. If code changes affect
`task_attribution_records`, `core.shared_intelligence.task_attribution`,
adapter usage outcome rollups, Project Details recent work, Work Order
attribution drilldowns, or Capability Center outcome counts, the same change
set must refresh database/migration docs, Contract Atlas, dashboard mapping,
and the task attribution operations doc. Tests should prove unknown
model/provider values remain explicit, unavailable files/commands are not
invented, outcomes and rework are visible, and no fake token or cost precision
is introduced.

This gate is deliberately targeted. It should update impacted docs, not rewrite
every README, PRD, workflow doc, operator doc, or publication boundary by
default. The PRD changes only when product authority changes.

## GitHub Actions Cost Boundary

GitHub Actions should stay lightweight by default:

- `.github/workflows/ci.yml` runs PR smoke only.
- `.github/workflows/full-ci.yml` runs `ci_gate.py` manually with
  `workflow_dispatch`.
- `.github/workflows/release-validation.yml` runs release evidence manually or
  on explicit release tags.
- local `ci_gate.py` remains the heavy release gate.

Do not add full matrix runs to every push unless a future operator-approved
budget and release policy change explicitly makes that cost acceptable.

## Baseline Regeneration

Regenerate the baseline only after evidence shows the current findings are inherited debt, not new regressions:

```powershell
python interfaces/cli/lint_baseline.py write-baseline
```

Baseline updates should be reviewed like product changes. They must not hide real correctness failures.

Adapter scratch exclusions must stay narrow. They may keep local Claude/Codex
worktrees, sessions, and temporary runtime files out of the lint gate, but they
must not exclude active source directories, tests, public docs, templates, or
generated adapter projections that are intentionally tracked.

AI usage accounting changes are release-gate relevant. If code changes affect
token/model cost display, adapter billing modes, telemetry collectors, or
dashboard token analytics, the same change set must keep formatter output clean,
avoid new lint findings, and refresh the database, dashboard, Contract Atlas,
installed runtime, and readiness docs required by the drift report. Regression
tests should block hard-coded token-to-dollar pricing from returning to live
operator surfaces.

Repo publication readiness changes are release-gate relevant. If code changes
affect publication checks, privacy scans, sanitized export behavior, Git history
path classification, README/PRD alignment, or Apache-2.0 references, the same
change set must run `python interfaces\cli\repo_publication_readiness.py
--strict`, refresh the public publication evidence when intentional, and keep
private operational history out of tracked source.

External-project, Docker-boundary, long-run validation, and final
productization closeout changes are release-gate relevant. If code changes
affect paused external target intake, target selection gates, Docker profile
contracts, multisession dogfood evidence, live SQLite hash guards, or final
installed-platform closeout routing, the same change set must refresh Contract
Atlas, installed productization docs, Docker/external-project docs, and the
docs index. Tests should prove that external projects remain paused unless
selected, Docker stays optional, live SQLite guards stay intact, and closeout
routes to an explicit operator decision before public release.

Career Ops, Capability Center, scoped-agent, and GitHub repo intake changes are
release-gate relevant. If code changes affect private career authority,
capability/evaluation read models, agent context scoping, or external GitHub
repo adoption policy, the same change set must refresh database docs, Contract
Atlas docs, dashboard mapping, publication boundary docs, and the docs index.
Tests should prove private career data is excluded from public exports, agents
do not receive forbidden context by default, and repo intake does not copy code
or add dependencies without approval.

## Future Cleanup

Remaining flake8 debt should be paid down in focused follow-up work. Removing or reducing baseline entries is encouraged when safe. Broad semantic lint cleanup remains a separate approval boundary.
## Platform Hardening Refresh

The platform-hardening sequence adds a skill/workflow evaluation harness and installer/distribution checks, but it does not relax the lint or format baseline. `ds platform-hardening` and the Contract Atlas freshness views are derived status surfaces; Black, lint baseline checks, docs drift, and the release gate remain the release-blocking authorities for source changes.
