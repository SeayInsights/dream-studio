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

## Contract And Docs Drift Gate

The Contract Atlas drift gate is:

```text
python interfaces/cli/contract_docs_drift_gate.py
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
surface, and derived atlas view describe the same freshness boundary.

Installed runtime and productization changes are release-gate relevant. If code
changes affect `core/installed_runtime.py`, `core/installed_productization.py`,
module profile selection, `ds.ps1`, or the global `ds` command surface, the
same change set must refresh installed runtime/productization docs,
troubleshooting docs, adapter-boundary docs, and independent configuration docs
required by the drift report.

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

This gate is deliberately targeted. It should update impacted docs, not rewrite
every README, PRD, workflow doc, operator doc, or publication boundary by
default. The PRD changes only when product authority changes.

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

## Future Cleanup

Remaining flake8 debt should be paid down in focused follow-up work. Removing or reducing baseline entries is encouraged when safe. Broad semantic lint cleanup remains a separate approval boundary.
