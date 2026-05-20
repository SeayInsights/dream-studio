# Installed Platform Productization

Dream Studio is productized as a local installed platform: users select the
modules they need, keep source/build files separate from user-local state, and
interact through the global `ds` command surface instead of manually working
inside the source checkout.

## Install Model

| Area | Purpose |
| --- | --- |
| Source root | Installed Dream Studio source/build files and product code. |
| Dream Studio home | User-local runtime state, normally `~/.dream-studio`. |
| SQLite authority | `state/studio.db` inside the selected Dream Studio home. |
| Runtime config | `config/runtime.json` inside the selected Dream Studio home. |
| Adapter runtime | User-local adapter/router state under `adapters/` and `router/`. |
| Context packets | Fallback packets under `context-packets/` for unsupported tools. |
| Evidence and backups | Private local files under `meta/` and `backups/`. |

The installer and acceptance commands take `--source-root` and `--home` so
rehearsal installs, CI gates, and adapter launchers do not depend on the
current working directory.

## First-Run Setup

From any directory:

```powershell
python C:\path\to\dream-studio\interfaces\cli\ds.py `
  --source-root C:\path\to\dream-studio `
  --home C:\Users\Example\.dream-studio `
  install --profile analytics_only
```

For rehearsal validation, include `--rehearsal` and point `--home` at a
temporary directory. Rehearsal setup creates fresh state, bootstraps SQLite,
writes runtime config, creates adapter/router/context-packet directories,
registers default adapter authority profiles, and previews context-packet
fallback without mutating the live installed state.

## Module Profiles

Supported installed profiles:

- `core`
- `analytics_only`
- `security_only`
- `token_only`
- `telemetry_only`
- `dashboard_only`
- `adapter_router_only`
- `shared_intelligence_only`
- `full`

Unselected modules are disabled cleanly and should report honest empty states.
`analytics_only` works without hooks, agents, workflows, Claude, Codex, repo
mutation, or Docker. `security_only` works independently of Claude, Codex, and
Docker. `token_only` reports usage telemetry without converting plan-based or
unknown token visibility into fabricated cost. `full` enables the complete local
surface but still respects adapter and live-state guardrails.

Major module contracts live in `core.module_contracts`. They are independent of
the installed profile list and declare the operational boundary for `core`,
`telemetry`, `dashboard`, `security_only`, `token_only`, `analytics_only`,
`shared_intelligence`, `adapter_router`, `adapter_projection`,
`external_project`, `docker_optional`, and `full`. These contracts define owned
tables/authority, dependencies, events, routes, dashboard surfaces, commands,
disabled-module behavior, empty states, profile membership, readiness impact,
Contract Atlas maturity, and validation tests.

## Global Commands

The productized command surface includes:

```text
ds status
ds version
ds doctor
ds repair
ds install
ds install-command
ds dashboard
ds dashboard --status
ds dashboard --serve
ds dashboard --open
ds dashboard --check
ds validate
ds contract-atlas
ds contract-atlas-refresh
ds adapters
ds context-packet
ds modules
ds router
ds analytics-ingest
ds policy
ds platform-hardening
ds acceptance
ds backup
ds restore-check
ds update-check
ds migrate-legacy
ds repair-adapters
ds rollback-check
ds uninstall-check
```

On Windows, `ds.cmd` and `ds.ps1` are repo-owned launchers that can be placed
on PATH or invoked directly from any directory. `ds.cmd` supports the plain
`ds` command in normal `cmd.exe` and PowerShell shells without requiring
PowerShell script execution policy changes. Both launchers delegate to the
canonical Python CLI with an explicit source root:

```powershell
C:\path\to\dream-studio\ds.cmd --home C:\temp\dream-studio status
```

Installed Windows users can create user-local launchers in a PATH directory:

```powershell
python C:\path\to\dream-studio\interfaces\cli\ds.py `
  --source-root C:\path\to\dream-studio `
  --home C:\Users\Example\.dream-studio `
  install-command --execute
```

The same commands are available through `python interfaces\cli\ds.py` for
portable scripting and tests.

Distribution hardening commands are read-only or plan-only by default.
`ds doctor` reports runtime health, `ds repair` returns a repair plan without
writing state, `ds policy` previews permission decisions, and
`ds platform-hardening` reports the product-hardening sequence from SQLite
authority and repo declarations.

## Expert Workflow Surface

Installed Dream Studio exposes `/api/shared-intelligence/expert-workflows` as a
read-only catalog for expert workflow contracts. This lets dashboard, adapter,
and context-packet consumers discover intentional implementation, code quality,
debugging, performance, design, SEO/content, documentation, data modeling, API,
case-study, and career/portfolio workflow expectations without executing a
skill or relying on the current working directory.

The surface is not a career automation runner and does not publish private
career data. Career/application operations still require the existing career
skill modes, configured private storage, Playwright boundaries when used, and
operator approval before any submission.

