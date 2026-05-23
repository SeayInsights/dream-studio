# Shared Authority And Adapter Projections

Dream Studio is the source of truth for local-first AI orchestration and
operational intelligence. Claude, Codex, Cursor, Copilot, ChatGPT, MCP, local
models, shell tools, and future tools are adapters over Dream Studio authority.

## Canonical Authority

Canonical records live in:

- repo source for product code, schemas, skills, workflows, hooks, docs, and
  tests;
- operator-local SQLite for Work Orders, route decisions, telemetry facts,
  learning events, adapter profiles, model/provider profiles, context packets,
  normalized adapter results, hardening candidates, project authority, PRD
  authority, validation results, and security findings;
- operator-local evidence packets for human-readable exports and audit trails.

Dashboard data is a derived view. It must include `derived_view=true` and
`primary_authority=false` when exposed through API/read-model surfaces.

## Adapter Role

Adapters execute, review, explain, or project context. They do not own source
of truth.

Adapter-specific files such as `CLAUDE.md`, `AGENTS.md`, Cursor rules, Copilot
instructions, MCP command templates, and shell launchers are projections from
Dream Studio authority. They should say what authority they project from and
should be refreshed when SQLite/repo authority changes.

Repo-root `CLAUDE.md` and `AGENTS.md` are the active Claude/Codex project
surfaces when those adapters load the repository. Files under
`adapter-projections/` are generated projection artifacts used for verification,
staleness detection, export, and future sync/install flows. They do not become
active adapter config merely by existing; active-surface refresh requires an
explicit approved projection repair or install boundary.

Adapter scratch folders, app-created worktrees, local session histories, and
runtime caches are not adapter projections. They must stay under user-local
Dream Studio state or a checkout-local excluded path, and they must not pollute
repo status. Unknown adapter files require classification before any ignore,
delete, archive, or cleanup decision. Secret/auth/token paths may be recorded as
path-level metadata only; do not inspect or print their contents.

Installed adapter access should prefer the local Dream Studio router where
possible. The router is exposed through `ds router`, `ds adapters`, and
`/api/shared-intelligence/adapter-router`; it reports adapter health, route
state, context packet generation, evidence capture, telemetry capture, module
profile status, and Contract Atlas availability without making an adapter own
Dream Studio logic. Adapters that cannot call the router should consume exported
context packets and return normalized evidence for Dream Studio to ingest.
Productized installs use `ds install` and selected module profiles to create
the user-local runtime home that these adapter/router surfaces read from.
Unsupported tools remain context-packet-only rather than receiving overclaimed
router support. Repo-owned launchers such as `ds.cmd` and `ds.ps1` may expose
the global command surface, and `ds install-command` can materialize user-local
launchers in a PATH directory. They still delegate back to Dream Studio source
and SQLite authority.

The installed dashboard command follows the same projection boundary. `ds
dashboard --status` is the safe default/readiness mode, `--serve` starts the
local dashboard server with explicit source/home/SQLite environment, `--open`
starts or reuses the server and opens a browser, and `--check` probes route
health. These commands expose derived dashboard/API surfaces; they do not make
the dashboard primary authority or authorize migrations, backfills, cleanup, or
destructive SQLite mutation.

Security lifecycle access follows the same boundary. Adapters may read
`/api/shared-intelligence/security-lifecycle` or a generated context packet to
understand which 47-control checks are applicable, deferred, or blocking, but
they do not become security authority and must normalize results back into
Dream Studio records.

Production readiness access follows the same model. Adapters may read
`/api/shared-intelligence/production-readiness` and
`/api/shared-intelligence/production-readiness/controls` to understand
readiness posture, but persisted readiness authority remains in Dream Studio
SQLite records and evidence refs.

Module contract access is read-only. Adapters and dashboard tools may read
`/api/shared-intelligence/module-contracts` or the Contract Atlas section to
understand which modules own authority, which dependencies are optional, and how
disabled modules should behave. Those contracts do not authorize adapter
execution, repo mutation, Docker execution, or live SQLite writes.

AI usage accounting follows the same projection rule. Adapter-local files and
private model memory do not own billing mode, token visibility, cost visibility,
usage source, cost source, confidence, or operational outcome data. Those
records live in SQLite through `ai_adapter_accounting_profiles`,
`ai_usage_operational_records`, `token_usage_records`, and
`task_attribution_records`, then project into the router, Contract Atlas,
dashboards, and context packets. Subscription-plan tools must display cost as
`unknown` unless an explicit allocation profile is present.

Task attribution is adapter-readable but not adapter-owned. Meaningful
execution units should normalize back into `task_attribution_records` with
project, milestone, task, Work Order, process run, adapter, model/provider where
known, skills/workflows, hooks/tools, files touched, commands, validation,
outcome, rework, evidence refs, and security/readiness impact. If an adapter
run was not routed through Dream Studio, the source class should say
`untracked`, `imported_manual`, or `adapter_reported` instead of pretending the
execution was fully observed.

Contract Atlas lifecycle access is also read-only by default. Adapters may call
`ds contract-atlas-refresh` in dry-run mode or read
`/api/shared-intelligence/contract-atlas/freshness` to understand contract,
maturity, docs, PRD, README, dashboard/API, and sanitized export freshness.
Writing export files requires an explicit output directory and `--execute`; it
does not authorize SQLite mutation or adapter config repair.

Analytics-only ingestion is a current-authority import path, not adapter
authority. Tools may produce normalized JSON for projects, CI/validation,
security findings, token/usage telemetry, components, dependencies, PRDs, and
readiness assessments. `ds analytics-ingest` plans by default and writes only
with `--execute`. It imports into SQLite authority tables and keeps hooks,
agents, workflows, Claude, Codex, Docker, repo mutation, and cleanup optional or
out of scope.

