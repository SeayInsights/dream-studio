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

This gate is deliberately targeted. It should update impacted docs, not rewrite
every README, PRD, workflow doc, operator doc, or publication boundary by
default. The PRD changes only when product authority changes.

## Baseline Regeneration

Regenerate the baseline only after evidence shows the current findings are inherited debt, not new regressions:

```powershell
python interfaces/cli/lint_baseline.py write-baseline
```

Baseline updates should be reviewed like product changes. They must not hide real correctness failures.

## Future Cleanup

Remaining flake8 debt should be paid down in focused follow-up work. Removing or reducing baseline entries is encouraged when safe. Broad semantic lint cleanup remains a separate approval boundary.