## Analytics-Only Ingestion

`analytics_only` can be installed as a standalone analytics deployment profile.
It does not require hooks, agents, workflows, Claude, Codex, Docker, repo
mutation, or full orchestration.

External systems, CI jobs, security scanners, adapter wrappers, or manual
exports can produce normalized JSON payloads. Dream Studio imports them through
`ds analytics-ingest`. The command plans by default and writes only when
`--execute` is supplied:

```powershell
ds analytics-ingest --file C:\path\to\analytics-payload.json
ds analytics-ingest --file C:\path\to\analytics-payload.json --execute
```

Supported normalized sections include projects, validations/CI, security
findings, token usage, AI operational usage, components, dependencies, PRDs,
and readiness assessments. Imported records go into current SQLite authority
tables and are consumed by existing dashboard/API read models. Missing sections
remain honest empty states.

## Adapter Setup

Supported AI tools should connect through Dream Studio adapter/router surfaces
where possible:

- CLI and app surfaces with a configured source/home use `ds adapters`,
  `ds router`, and shared-intelligence API routes.
- MCP-capable clients can use the router contract when configured.
- Unsupported plain web/chat tools use context-packet fallback.
- Unproven cloud or app environments must remain classified as unproven until
  evidence proves live consumption.

Adapter setup never treats private model memory as authority.

## Dashboard Onboarding

`ds dashboard` defaults to safe status-only behavior. It reports dashboard
readiness, the selected source/state paths, the derived API routes, and the
exact commands for starting or checking the local server. It does not start a
server by itself.

Dashboard command modes:

```powershell
ds dashboard --status   # readiness only; same as ds dashboard
ds dashboard --serve    # start the local FastAPI dashboard server
ds dashboard --open     # start or reuse the server and open a browser
ds dashboard --check    # validate /dashboard and /api/health on a running server
```

`--serve` starts `projections.api.main:app` through uvicorn using resolved
Dream Studio source/home/SQLite environment variables. It does not bootstrap,
migrate, backfill, or clean runtime state. Use `ds install`, `ds validate`, or
approved migration flows for state setup.

Dashboard-enabled profiles show derived empty states when no runtime facts
exist. Disabled profiles report that dashboard routes are disabled by the
selected module profile.

## Backup, Restore, Update, And Uninstall

`ds backup` plans a backup by default. `ds backup --execute` creates a
non-destructive backup in the selected Dream Studio home or explicit
`--backup-dir`.

`ds restore-check` validates a backup but does not restore it.

`ds update-check` compares installed SQLite state with the current migration
level without mutating the database. It also reports legacy-install detection
metadata so users who previously installed an old checkout do not accidentally
treat that checkout as a normal pull/update path.

`ds install --check-legacy` detects old source checkouts, old runtime state,
old SQLite schema versions, legacy file-sprawl folders, stale user-local
launchers, Dream-Studio-owned Claude/Codex adapter config paths, stale
environment variables, and unknown/manual-review install states. It is
read-only and does not print secret values.

`ds migrate-legacy --dry-run` creates the upgrade plan. `ds migrate-legacy
--execute` is the guarded execution path: it creates a full backup of the
existing Dream Studio home, writes rollback instructions, creates a fresh active
home, applies current migrations, migrates compatible SQLite authority rows
into current tables, refreshes launchers to the clean source checkout, and
repairs only Dream-Studio-owned adapter hook paths. It does not merge unrelated
Git histories, inspect secrets, copy old Work Order/handoff/report/evidence
file sprawl into active state, delete old source checkouts, or delete backups.

`ds repair-adapters` repairs user-local `ds` launchers and Dream-Studio-owned
adapter hook paths. It plans by default and writes only with `--execute`.

`ds rollback-check` validates that a legacy-upgrade backup exists, contains a
readable SQLite backup, and includes rollback instructions. It does not restore
or delete anything.

`ds uninstall-check` inventories local files without deleting anything.

Live restore, update, or uninstall execution requires a separate
operator-approved scope.

## External Project Pipeline

External projects are supported through a paused-by-default validation pipeline.
DreamySuite, Bill Stack, TORII, and future targets can be represented in the
external target registry, but no target is read, scanned, mutated, validated,
committed, pushed, or deployed unless the current operator decision explicitly
selects that target and scope.

The pipeline can generate a derived dashboard card, read-only intake plan,
dirty-state classification requirement, validation profile, Work Order sequence,
commit policy, push/deploy hold, and private-artifact exclusion policy. Private
planning artifacts, Work Orders, handoffs, local evidence, backup dumps, SQLite
databases, generated runtime state, and secrets stay out of target repos unless
a later sanitized publication policy approves them.

## Docker Boundary

Docker is an optional runtime boundary, not core Dream Studio authority. The
`docker_optional` module and Docker profile contracts describe scanner,
validation sandbox, adapter worker, ingestion worker, and dashboard/API
possibilities, but static validation does not start containers or build images.
Analytics-only, security-only, dashboard-only, shared-intelligence-only,
adapter-router-only, and full local operation all continue to work without
Docker.

