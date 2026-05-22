# Database Guide

Dream Studio uses SQLite as the local structured authority for operational intelligence. The public repo contains schema migrations, bootstrap code, read models, tests, and docs. The operator's live database is private runtime state.

## Paths

| Path | Meaning | Git policy |
| --- | --- | --- |
| `core/event_store/migrations/` | Repo-backed schema migrations | Tracked |
| `core/config/sqlite_bootstrap.py` | Bootstrap and migration application | Tracked |
| `core/config/database.py` | Canonical DB path resolver and environment override behavior | Tracked |
| `~/.dream-studio/state/studio.db` | Operator-local live DB | Ignored/private |
| `*.db`, `*.sqlite*`, `*.db-wal`, `*.db-shm` | Runtime DB files | Ignored/private |

## Authority Areas

Dream Studio's SQLite authority covers:

- project, session, milestone, task, and Work Order state;
- route decisions and approval state;
- hook, tool, skill, token, validation, security, workflow, research, decision, and outcome telemetry;
- dashboard attention items and read-model inputs;
- shared intelligence records including adapters, context packets, normalized results, model/provider metadata, learning events, hardening candidates, and evaluation records;
- secure production readiness assessments, control applicability, findings, remediation Work Order links, project health/readiness scorecards, release readiness records, and compliance/legal review flags;
- release/cutover evidence summaries where safe.

Current Career Ops, Capability Center, scoped-agent, and GitHub repo intake
authority lives in migration 044:

- `career_profiles` and related `career_*` tables for opt-in private career
  profiles, fields, role targets, resume/cover-letter variants, portfolio
  artifacts, case studies, job opportunities, applications, application events,
  field mappings, browser automation runs, interview stories, evidence refs,
  and scorecards;
- `capability_center_records` for optional persisted capability metadata, with
  dashboard summaries also reading current invocation and hardening records;
- `agent_registry_records`, `agent_context_scope_policies`,
  `workflow_agent_skill_mappings`, and `agent_result_records` for scoped worker
  declarations and normalized results;
- `github_repo_*` tables for evidence-backed repository evaluations, license,
  security, dependency, integration, pattern, adoption, and attribution records.

Career data is private by default and excluded from public exports unless
explicitly redacted and approved. GitHub repo intake records do not authorize
copying code, adding dependencies, forking, vendoring, or mutating external
projects.

Current AI usage accounting authority lives in:

- `token_usage_records` for token telemetry with billing, token visibility,
  cost visibility, usage source, cost source, and confidence metadata;
- `ai_adapter_accounting_profiles` for operator-declared adapter billing modes
  such as Claude Code subscription, Claude API token-metered, Codex ChatGPT
  plan, Codex token-metered/flexible, local model, and unknown/custom;
- `ai_usage_operational_records` for operational value telemetry such as run
  count, project/milestone/task/Work Order context, files touched, commands
  run, validation outcome, PR/result outcome, rework, duration, and evidence.
- `task_attribution_records` for execution-unit attribution: which adapter,
  model/provider where known, skills/workflows, tools/hooks, files, commands,
  validations, outcome, rework state, commit/PR/result refs, and
  security/readiness impact belong to a meaningful task or Work Order.

Tokens are usage telemetry. They are not dollars unless the adapter billing
mode and source metadata explicitly make cost reportable. Plan/subscription
usage preserves observed tokens where available and shows cost as unknown
unless an explicit allocation profile exists. Reconciled legacy token rows must
carry `source_refs_json` and `evidence_refs_json` so token analytics can use
current authority without restoring legacy `canonical_events` as an active
source.

Task attribution links usage, adapter results, validation, security/readiness,
and Work Order facts without becoming token/cost authority. Unknown
model/provider values remain `unknown`; unavailable file or command data remains
`unavailable`; imported or untracked work must be classified instead of
overclaimed.

Dashboard launch commands must use the resolved SQLite path through
`DREAM_STUDIO_DB_PATH` and `DREAM_STUDIO_HOME` instead of assuming the caller's
current directory or default home. Serving or checking the dashboard must not
bootstrap, migrate, backfill, clean, or destructively mutate the live database.

Platform hardening authority lives in migration
`046_platform_hardening_authority.sql` and covers:

- `skill_evaluation_runs`
- `policy_decision_records`
- `connector_ingestion_runs`
- `privacy_redaction_export_records`
- `local_watch_schedule_records`
- `team_rollup_records`
- `installer_distribution_checks`
- `demo_case_study_packets`

These records make skill evaluation, permission decisions, connector imports,
privacy/export checks, opt-in watchers, sanitized team rollups,
installer/distribution checks, and demo/case-study packets queryable without
promoting local files to authority.

PRD lifecycle authority lives in migration
`047_prd_lifecycle_authority.sql` and covers:

- `project_intake_records` and `project_intake_questions` for adaptive
  new-project and import-existing-project intake;
- `project_assumption_records` for explicit assumptions and operator
  confirmation state;
- `prd_version_records` for PRD lifecycle state, confidence, version lineage,
  source refs, evidence refs, known unknowns, and current-version selection;
