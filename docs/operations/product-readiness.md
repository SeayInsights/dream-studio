# Product Readiness Baseline

This baseline is the repeatable Phase 15 evidence path for the stabilized Dream Studio platform. It proves required contracts, scripts, reports, authority invariants, accepted warnings, and adjacent enterprise posture without adding product features or repairing local runtime state.

## Authority

Product readiness validation is evidence only. It does not own canonical state, repair the native runtime DB, create schema migrations, promote enterprise code, expand Docker, or move authority into dashboards, telemetry, adapters, research, or enterprise analytics.

Docker is optional validation/sandboxing infrastructure, not runtime authority.

The local canonical runtime DB remains private operator state. Product readiness checks should inspect runtime DB metadata only through read-only guards and record the observed schema version in local evidence. Public docs must not hard-code one operator machine's historical schema skew as current product state.

## Windows Evidence Path

Run the narrow static baseline first:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 product-readiness
```

Then run normal validation under the runtime state hash guard:

```powershell
python scripts/runtime_state_hash_guard.py --label phase15_verify -- powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 verify
python scripts/runtime_state_hash_guard.py --label phase15_full_suite -- powershell -ExecutionPolicy Bypass -File scripts/dev.ps1 test
```

The `product-readiness` target runs only:

```powershell
python -m pytest tests/unit/test_product_readiness_baseline.py -q --tb=line
```

It is not a replacement for hash-guarded `verify` or `test`.

## Security Lifecycle Gate

Release readiness must include the security-by-default lifecycle gate. The gate
uses the 47 enterprise security controls as the canonical framework and records
which controls are applicable, not applicable with a reason, manual-review
required, or unknown.

Security lifecycle statuses affect readiness:

- `ready` allows the release gate to continue.
- `needs_manual_review` holds release closure until the applicable manual
  reviews are recorded.
- `unknown_requires_review` holds release closure until unknown controls are
  classified.
- `blocked_by_open_findings` blocks release closure until findings are
  remediated or formally accepted.

The readiness gate must not run scans, inspect secrets, mutate repositories, or
write live SQLite unless a separate approved Work Order explicitly authorizes
that action.

## Secure Production Readiness Gate

Product readiness now includes `secure_production_readiness_gate`. This gate
combines the 47 enterprise security controls with production readiness controls
for API resilience, database readiness, caching correctness, accessibility,
observability, performance, dependency/supply-chain risk, code quality,
privacy/compliance applicability, backup/restore/rollback, and release
readiness.

The gate writes authoritative readiness records only through the
production-readiness workflow and an injected SQLite connection. Project health
and project readiness stay separate:

- project health describes the current condition and active operational risks.
- project readiness describes whether the project has enough evidence to move
  toward real users, release, deployment, publication, enterprise use, or
  broader rollout.

If evidence is insufficient, readiness is `partial` or `unavailable` with
missing evidence and blocking factors. Do not display fake precision.

AI usage accounting contributes operational value signals but not fabricated
cost. Readiness may use run count, validation result, rework, security/readiness
findings, files touched, commands run, and duration. It may use cost only when
the adapter accounting record marks it as exact, provider-reported, explicitly
estimated, or allocated subscription cost with supporting source/evidence refs.
Unknown cost should remain `unknown`, not zero.

Module contract maturity is part of readiness evidence. `core.module_contracts`
declares which modules own authority, which dependencies are optional, what
disabled-module and empty-state behavior should look like, and which validation
tests enforce each boundary. The read-only module-contracts API and Contract
Atlas section can inform readiness, but they do not execute checks or authorize
state mutation.

## Project Portfolio Readiness Surface

All Projects and Project Details are the normal operator surfaces for project
health, PRD status, security posture, production readiness, remediation, and
release blockers. They are derived views over current project authority,
current PRD authority, security/readiness records, validation records,
attention items, evidence refs, and source repos.

Default project lists must include only current legitimate projects. Temp,
pytest, demo, placeholder, inactive/quarantined, adapter scratch/worktree,
missing-path, and legacy fallback records stay out of normal operator views and
are retained only as manual-review or retention-only records when they cannot
be safely removed.

Project health and project readiness remain separate. Health describes current
condition and operational risk; readiness describes whether evidence supports
real users, release, deployment, publication, enterprise use, or broader
rollout. If evidence is insufficient, the dashboard and API must show
unavailable or partial status with missing evidence, blockers, and source refs.
They must not show fake precision.

Project Details is the operating view for production-readiness context. It
shows safe stack evidence, confirmed dependency graph status, inferred or
unverified dependencies hidden by default, module/runtime profile fit, security
findings, 47-control status, readiness controls, validations, attention items,
known gaps, evidence refs, and the current next action. It is a derived view and
must not mutate external projects, inspect secrets, run Docker, or write SQLite.

PRD status is part of project authority. Existing safe PRD files can be read
and summarized. Missing or stale PRD evidence becomes `draft_generated`,
`needs_update`, `stale_superseded`, or `manual_review_required` status; no
unsupported product claims should be invented.

Analytics-only deployments may import product-readiness facts from normalized
payloads. Imported readiness records can feed Project Details, release
readiness summaries, and Contract Atlas maturity only when source/evidence refs
are present. Missing imported sections remain honest empty states. The profile
must not require hooks, agents, workflows, Claude, Codex, Docker, repo mutation,
or full orchestration to display current analytics.

## Optional Adjacent Enterprise Spot-Check

Enterprise remains adjacent and excluded from main normal validation. If a separately approved adjacent enterprise repo is present, use it only as separate evidence with that repo's explicit path:

```powershell
git -C "<adjacent-enterprise-repo>" status --short --branch
python -m pytest tests/ -q --tb=line
rg -n "~/.dream-studio|studio\.db" api ml org_intelligence tests README.md pyproject.toml
rg -n "from projections|import projections|from core|import core|sys\.path\.insert" api ml org_intelligence tests generate_org_intelligence.py
rg -n 'dream-studio:|"ds:' tests api ml org_intelligence README.md
```

Enterprise aggregate/redacted input package schema remains a known readiness risk. It is not implemented by this baseline and must not be treated as a main runtime dependency.

## Authority Checks

Run these checks as part of Phase 15 evidence:

```powershell
rg -n "name:\s*dream-studio:\s*" skills
rg -n "dream-studio:\s*" control core interfaces projections skills docs/contracts tests/unit
rg -n '"ds:' control tests projections core interfaces
rg -n "name:\s*ds-" skills
Test-Path hooks\lib
Test-Path runtime\hooks
Test-Path core\event_store\migrations\034_execution_graph.sql
git diff --name-only 1efa3d6..HEAD | Select-String -Pattern 'docker-compose|compose\.ya?ml|Dockerfile|\.dockerignore'
git diff --name-only 1efa3d6..HEAD | Select-String -Pattern 'core/event_store/migrations/0[3-9][0-9]_'
```

Expected:

- no forbidden skill identifier matches;
- `hooks/lib` is absent;
- `runtime/hooks` exists;
- migration `034_execution_graph.sql` exists;
- no Docker or compose expansion;
- no schema migration expansion.

## Accepted Warning Baseline

The following warnings are accepted for Phase 15 readiness evidence unless their text, source, or count changes materially:

- missing temp session root warning from `tests/integration/test_session_analytics.py`;
- `RequestsDependencyWarning` in the web research test environment;
- coverage warning for absent retired `hooks/lib`;
- enterprise `statsmodels` fallback warning;
- enterprise missing `DREAMSTUDIO_ENTERPRISE_KEY` license-key warning.

These warnings are not hidden. They are documented so new warnings stand out.

## Required Evidence Artifacts

The baseline requires contract docs for event, state, projection, adapter, governance, skill, workflow, hook, agent, portable execution, research source, and enterprise aggregation.

It also requires operation docs for local runtime, Windows dev commands, Docker clean-room validation, this product-readiness baseline, the code-history impact guardrail, and the lint/format baseline policy.

Code changes must also follow the code-history and impact guardrail in `docs/operations/code-history-impact-guardrail.md`. Release validation must follow the lint/format baseline policy in `docs/operations/lint-format-baseline-policy.md`.

The Phase 15 evidence trail should cite the Phase 8 through Phase 14A reports and include fresh command output for the focused baseline test, hash-guarded verify, hash-guarded full suite, enterprise spot-check, and authority checks.

## Stop Conditions

Stop Phase 15 readiness validation if:

- normal validation mutates native runtime DB/backups;
- `hooks/lib` is recreated;
- skill identifiers drift;
- enterprise is promoted into main runtime or normal validation;
- Docker becomes canonical authority;
- schema migrations are added without explicit scope;
- cloud/org/global sync appears;
- dashboards, telemetry, adapters, research, or enterprise analytics become canonical authority.
