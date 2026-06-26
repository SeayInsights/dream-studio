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
and case-study workflow expectations without executing a
skill or relying on the current working directory.

The surface is a read-only catalog. It does not execute skills, mutate SQLite,
or replace the existing skill/workflow owners.

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

`ds restore <backup>` performs the mutating restore. With no flags it is a dry-run
(validate + plan). `--execute` takes a pre-restore backup of the current state
first (written outside the home so it survives), then replaces the state-tier
databases (`studio.db` / `files.db`) from the chosen backup. `--force` overrides a
not-restore-ready backup. See the [restore contract](../contracts/restore-contract.md).

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

`ds uninstall` performs the mutating teardown. With no flags it is a dry-run
(plan only). `--execute` removes the `.claude` hook wiring from both generated
settings.json copies and the global `ds` launchers, leaving `~/.dream-studio`
state intact (reversible by reinstall). `--purge-state --force` additionally
wipes the state tier, but only after taking an automatic backup outside the home
first. The mandatory second confirmation (`--force`) is enforced. See the
[uninstall contract](../contracts/uninstall-contract.md).

Live restore or update execution requires a separate operator-approved scope.

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
<!-- Last reviewed 2026-05-20 — A2.5: `_design_brief_create` lifted to `create_design_brief` in `core/design_briefs/mutations.py` (returns dict with brief_id, project_id, status, next_step). CLI wrapper preserves the legacy `Draft brief created:` stdout line. A2.4's lazy `from interfaces.cli.ds import _design_brief_create` in `core/skills/invocation.py` is now a direct `core.design_briefs.mutations` import. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.6: `_design_brief_lock` lifted to `lock_design_brief` in `core/design_briefs/mutations.py` (returns dict with brief_id, status='locked', locked_at; ok=False/error for missing brief). CLI wrapper preserves the legacy `Brief <id> locked.` stdout line and exit-1 JSON path. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.7: `_milestone_close` lifted to `close_milestone` in `core/milestones/close.py`. Pure function returns one canonical result dict across every path (missing milestone / open WOs / gate failures / forced bypass / success); CLI wrapper preserves the legacy mixed-format operator output (JSON for failures, plain-text on success, `[gate.bypassed] WARNING:` stderr on force). No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A2.8: `_update_command` no longer self-shells via `subprocess.run(['ds','integrate','install','claude_code','--execute'])`; instead it calls `ClaudeCodeInstaller.install('execute')` directly in-process, mirroring the `ds integrate install` code path. Skips interpreter respawn, keeps tracebacks intact, and lets callers patch the installer with `unittest.mock`. Final A2 handler. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — A6.3: `_project_delete` lifted to `delete_project` in `core/projects/mutations.py` (returns dict; CLI wrapper preserves the `--confirm` operator-facing text). New `ds-project:manage` mode under `canonical/skills/ds-project/modes/manage/` wraps `get_project_list` + `set_active_project` + `deactivate_project` + `delete_project` per the AI-presents-from-database discipline. Final A6 PR. No policy or contract change here. -->
<!-- Last reviewed 2026-05-20 — B.3: git pre-push hook + installer wiring landed. `ds workflow run pre-push --non-interactive` dispatches deterministic gates; `ClaudeCodeInstaller.git_repo_root` opt-in plants `<repo>/.git/hooks/pre-push`. No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-21 — First-run setup now records a platform profile at `~/.dream-studio/state/platform.json` immediately after runtime directories are created, before SQLite bootstrap. This makes OS, shell, Python version, and terminal available to any subsequent install step that needs shell-correct output. `ds doctor` also refreshes the profile. Both paths use `core.config.platform.ensure_platform_recorded()`. The platform profile is local state, not SQLite authority, and does not require a migration. -->

<!-- Last reviewed 2026-05-21 — TA0 SDLC entity creation events: interfaces/cli/ds.py change in this PR is a CLI handler refactor only. _project_register now delegates to core.projects.mutations.register_project() instead of containing an inline INSERT. This aligns the CLI with the A2 refactor pattern already applied to all other project/milestone/work-order handlers. No new CLI surface, no new permissions, no installer change, no runtime path change, no adapter boundary change. No policy or contract change in this doc. -->

<!-- Last reviewed: TA2 (2026-05-22) — no structural change required for this workstream -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->

<!-- Last reviewed 2026-05-22 — Phase 18.1.5: `ds projection` command group added to the installed command surface (list, status <name>, rebuild <name>, dead-letter list/retry/resolve, daemon start/stop/status). These are read-only or controlled-mutation commands. No new install profile required; projection CLI is part of the existing full and core profiles via interfaces/cli/projection_cli.py registered in ds.py. -->


<!-- Last reviewed 2026-05-23 -- Phase 18.1.7: ds_* project-spine tables renamed to business_* via migration 070. No policy or boundary change in this doc; runtime table names updated. -->


<!-- Last reviewed 2026-05-24 — Phase 18.1.13: ds validate and ds doctor --help text updated to explicitly identify each command's health-check plane. ds validate description now reads: DB authority plane (schema version, migrations, module profiles). ds doctor description now reads: Claude Code integration plane (skills, agents, hooks, routing, version). Each help text cross-references the other command. README.md health-checks section expanded; docs/operations/fresh-install-validation.md updated to require both commands. No runtime behavior change. No new CLI surface. No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-26 — Phase 18.1.15b: ds.py updated to read skip_hook_install from config.json in _integrate_dispatch. No changes to the installed runtime contract, adapter routing, or global command surface described in this doc. -->

<!-- Last reviewed 2026-05-27 — Phase 18.2.5: ds.py gains --include-deleted flag on ds project list subcommand to surface soft-deleted projects. No changes to installed runtime paths, adapter routing contracts, global command surface, productization lifecycle, or platform hardening policy described in this doc. -->

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-05: Phase 18.6.2 reviewed — module_contracts.py removed project_health_scorecards and project_readiness_scorecards from analytics_only read_dependencies (tables dropped in migration 099). No semantic change to this document required. -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. Dropped `career/portfolio` from the expert-workflow-surface catalog list and replaced the career-automation-runner caveat with a generic read-only-catalog caveat; removed the `career_ops_only` opt-in private module paragraph under "Private Capability Modules" (the scoped-agent privacy sentence stays). -->

<!-- 2026-06-06: Wave 6 — 13 verified-dead tables dropped (migration 101). no semantic change required. -->

<!-- reviewed: 2026-06-06, WO-C orphan rot sweep. core/module_contracts.py: removed dead test file reference from 3 module validation_tests lists. No module profile, install runtime, or productization behavior change. No semantic change required. -->

<!-- Last reviewed 2026-06-07 — WO-F prd_* cluster drop (migration 103): migration 103 drops the entire prd_* cluster (prd_documents, prd_plans, prd_tasks, prd_sessions, prd_handoffs, session_tasks, prd_version_records, prd_amendment_records, prd_route_reconciliation_records) and the views vw_prd_progress and vw_task_details. AD-10 decision: business_projects IS what PRD was. All prd_* callers removed from studio_db.py, prd_authority.py (deleted), routes/prd.py (deleted), analytics_ingestion.py, module_contracts.py, dashboard_freshness.py, contract_atlas.py, contract_registry.py, project_intelligence.py, shared_intelligence.py, resume_from_handoff.py, and migrate_prd_schema.py (deleted). -->

<!-- reviewed 2026-06-26: migration 128 dead-tables removal — no content changes required -->