- `project_milestone_records` for ordered milestone authority, stage gates,
  validation expectations, security/readiness checks, evidence requirements,
  and adapter context requirements;
- `project_work_order_authority_records` for Work Order purpose, scope,
  approved surfaces, stop gates, verdict taxonomy, route expectations, and
  rollback strategy;
- `project_change_order_records` and `prd_amendment_records` for material and
  lightweight PRD changes without silently overwriting current authority;
- `prd_route_reconciliation_records` for planned-vs-actual milestone, release,
  or project closeout reconciliation.

`prd_documents` remains a compatibility/list surface. It is not sufficient as
the only PRD authority for in-flight continuation because it lacks change-order
lineage, milestone impact, route reconciliation, and adapter context-scoping
fields. PRD files, when generated, are exports and must not become a competing
source of truth.

Legacy install upgrades do not add legacy tables to the current schema. The
upgrade flow creates a fresh current SQLite database through the normal
migration runner, then imports only compatible rows into tables that already
exist in the current schema. Legacy-only tables, FTS/shadow tables,
`canonical_events`, backup/import-map tables, and old file-sprawl remain in the
backup/manual-review set unless a future additive migration gives them current
authority semantics.
installer/distribution checks, and demo/case-study packets measurable without
replacing validation, Work Order, security, analytics, or adapter authority.

## Runtime Rules

- Normal runtime uses the canonical path resolver.
- Tests that write must use temp or injected DB paths.
- Live DB migration requires explicit approval, fresh backup, backup verification, and rollback instructions.
- Destructive migration, DB record deletion, retention cleanup, compaction, and archive execution are separate approval boundaries.
- Public docs may describe schema concepts but must not include private rows, raw logs, operator decisions, local evidence contents, or DB backups.

## Read Models

Telemetry read models aggregate structured state into dashboard-consumable views. They are derived views and must expose or imply:

- `derived_view: true`
- `primary_authority: false`
- `routing_authority: false`
- source tables and freshness metadata
- module availability and empty-state behavior

## Publication Boundary

Never commit live DB files, backups, WAL/SHM files, dumps, raw telemetry, cutover evidence, cleanup manifests, or local audit trails. Use sanitized fixtures and synthetic examples for public tests and demos.

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

<!-- Last reviewed 2026-05-21 — Platform profile clarification: `~/.dream-studio/state/platform.json` is NOT a SQLite table and is NOT managed by the migration runner. It is a flat JSON file written by `core.config.platform.ensure_platform_recorded()` during install and `ds doctor`. It lives alongside `studio.db` in the `state/` directory but is outside SQLite authority. Override via `DS_PLATFORM_PROFILE_PATH`. No migration required. -->

<!-- Last reviewed 2026-05-21 — TA0 SDLC entity creation events: migration 061 added. Migration 061 (`061_backfill_sdlc_creation_events.sql`) backfills synthetic `project.created`, `milestone.created`, and `work_order.created` events into canonical_events for rows that predate event emission. Uses deterministic `backfill-<type>-<id>` event_ids and `INSERT OR IGNORE` for idempotency. attribution_status = 'backfill' marks them as synthetic. Forward emission added to `register_project`, `create_milestone`, and `create_work_order`. No schema DDL change (data-only migration). No policy change here. -->

<!-- Last reviewed 2026-05-21 — TA0b dual event store reconciliation: three new migrations applied. Migration 058 is documentation-only (registers domain field validation requirement; no schema change). Migration 059 adds `_built_from_event_id TEXT` column and `idx_execution_events_canonical_link` index to `execution_events`, establishing the projection link from execution_events rows back to their source canonical_events row. Migration 060 backfills `trace.domain` on existing canonical_events rows ('telemetry' for session/prompt/tool/token/execution event types; 'sdlc' for work_order/task/milestone/project/skill event types) and backfills `_built_from_event_id` on existing execution_events rows that can be matched by event_type. The `execution_events` table is now a projection of `canonical_events`; direct writes to execution_events outside the projection path are deprecated. `canonical_events` is the authoritative event store. -->

<!-- Last reviewed 2026-05-22 — TA0c activity_log retirement: migrations 062 and 063 applied. Migration 062 is destructive/structural: relaxes `activity_id` from NOT NULL to nullable in 7 child tables (hook_executions, hook_findings, sec_sarif_findings, sec_manual_reviews, sec_cve_matches, sec_hook_checks, adapter_executions) via table-recreation pattern; permanently retires `vw_graph_edges` and `vw_component_stats` (both broken since initial commit 790965e — wrong column names and non-existent table refs); rewrites `vw_activity_timeline` to query `canonical_events` and `vw_guardrail_decisions` to query `guardrail_decisions` directly; backfills 159 historical `activity_log` rows into `canonical_events` via `INSERT OR IGNORE` with deterministic `backfill-activity-log-<id>` event_ids and `trace.attribution_status = 'backfill'`. Migration 063 drops the `activity_log` table and its 4 indexes. `canonical_events` is now the sole event store. All read/write sites in production code have been migrated off `activity_log`. -->