## Acceptance Tests

Fresh-environment acceptance is exercised by:

```powershell
python interfaces\cli\ds.py `
  --source-root C:\path\to\dream-studio `
  --home C:\temp\dream-studio-productization `
  acceptance --profile analytics_only --profile security_only --profile full
```

The acceptance report validates fresh state creation, selected/unselected
profile behavior, dashboard status, adapter status, analytics-only independence,
security-only independence, full profile availability, backup/restore/update
checks, and uninstall dry-run behavior.

Final productization closeout additionally aggregates long-run multisession
validation, the live SQLite hash guard, release gate evidence, command-surface
checks, adapter status documentation, Contract Atlas/docs freshness, sanitized
public export freshness, and publication boundary checks. Passing closeout
routes to `operator_decision_on_public_release_private_dogfood_or_external_project_use`.

## Usage Accounting Setup

First-run setup registers default non-secret adapter accounting profiles for
Claude Code subscription, Claude API token-metered, Codex via ChatGPT plan,
Codex token-metered/flexible, ChatGPT plan, Cursor plan, Copilot subscription,
MCP, local model runtime, and shell tools. Users can later replace or extend
these declarations through approved SQLite-backed configuration, but setup must
not inspect provider billing credentials.

Installed analytics and dashboard profiles use these declarations to show
tokens, usage outcomes, and operational value honestly. Cost stays `unknown`
unless provider metadata, provider export, billing API evidence, or explicit
operator allocation metadata makes it reportable.

Installed dashboard and adapter usage views also read task attribution records
when available. Those records explain which adapter did meaningful work, which
skills/workflows were used, what files and commands were recorded, what
validation ran, what outcome occurred, whether rework was needed, and what
security/readiness impact resulted. Missing model/provider, token, cost, file,
or command detail remains explicit rather than inferred.

## Private Capability Modules

Productized installs may include `career_ops_only` as an opt-in private module.
It stores career and application records in local SQLite authority only after
explicit enablement and excludes them from public exports by default.

Shared-intelligence and full profiles expose Capability Center, scoped-agent
registry/context previews, and GitHub repo intake summaries. These are
read-only platform surfaces unless a separate approved command records
authority. They do not execute agents, publish private career data, mutate
external repositories, or approve third-party code/dependency adoption.

Installed shared-intelligence profiles also expose PRD lifecycle context.
Project intake, current PRD version, milestones, Work Orders, change orders,
and route reconciliation remain SQLite authority; productized installs surface
them through Project Details and context packets without requiring users to open
the source repo.

<!-- Last reviewed 2026-05-20 — repo-wide `py -m black .` formatting applied; no behavior or policy change required here. -->

<!-- Last reviewed 2026-05-20 — pipeline optimization landed (migration 057 extends ds_work_order_types with workflow_template, precondition_skill, task_generator, resolution_instructions; CLI gains `ds project state` single-query, auto-advance, gotcha injection, brief mode); doc policy unchanged here. -->

<!-- Last reviewed 2026-05-20 — A1 extraction: 22 CLI handlers refactored into importable functions under core/projects, core/work_orders, core/design_briefs, core/milestones, core/skills, core/health. ds.py wrappers are now thin (call function, print result, return exit code). No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-20 — A2.1: `_work_order_start` decomposed into `read_work_order_brief`, `write_work_order_context`, `start_work_order` under `core/work_orders/start.py`. Stdin y/N prompt removed from the pure path; CLI wrapper preserves the legacy stderr warning + non-TTY auto-accept for operator terminals. No policy or contract change here. -->

<!-- Last reviewed 2026-05-20 — A2.2: `_work_order_close` decomposed into `run_gate_check`, `check_close_gates`, `close_work_order` under `core/work_orders/close.py`. `_run_gate_check` lifted out of `interfaces/cli/ds.py`; `core/projects/queries.py` now imports the predicate directly. CLI wrapper re-emits `[gate.bypassed] WARNING:` to stderr from the returned `bypassed_gates` list for operator-terminal parity. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.3: `_project_start` decomposed into the `start_project` composer under `core/projects/start.py`, which orchestrates `set_active_project` (mutations) + `get_next_work_order` (queries) + `start_work_order` (work_orders/start). CLI wrapper converts the compound result dict into the legacy operator-facing summary; no policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.4: `_skill_invoke` (heaviest CLI handler) decomposed into `load_skill_content` + `record_skill_invocation` + `seed_gate_artifact_files` under `core/skills/invocation.py`. Duplicate `_load_packs` / `_SKILL_SPECIFIER_RE` / `_SKILL_FM_RE` removed from `interfaces/cli/ds.py`; the canonical `_load_packs` lives in `core/skills/queries.py`. Phase A3 workflow runner can now compose these three functions directly. No policy or contract change here. -->