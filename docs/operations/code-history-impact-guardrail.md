# Code History And Impact Guardrail

Status: active operational policy

Dream Studio must understand local code history and broader correctness impact before and after code-related changes. This guardrail applies to source edits, cleanup, formatting, refactors, tests, release-gate changes, route/API work, dashboard changes, telemetry changes, hooks, skills, workflows, adapters, and generated projection changes.

## Before Code Mutation

Before changing product code, Dream Studio should inspect enough relevant context to preserve the existing design:

- recent git history for files that will be touched;
- module purpose, ownership, and active architecture boundaries;
- current tests, validation commands, and release-gate expectations;
- related routes, APIs, read models, migrations, telemetry, dashboard surfaces, hooks, skills, workflows, adapters, and config projections;
- prior decisions, evidence, or Work Order constraints when available;
- file classification: product source, generated artifact, test fixture, local state, external target, private evidence, or ignored runtime output.

This inspection should be scoped. Dream Studio should read what is needed to make a safe change, not sweep unrelated areas for curiosity.

## After Code Mutation

After cleanup, formatting, refactor, source mutation, or code-related change, Dream Studio must evaluate broader impact:

- imports still resolve;
- public APIs and routes still return expected status and response shapes;
- read models still return expected derived-view metadata and structures;
- dashboard/frontend contracts still hold;
- SQLite path resolution, temp DB use, and live-state boundaries still hold;
- tests that write state use temp or injected DB paths;
- no live DB or installed local state was unintentionally touched;
- no external project scope was crossed;
- no behavior changed in a supposedly mechanical cleanup;
- focused validations and the release gate still pass or any remaining baseline debt is explicitly classified.

## Mechanical Cleanup Rule

Mechanical formatting commits must not include semantic refactors. If formatting reveals a real correctness issue, fix it in a separate follow-up commit with its own validation.

## Release Gate Interaction

The release gate treats formatting debt differently from lint debt:

- Black formatting must pass after the repo-wide formatting cleanup.
- Flake8 findings that already exist in the committed baseline remain tracked debt.
- New flake8 findings outside the baseline block release.
- True correctness, security, runtime-boundary, DB-boundary, route-contract, dashboard-contract, or release-policy issues block release even if a lint baseline exists.

## Stop Conditions

Stop and require operator approval when the safe fix would require broad semantic refactoring, live DB mutation, live installed-state mutation, external project mutation, package/dependency changes, Docker start/build, push, tag, merge, deploy, secret access, or history rewrite.
