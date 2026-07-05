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
and SQLite authority. `ds uninstall` reverses this projection: it deregisters the
Dream-Studio hook wiring from both generated `.claude/settings.json` copies and
removes the launchers, while preserving the SQLite authority state tier unless
`--purge-state --force` is given (which backs up before wiping). `ds restore
<backup>` is the inverse of `ds backup`: it replaces the state-tier databases from
a chosen backup, taking a pre-restore backup of current state first so the restore
is itself reversible.

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
integration, and case-study workflow contracts. Results must
normalize back into Dream Studio authority records when execution is approved.
The route does not replace existing skills or authorize browser automation.

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

<!-- Last reviewed 2026-05-28 — Projection staleness fix: adapter-projections/claude/CLAUDE.md was carrying a stale Skill Routing section that made its SHA256 mismatch the generator output, causing aligned_count to report 7 instead of 8 and boundary_violation_report to show attention_required. The extra block was removed so the file matches _projection_content exactly. Policy unchanged: adapter-projections/ files are generated artifacts, not active config. No adapter boundary or authority change. -->

<!-- Last reviewed: TA2 (2026-05-22) — no structural change required for this workstream -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->

<!-- Last reviewed 2026-05-22 — Phase 18.1.5: L3 hub-and-spoke projection tables (business_work_orders and future peers) are derived views from business_canonical_events and ai_canonical_events. They do not become primary authority; the dual canonical tables remain the canonical source. ProjectionEngine reads from canonical, writes to L3 via idempotent safe_upsert, and tracks cursor position in projection_state. Adapters consuming L3 projections should treat them as derived views with projection_state.last_run_at as the freshness signal. -->


<!-- Last reviewed 2026-05-23 -- Phase 18.1.7: ds_* project-spine tables renamed to business_* via migration 070. No policy or boundary change in this doc; runtime table names updated. -->


<!-- Last reviewed 2026-05-24 — Phase 18.1.13: ds validate and ds doctor --help text updated to explicitly identify each command's health-check plane. ds validate description now reads: DB authority plane (schema version, migrations, module profiles). ds doctor description now reads: Claude Code integration plane (skills, agents, hooks, routing, version). Each help text cross-references the other command. README.md health-checks section expanded; docs/operations/fresh-install-validation.md updated to require both commands. No runtime behavior change. No new CLI surface. No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-26 — Phase 18.1.15a: adapter-projections/ floating files removed (chatgpt, codex, copilot, cursor, local-model, mcp, shell adapter projection files and README). These were stale drafts not wired to the adapter runtime; their removal does not change the adapter boundary or projection authority described in this doc. No policy or contract change. -->

<!-- Last reviewed 2026-05-26 — Phase 18.1.15b: ds.py updated to read skip_hook_install from config.json in _integrate_dispatch. No changes to the installed runtime contract, adapter routing, or global command surface described in this doc. -->

<!-- Last reviewed 2026-05-27 — Phase 18.2.5: ds.py gains --include-deleted flag on ds project list subcommand to surface soft-deleted projects. No changes to installed runtime paths, adapter routing contracts, global command surface, productization lifecycle, or platform hardening policy described in this doc. -->

<!-- Last reviewed 2026-05-28 — fix/linux-ci-failures-batch2: adapter-projections/ now contains all 8 generated files from default authority profiles (chatgpt, claude, codex, copilot, cursor, local-model, mcp, shell). The 7 previously missing files (removed in Phase 18.1.15a as stale drafts) have been regenerated from sqlite:adapter_authority_profiles defaults. The claude/CLAUDE.md file was also regenerated to match default profile sha256. No adapter boundary or projection authority policy change. -->

<!-- Last reviewed 2026-05-28 — fix/full-ci-failures-batch3: adapter-projections/claude/CLAUDE.md restored to have the routing-table placeholder (BEGIN/END AUTO-ROUTING markers with the ROUTING TABLE GENERATED BY COMPILER comment). The prior batch2 regeneration lost the placeholder section; test_adapter_projection_source_contains_placeholder_not_hardcoded_table now passes. No adapter boundary or projection authority policy change. -->

<!-- Last reviewed 2026-05-28 — fix/claude-projection-routing-placeholder: adapter_config_projection._projection_content() updated to emit the Skill Routing section with BEGIN/END AUTO-ROUTING markers and the compiler placeholder for claude-type adapters. The adapter-projections/claude/CLAUDE.md file now matches the generator SHA256 while also satisfying the compiler routing test. This resolves the two-system conflict introduced in batch2/batch3: staleness check and compiler test now agree on the canonical source content. -->

<!-- Last reviewed 2026-05-29 — Phase 18.4.6 migration-risk gate: CLAUDE.md updated to add the universal merge-authorization two-tier rule (pre-push gate = push-auth; 3-platform matrix = merge-auth) and the OOM/subset reality note (pre-push runs tests/evals/ only; full suite only runs in remote CI). This is an adapter-projection boundary change because CLAUDE.md is the claude-adapter projection document. The rule content is factual operational discipline, not a new adapter boundary or authority-model change. -->

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->

<!-- 2026-06-01: security_scan_runs → scan_runs, security_findings → findings, security_scan_deltas → scan_deltas (migration 089); brownfield intake prompt added; proving-index.md added. -->

