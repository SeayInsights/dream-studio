# Installed Adapter Runtime

Dream Studio should behave as an installed local orchestration layer. Normal
adapter and operator workflows should not require manually opening a shell in
the Dream Studio source checkout.

## Runtime Model

The installed runtime keeps source and state separate:

| Area | Location | Authority |
| --- | --- | --- |
| Source/build | Dream Studio checkout or installed source root | repo source |
| User-local state | `~/.dream-studio` or explicit `DREAM_STUDIO_HOME` | local runtime state |
| SQLite authority | `~/.dream-studio/state/studio.db` | canonical local SQLite |
| Adapter runtime | `~/.dream-studio/adapters` | user-local adapter state |
| Router runtime | `~/.dream-studio/router` | user-local router state |
| Context packets | `~/.dream-studio/context-packets` | user-local packet exports |
| Evidence | `~/.dream-studio/meta` | file-backed private evidence |

The source root can be supplied with `--source-root` or
`DREAM_STUDIO_SOURCE_ROOT`. The runtime home can be supplied with `--home` or
`DREAM_STUDIO_HOME`. Commands must not assume the current working directory is
the Dream Studio repo.

Runtime helpers that need the user-local Dream Studio home must honor
`DREAM_STUDIO_HOME` before falling back to `~/.dream-studio`. This keeps
rehearsals, CI gates, and installed adapter launches from touching the
operator's live runtime state unless a live update scope has been approved.

## Global Command Surface

The installed command surface is `ds`:

```text
ds status
ds install
ds install-command
ds dashboard
ds dashboard --status
ds dashboard --serve
ds dashboard --open
ds dashboard --check
ds validate
ds contract-atlas
ds contract-atlas-refresh --output-dir C:\path\to\private-or-public-export
ds adapters
ds context-packet --adapter codex
ds modules
ds router
ds analytics-ingest --file payload.json
ds acceptance
ds backup
ds restore-check
ds update-check
ds migrate-legacy --dry-run
ds repair-adapters
ds rollback-check
ds uninstall-check
```

When running directly from a checkout before packaging, use:

```powershell
python C:\path\to\dream-studio\interfaces\cli\ds.py --source-root C:\path\to\dream-studio status
```

On Windows, `ds.cmd` and `ds.ps1` are repo-owned launchers for the same global
command surface. `ds.cmd` is the preferred plain-command launcher because it
works in normal `cmd.exe` and PowerShell shells without changing script
execution policy:

```powershell
C:\path\to\dream-studio\ds.cmd --home C:\temp\dream-studio status
```

Installed users can materialize user-local launchers with
`ds install-command --execute` after the source and home paths are configured.

Legacy installs are not treated as ordinary Git updates. `ds install
--check-legacy` and `ds migrate-legacy --dry-run` detect old source/runtime
paths and stale adapter surfaces before any write. `ds repair-adapters` updates
only Dream-Studio-owned launcher and adapter hook paths after a backup or
explicit repair approval; it must not inspect secrets or rewrite unrelated
Claude, Codex, Cursor, Copilot, MCP, or shell configuration.

The command surface resolves source/state from explicit configuration, opens
SQLite authority through Dream Studio's existing bootstrap/access layer, and
prints JSON so shells, adapters, MCP clients, and dashboard tools can consume it.

## Adapter Router

The adapter router is a local read model exposed by:

- `ds router`
- `ds adapters`
- `/api/shared-intelligence/adapter-router`

It reports current route state, adapter health, context-packet availability,
Contract Atlas availability, module profile status, telemetry/evidence capture
capabilities, and adapter workspace hygiene. It does not execute adapters,
mutate routing policy, write adapter configs, or write live SQLite by default.

The final productization closeout also treats the adapter router as one of the
long-run validation cycles. Passing closeout requires adapter status evidence,
context-packet fallback documentation, and no drift from the proven Claude/Codex
baseline unless Dream Studio explicitly detects adapter staleness.

## Usage Accounting

The adapter router also reports `usage_accounting`. This is a derived read
model over current SQLite authority and includes:

- declared adapter accounting profiles;
- token usage records grouped by adapter/model/provider;
- operational value metrics such as run count, files touched, commands run,
  validation outcome, success/failure, rework, and duration when recorded;
- billing mode, token visibility, cost visibility, usage source, cost source,
  and confidence.

Plan-based surfaces do not receive fabricated per-run dollar costs. When cost
evidence is missing, installed commands and dashboard routes must display
`unknown`, not `$0.00` or a token-derived estimate.

The shared-intelligence route surface also exposes
`/api/shared-intelligence/security-lifecycle`. That surface is a read-only
installed runtime capability for security classification and release-readiness
status; it does not run scans, inspect secrets, or write runtime state.