PRD lifecycle access is read-only by default for adapters. Context packets and
`/api/shared-intelligence/prd-authority` expose current PRD version, milestone,
active Work Order, assumptions, known unknowns, relevant change orders,
security/readiness constraints, evidence refs, allowed scope, validation
expectations, and stop gates. They exclude unrelated project history, full
private operational history, career data, secrets, and raw local evidence
unless explicitly scoped.

Expert workflow access is read-only by default. Adapters may read
`/api/shared-intelligence/expert-workflows` or a context packet summary to
understand the intentional implementation, code quality, debugging,
performance, frontend design, SEO/content, documentation, data modeling, API
integration, case-study, and career/portfolio workflow contracts. Results must
normalize back into Dream Studio authority records when execution is approved.
The route does not replace existing skills, publish private career data, fill
applications, or authorize browser automation.

Career Ops follows the same authority boundary. Adapter outputs may help draft
private career material only after the module is enabled and scoped; career
profiles, application records, generated materials, and browser automation
evidence persist in local SQLite authority and stay out of public exports by
default.

Capability Center and scoped-agent routes are adapter-readable projections.
They explain which skills, workflows, agents, controls, evaluations, and
hardening candidates exist, but they do not authorize execution. Scoped agents
receive only the context named by their task contract and must normalize
results back into Dream Studio authority.

GitHub repo intake routes are also projections over authority. They record
license, security, dependency, maintenance, overlap, attribution, and adoption
decisions before Dream Studio uses third-party repositories. They do not fetch
or mutate repositories, copy code, add dependencies, fork, vendor, or waive
legal/security review.

External project validation follows the same projection discipline. External
targets are registry entries and dashboard cards until the current operator
decision selects a target and scope. Planning can describe dirty-state capture,
PRD/status detection, stack/dependency discovery, security/readiness
classification, validation profile, Work Orders, and commit policy, but it does
not inspect or mutate the target repo.

Long-run multisession validation is also derived evidence. It aggregates
dashboard/authority, dogfood route, release gate, installed command, docs drift,
security/readiness, adapter/router, and analytics-only cycles with a live SQLite
hash guard. It does not turn adapter output, dashboard output, Docker status, or
external target metadata into source authority.

Private model memory is never authority. If another AI resumes work, Dream
Studio should provide a shared context packet from SQLite/evidence records.

## Convergence Rules

When duplicate legacy state exists:

1. classify the source;
2. migrate real data into current authority where possible;
3. prove current API/read models consume current authority;
4. verify no active reference depends on the old source;
5. purge only the old source rows proven migrated, obsolete, mock, demo, temp,
   or placeholder;
6. keep unknown or sensitive items under manual review.

Rollback backups remain protected until a separate cleanup approval boundary.

Legacy install upgrades follow the same convergence rule. Old repo checkouts,
old `.dream-studio` homes, old launchers, old Claude/Codex hook paths, and old
adapter projections are detection inputs, not authority. Compatible records may
be rehydrated into current SQLite tables with source references and row-count
evidence; legacy Work Order, handoff, report, prompt, cache, log, audit, and
raw evidence file-sprawl stays in backup/manual review and must not become an
active competing store.

## Cross-AI Continuity

Dream Studio records adapter profiles, model/provider profiles, generated
context packets, normalized adapter results, capability routes, learning events,
and hardening candidates in SQLite. A Claude-style packet and a Codex-style
packet generated from the same source should explain the same project state.
Their results should normalize into one shared Dream Studio history.

## Container Boundary

Docker is optional. It can support scanners, workers, adapters, dashboard/API
profiles, and validation sandboxes, but it must not create a second authority
database. Docker-backed modules should receive an explicit SQLite path or a
read-only/rehearsal copy according to their approved profile.
Static Docker profile contracts can be used operationally for planning and
status, but container execution requires separate approval.
## Platform Hardening Refresh

Platform-hardening reinforces the shared-authority rule: adapters may produce evidence, usage, connector payloads, policy previews, demo packets, and validation outcomes, but those results must normalize into Dream Studio SQLite authority or sanitized derived exports. Adapter projections remain generated config surfaces and must not become competing source authority.

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

<!-- Last reviewed 2026-05-21 — Platform detection added: `core.config.platform` detects OS, shell, Python version, and terminal at install/doctor time. Profile persisted to `~/.dream-studio/state/platform.json` (private local state, never committed). This is not SQLite authority and not an adapter projection. Override path via `DS_PLATFORM_PROFILE_PATH` env var; used for shell-correct error messages and diagnostic output. Adapter projections such as `CLAUDE.md` remain generated projections; platform detection is a runtime config helper, not an adapter surface. -->

<!-- Last reviewed 2026-05-21 — TA0 SDLC entity creation events: interfaces/cli/ds.py change in this PR is a CLI handler refactor only. _project_register now delegates to core.projects.mutations.register_project() instead of containing an inline INSERT. This aligns the CLI with the A2 refactor pattern already applied to all other project/milestone/work-order handlers. No new CLI surface, no new permissions, no installer change, no runtime path change, no adapter boundary change. No policy or contract change in this doc. -->

<!-- Last reviewed: TA2 (2026-05-22) — no structural change required for this workstream -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->

<!-- Last reviewed 2026-05-22 — Phase 18.1.5: L3 hub-and-spoke projection tables (business_work_orders and future peers) are derived views from business_canonical_events and ai_canonical_events. They do not become primary authority; the dual canonical tables remain the canonical source. ProjectionEngine reads from canonical, writes to L3 via idempotent safe_upsert, and tracks cursor position in projection_state. Adapters consuming L3 projections should treat them as derived views with projection_state.last_run_at as the freshness signal. -->