<!-- 2026-06-05: Phase 18.6.2 reviewed — module_contracts.py removed project_health_scorecards and project_readiness_scorecards from analytics_only read_dependencies (tables dropped in migration 099). No semantic change to this document required. -->

<!-- 2026-06-05: Wave 2 career annihilation — career_ops module, 15 career_* tables (migration 100), ds-career skill pack, /career-ops route, career_ops contract+profile, and career expert workflow removed. capability_center/scoped_agents/github_repo_intake unchanged. Dropped "career/portfolio" from the expert-workflow contract list, removed the career/application/browser-automation caveats and the "Career Ops follows the same authority boundary" paragraph; the PRD-lifecycle "career data" exclusion stays as a deny-by-default privacy class. -->

<!-- 2026-06-06: Wave 6 — 13 verified-dead tables dropped (migration 101). no semantic change required. -->

<!-- reviewed: 2026-06-06, WO-C orphan rot sweep. core/module_contracts.py: removed dead test file reference from 3 module validation_tests lists. No shared authority boundary or adapter projection contract change. No semantic change required. -->

<!-- Last reviewed 2026-06-07 — WO-F prd_* cluster drop (migration 103): migration 103 drops the entire prd_* cluster (prd_documents, prd_plans, prd_tasks, prd_sessions, prd_handoffs, session_tasks, prd_version_records, prd_amendment_records, prd_route_reconciliation_records) and the views vw_prd_progress and vw_task_details. AD-10 decision: business_projects IS what PRD was. All prd_* callers removed from studio_db.py, prd_authority.py (deleted), routes/prd.py (deleted), analytics_ingestion.py, module_contracts.py, dashboard_freshness.py, contract_atlas.py, contract_registry.py, project_intelligence.py, shared_intelligence.py, resume_from_handoff.py, and migrate_prd_schema.py (deleted). -->


<!-- Last reviewed 2026-06-20 — WO-P20-AGENTS-GEN: AGENTS.md is now the GENERATED universal adapter target (integrations/compiler/agents_md.py) emitting the routing table + WO types + gate defs from packs.yaml + canonical. The Claude-Code compiler (claude_code.py) reduces CLAUDE.md to import @AGENTS.md instead of embedding the routing table, and ships AGENTS.md in the install pack. No authority/projection-boundary change: routing still derives from canonical; this de-duplicates it across adapter files. -->

<!-- Last reviewed 2026-06-20 — WO-P20-FULLCI-FIX: the generated AGENTS.md header now includes the lowercase "projection" authority marker so the codex active_repo_surface staleness classification holds (it was lost when AGENTS.md became generated). No change to the staleness classifier or authority-marker set; AGENTS.md remains a generated projection consuming canonical authority. .claude-plugin/plugin.json is now committed (un-ignored) so the marketplace manifest ships with the repo. -->

<!-- reviewed 2026-06-26: migration 128 dead-tables removal — no content changes required -->

<!-- reviewed 2026-06-27: Wave 1 migration 130 — module_contracts.py: removed artifact_records from telemetry module owned_tables (table dropped in migration 130; 0 rows, aspirational telemetry). No installed adapter runtime behavior, state, routing, or productization change. No semantic change required. -->

<!-- Last reviewed 2026-06-27 — Wave 2 substrate realignment (migration 131, worktree-agent-a910d590fedb5c672): the shared-intelligence authority write helpers for dormant tables are removed: core/shared_intelligence/authority.py drops record_adapter_result, record_artifact_authority, record_learning_event, record_hardening_candidate, record_model_provider_profile, record_shared_context_packet (and those table names leave REQUIRED_SHARED_INTELLIGENCE_TABLES). result_normalization.py is now a no-op stub (adapter_result_records dropped); context_packets.py no longer persists shared_context_packets (all callers were persist=False). Adapter-projection boundary is unchanged — adapter_authority_profiles / capability_route_records / policy_decision_records remain the live authority surfaces. -->

<!-- Last reviewed 2026-06-28 — Batch 1 canonical-first migration (migration 133): policy_decision_records dropped (persist=False dead gate — PLATFORM_HARDENING_TABLES now empty). compliance_review_flags and release_readiness_records dropped (persist=False dead gate via early-return in record_production_readiness_assessment — production_readiness_assessment_runs doesn't exist). guard_events dropped (all writers were test-only reachable). Adapter-projection boundary unchanged — adapter_authority_profiles / capability_route_records remain live authority. -->

<!-- Last reviewed 2026-07-04 — migration 139 (WO-AI-SPINE, AD-5): core/module_contracts.py telemetry module owned_tables list updated — outcome_records removed (dropped migration 139; pure duplication of execution_events dual-write, 0/2/0 production rows). Adapter-projection boundary unchanged — adapter_authority_profiles / capability_route_records remain live authority. -->

<!-- Reviewed 2026-07-05 — WO 6d978483 (PEP 585/604 modernization [2/2]): source files in this domain received mechanical type-annotation modernization only (PEP 585 builtin generics, PEP 604 unions, datetime.UTC) via ruff UP safe autofixes. No contract, behavior, schema, routing, API-shape, or CLI-surface change — reviewed, no doc content change needed. -->