It also exposes `/api/shared-intelligence/production-readiness` and
`/api/shared-intelligence/production-readiness/controls`. These installed
surfaces preview readiness gates or read persisted SQLite readiness summaries
without executing checks, mutating adapter config, or writing live state from a
GET request.

It also exposes `/api/shared-intelligence/expert-workflows`. This is a
read-only installed surface for expert workflow definitions, overlap decisions,
evidence-backed scoring rubrics, career privacy boundaries, and application
automation rules. It does not execute skills, fill applications, publish
career artifacts, mutate SQLite, or replace the existing skill/workflow owners.

Supported adapter access modes:

| Mode | Meaning |
| --- | --- |
| `repo_attached` | Adapter reads repo-root projection files in an open checkout. |
| `cli_with_workdir` | Adapter invokes `ds` or tools with an explicit source root/workdir. |
| `app_workspace` | App has a configured workspace/source root. |
| `cloud_repo_environment` | Cloud environment can read repo files but local runtime is not proven. |
| `mcp_capable` | Client can call a local/MCP bridge when configured. |
| `context_packet_only` | Tool can consume exported packets but not local router APIs. |
| `unsupported` | No supported access path is currently proven. |

Current baseline:

- Claude Code CLI: `live_consumption_proven`
- Claude Code app/workspace:
  `live_consumption_proven_with_workspace_head_check`
- Codex CLI: `live_consumption_proven`
- Codex app configured environment: `live_consumption_proven`
- Codex cloud/GitHub environment: `not_proven_in_local_runtime`
- MCP-capable clients: `router_contract_available`
- shell tools: `supported_via_global_ds_command`
- plain web/chat tools: `context_packet_only`

External project and Docker profile status remain adjacent runtime surfaces,
not adapter authority. External targets require current target selection before
read-only intake, and Docker profiles require explicit operator approval before
any container execution.

## Module Profiles

Installed profiles are declared in `core.module_profiles`:

- `core`
- `career_ops_only`
- `analytics_only`
- `security_only`
- `token_only`
- `telemetry_only`
- `dashboard_only`
- `adapter_router_only`
- `shared_intelligence_only`
- `full`

Each profile declares includes, excludes, dependencies, commands/routes, hook
requirements, agent/workflow requirements, Claude/Codex requirements, Docker
requirements, expected dashboard/API behavior, and honest empty states.

Module boundaries are separately declared in `core.module_contracts` for:
`core`, `career_ops`, `telemetry`, `dashboard`, `security_only`, `token_only`,
`analytics_only`, `shared_intelligence`, `adapter_router`,
`adapter_projection`, `external_project`, `capability_center`,
`scoped_agents`, `github_repo_intake`, `docker_optional`, and `full`.
Each contract declares purpose, owned authority, read/write dependencies,
events, API routes, dashboard surfaces, CLI commands, profile membership,
disabled-module behavior, empty-state behavior, security/readiness impact,
Contract Atlas maturity, and validation tests.
The direct read-only API surface is `/api/shared-intelligence/module-contracts`.

`analytics_only` must work without hooks, agents, workflows, Claude, Codex, repo
mutation, or Docker. It exposes read-only telemetry/shared-intelligence surfaces
and uses honest empty states when no facts exist.

`token_only` reports token and AI usage telemetry without inventing per-run
cost. Unknown or plan-based costs remain unknown unless provider metadata,
provider exports, billing API data, or explicit allocation metadata makes cost
reportable.

Task attribution is available to installed shared-intelligence, dashboard, and
adapter-router profiles through read-only SQLite-backed routes. It reports
adapter, skill/workflow, file, command, validation, outcome, rework, and
security/readiness impact facts when recorded, while preserving `unknown` or
`unavailable` values for unobserved model/provider, file, command, token, or
cost details.

`career_ops_only` is private and opt-in. It exposes private Career Ops status
and dashboard routes without requiring hooks, agents, workflows, Claude, Codex,
or Docker. Career data stays in local SQLite authority and is excluded from
public exports by default.

`shared_intelligence_only` includes Capability Center, scoped-agent registry
views, and GitHub repo intake read models. These surfaces are read-only unless a
separate approved command writes authority records through an injected/current
SQLite connection.

Analytics-only also exposes explicit normalized ingestion through:

```powershell
ds analytics-ingest --file C:\path\to\payload.json
ds analytics-ingest --file C:\path\to\payload.json --execute
```

The command is dry-run by default. `--execute` writes idempotent normalized
records into current SQLite authority tables for projects, CI/validation,
security findings, token/AI usage, components/dependencies, PRDs, and
readiness scorecards. Hooks are optional producers of those payloads; they are
not required dependencies. The command must not mutate repos, require Claude or
Codex, run Docker, inspect secrets, or create legacy file-sprawl.

## Rehearsal Install

Rehearsal installs must use a temporary Dream Studio home:

```powershell
python interfaces\cli\ds.py --source-root C:\path\to\dream-studio rehearsal-install --rehearsal-home C:\temp\dream-studio-home
```

This creates temp state, bootstraps SQLite, writes rehearsal runtime config,
creates adapter/router/context packet directories, registers default adapter
profiles, and previews a context packet. It does not mutate live installed
state.

The productized first-run path also supports selected module profiles:

```powershell
python interfaces\cli\ds.py --source-root C:\path\to\dream-studio --home C:\temp\dream-studio-home install --rehearsal --profile analytics_only
```

Use `ds acceptance` against a temporary home to validate fresh setup,
selected/unselected module behavior, dashboard status, adapter status,
analytics-only independence, security-only independence, full profile behavior,
backup/restore/update checks, and uninstall dry-run behavior.

## Live Update Readiness

After rehearsal passes, a live update may be planned, but it requires a separate
operator-approved scope before mutating `~/.dream-studio`. The live update plan
should copy or refresh only installed runtime/router config needed to point
adapters at the validated source root and local SQLite authority. It must not
delete, archive, compact, deduplicate, inspect secrets, run Docker, deploy, or
destructively migrate SQLite.
## Platform Hardening Refresh

The installed adapter runtime now exposes platform-hardening as a derived status surface through `/api/shared-intelligence/platform-hardening` and `ds platform-hardening`. These additions preserve the installed runtime boundary: adapter/router state remains under user-local Dream Studio state, source remains in the repo, and no adapter surface becomes primary authority.

## PRD Lifecycle Context

Installed adapters consume PRD lifecycle authority through context packets and
shared-intelligence routes. The adapter runtime does not own PRD state; it
passes current PRD version, milestone, Work Order, change-order, validation,
and stop-gate context from SQLite authority to supported tools.

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

<!-- Last reviewed 2026-05-21 — Platform profile added to runtime state: `~/.dream-studio/state/platform.json` is written at install time and refreshed by `ds doctor`. It records OS, shell, Python version, and terminal. Override via `DS_PLATFORM_PROFILE_PATH` env var for test isolation. This file is local state (ignored by git) and is not SQLite authority. The installed adapter runtime now includes platform.json alongside studio.db in the `state/` directory. -->

<!-- Last reviewed 2026-05-21 — TA0 SDLC entity creation events: interfaces/cli/ds.py change in this PR is a CLI handler refactor only. _project_register now delegates to core.projects.mutations.register_project() instead of containing an inline INSERT. This aligns the CLI with the A2 refactor pattern already applied to all other project/milestone/work-order handlers. No new CLI surface, no new permissions, no installer change, no runtime path change, no adapter boundary change. No policy or contract change in this doc. -->

<!-- Last reviewed: TA2 (2026-05-22) — no structural change required for this workstream -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->

<!-- Last reviewed 2026-05-22 — Phase 18.1.5: projection runner daemon (core/projections/runner.py) added as an optional background runtime component. Runner writes PID to ~/.dream-studio/state/projection_runner.pid and is controlled via `ds projection daemon start/stop/status`. It runs ProjectionEngine.run_cycle() on a configurable poll interval (default 5s, PROJECTION_POLL_INTERVAL env var) and does not start automatically — operator must invoke `ds projection daemon start`. Installed runtime model unchanged; runner is an opt-in background process alongside the existing ds command surface. -->


<!-- Last reviewed 2026-05-23 -- Phase 18.1.7: ds_* project-spine tables renamed to business_* via migration 070. No policy or boundary change in this doc; runtime table names updated. -->


<!-- Last reviewed 2026-05-24 — Phase 18.1.13: ds validate and ds doctor --help text updated to explicitly identify each command's health-check plane. ds validate description now reads: DB authority plane (schema version, migrations, module profiles). ds doctor description now reads: Claude Code integration plane (skills, agents, hooks, routing, version). Each help text cross-references the other command. README.md health-checks section expanded; docs/operations/fresh-install-validation.md updated to require both commands. No runtime behavior change. No new CLI surface. No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-26 — Phase 18.1.15b: ds.py updated to read skip_hook_install from config.json in _integrate_dispatch. No changes to the installed runtime contract, adapter routing, or global command surface described in this doc. -->

<!-- Last reviewed 2026-05-27 — Phase 18.2.5: ds.py gains --include-deleted flag on ds project list subcommand to surface soft-deleted projects. No changes to installed runtime paths, adapter routing contracts, global command surface, productization lifecycle, or platform hardening policy described in this doc. -->
