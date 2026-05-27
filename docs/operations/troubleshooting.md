# Troubleshooting

This guide covers installed Dream Studio behavior for local users and adapter
operators. It avoids cleanup instructions that delete unknown files or mutate
live SQLite state.

## Command Cannot Find State

Symptom: `ds router` or `ds adapters` reports that SQLite authority is missing.

Check:

- Confirm `--home` or `DREAM_STUDIO_HOME` points at the intended Dream Studio
  home.
- Run `ds validate` with the same `--source-root` and `--home`.
- For rehearsal use, run `ds install --rehearsal --home <temp-home>` or
  `ds acceptance --home <temp-home>`.

Do not copy files from another runtime home unless a restore plan has been
approved.

## Current Directory Assumptions

Symptom: a command only works from the Dream Studio repo.

Check:

- Use `--source-root <dream-studio-source>` explicitly.
- Use `--home <dream-studio-home>` explicitly for installed or rehearsal state.
- On Windows, prefer the plain-command launcher `ds.cmd`, or run
  `ds install-command --execute` to create user-local `ds.cmd` and `ds.ps1`
  launchers in a PATH directory such as `%USERPROFILE%\.local\bin`.
- For packaged installs, verify `DREAM_STUDIO_SOURCE_ROOT` and
  `DREAM_STUDIO_HOME`.

Commands are expected to work from outside the repo.

Use `ds version` to confirm the source/runtime resolver, `ds doctor` for
read-only health checks, and `ds repair` for a non-mutating repair plan. These
commands do not perform cleanup, live SQLite writes, or destructive repair.

## Legacy Install Detected

Symptom: a user previously installed Dream Studio from an old checkout, or
`ds update-check` reports legacy install metadata.

Check:

- Run `ds install --check-legacy --home <dream-studio-home>`.
- Run `ds migrate-legacy --dry-run --home <dream-studio-home>` to review the
  exact backup path, planned writes, compatible SQLite migration scope, adapter
  repair scope, and rollback instructions.
- Use `ds repair-adapters` only for Dream-Studio-owned launchers and adapter
  hook paths.
- Use `ds rollback-check --backup-path <backup>` before any restore decision.

Do not `git pull` the old repo into the new clean repo. Do not merge unrelated
Git histories. Do not copy legacy Work Orders, handoffs, reports, evidence
folders, caches, logs, prompts, or audit clutter into the fresh active runtime.
Do not delete old source/runtime backups without explicit approval.

## Unknown Module Profile

Symptom: install or acceptance reports an unknown profile.

Check `ds modules` for the supported profile ids:

- `core`
- `analytics_only`
- `security_only`
- `token_only`
- `telemetry_only`
- `dashboard_only`
- `adapter_router_only`
- `shared_intelligence_only`
- `full`

Do not edit runtime config by hand to invent a profile.

If a module exists in Contract Atlas but not in `ds modules`, check
`core.module_contracts`: module contracts describe boundaries, while installed
profiles describe selectable runtime packages.

## Dashboard Is Empty

Symptom: dashboard routes are available but show no facts.

This can be valid. Dream Studio uses honest empty states when selected modules
are installed but no runtime facts, telemetry, or readiness records exist yet.
Run `ds validate`, `ds modules`, and `ds contract-atlas` to confirm the runtime
surface is available. Run `ds contract-atlas-refresh` without `--execute` to
preview sanitized export and docs/PRD/README freshness without writing files.

## Dashboard Does Not Open

Symptom: `ds dashboard` reports readiness, but no browser opens and no server
starts.

This is expected. `ds dashboard` is the safe status-only default. Use one of
the explicit modes:

- `ds dashboard --status` reports readiness only.
- `ds dashboard --serve` starts the local dashboard server.
- `ds dashboard --open` starts or reuses the server and opens a browser.
- `ds dashboard --check` validates `/dashboard` and `/api/health` on a running
  server.

If `--check` fails, start the server with `ds dashboard --serve` in a separate
terminal and rerun the check with the same `--source-root`, `--home`, `--host`,
and `--port` values. Dashboard serving should not bootstrap, migrate, backfill,
clean, or destructively mutate live SQLite state.

## Expert Workflow Catalog Is Empty Or Missing

Symptom: `/api/shared-intelligence/expert-workflows` is unavailable or does not
list the expected expert workflow contracts.

Check:

- Run `ds contract-atlas` and confirm `expert_workflow_system` has
  `validation_status: pass`.
- Run `python -m pytest tests/unit/test_expert_workflow_catalog.py -q` from the
  source checkout.
- Confirm the installed source root points at a checkout that contains
  `core/shared_intelligence/expert_workflows.py`.

Do not create duplicate skill folders to make the route pass. The route should
map to existing skill/workflow owners and report missing evidence honestly.

## Adapter Is Unsupported Or Unproven

Symptom: an AI tool is classified as `context_packet_only` or
`not_proven_in_local_runtime`.

Use `ds context-packet --adapter <adapter>` for fallback context. Do not mark an
adapter as proven until live consumption evidence exists. Private model memory
is never Dream Studio authority.

## Analytics-Only Has No Hooks Or Agents

This is expected. `analytics_only` intentionally works without hooks, agents,
workflows, Claude, Codex, repo mutation, or Docker. If a command asks for those
dependencies in analytics-only mode, treat it as a product boundary bug.

## External Project Stays Paused

This is expected unless the current operator decision explicitly selects a
target and read-only scope. External targets such as DreamySuite, Bill Stack,
and TORII should not be read, scanned, validated, mutated, committed, pushed, or
deployed from stale route state. Use the external project validation pipeline to
plan target selection, dirty-state classification, validation profile, and Work
Order evidence before any target access.

## Docker Profile Is Unavailable

This is expected on local-first installs. Docker is optional and does not block
core, analytics-only, security-only, dashboard-only, shared-intelligence-only,
adapter-router-only, or full local operation. Do not start or build containers
while troubleshooting unless a current operator decision approves Docker
runtime validation.

## Analytics Import Shows No Data

`ds analytics-ingest --file <payload>` is a dry run. Add `--execute` only when
you intend to write normalized records to the selected SQLite authority. Verify
the same `--home` is used for ingest and dashboard/API checks.

If a payload omits a section, Dream Studio should show an honest empty state
for that section. Do not create placeholder projects, fake dependency edges,
fake costs, or synthetic findings to make a dashboard look populated.

## Restore Or Uninstall Requested

Use `ds restore-check` or `ds uninstall-check` first. These commands inspect the
selected local runtime home and do not restore or delete data. Live restore,
update, uninstall, cleanup, or deletion needs a separate approved scope.

## Secrets And Auth Files

Do not inspect or print secrets, auth tokens, cookies, private keys, or provider
credentials while troubleshooting. If a path looks like an auth store, classify
it as sensitive and route to operator review.

## AI Usage Cost Looks Unknown

This can be correct. Dream Studio records tokens and operational outcomes for
AI adapters, but it does not convert subscription-plan usage into API-dollar
costs. Check `ds router`, `ds adapters`, or
`/api/shared-intelligence/ai-usage-accounting` for the adapter billing mode,
token visibility, cost visibility, usage source, cost source, and confidence.

Only token-metered/API-metered/credit-metered usage with source-backed cost
metadata, or an explicit subscription allocation profile, should display a
reportable cost. Otherwise the dashboard should say `unknown`.

## Task Attribution Looks Incomplete

This can be correct when work was imported, untracked, or not routed through
Dream Studio. Check `/api/shared-intelligence/task-attribution` or the Project
Details `recent_attributed_work` section. Unknown model/provider values,
unavailable files or commands, uncertain validation, and
`manual_review_required` outcomes should remain visible instead of being
filled with guesses.

## Career Ops Is Disabled

This is expected unless the operator explicitly enables the private module.
Career profiles, resumes, applications, browser automation evidence, and
career scorecards should not appear in public exports or demo packets. If they
do, treat it as a publication-boundary bug.

## Scoped Agent Context Looks Too Small

This is expected. Scoped agents receive only task-required context. They should
not receive full conversation history, secrets, all Work Orders, all user
memories, unrelated project details, raw local evidence, or career-private data
unless that data class is explicitly enabled and scoped.

## GitHub Repo Intake Blocks Adoption

This is expected when license, attribution, security, maintenance, or overlap
evidence is missing. The workflow should route unclear licensing to legal
review and unclear security/supply-chain posture to security review. It should
not copy code, add dependencies, fork/vendor, or mutate an external repository
without explicit approval.

## Final Closeout Blocks

Final installed-platform closeout requires release gate evidence, docs drift
evidence, command-surface evidence, adapter status evidence, long-run cycle
evidence, publication-boundary evidence, and a live SQLite hash guard. A missing
evidence ref should remain a blocker instead of being normalized into a pass.

## Project Continuation Lacks PRD Context

Check `/api/shared-intelligence/prd-authority` and Project Details. A safe
continuation packet should include the current PRD version, milestone, active
Work Order, assumptions, known unknowns, relevant change orders, validation
expectations, and stop gates. If those are missing, formalize or review PRD
authority before continuing implementation.

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
<!-- Last reviewed 2026-05-20 — B.3: `ds workflow run pre-push --non-interactive` dispatches to `core.gates.pre_push.run_pre_push_gates()` instead of the model-driven workflow engine; new `ClaudeCodeInstaller.git_repo_root` parameter is opt-in so tests do not write to the operators .git/hooks/. CLI passes cwd when .git/ is present. No policy or contract change here. -->

<!-- Last reviewed 2026-05-21 — Platform profile troubleshooting added: if `ds doctor` reports shell-incorrect command hints or `~/.dream-studio/state/platform.json` is missing, re-run `ds doctor` to redetect and overwrite the profile. Override path via `DS_PLATFORM_PROFILE_PATH` for test or rehearsal environments. The profile is not SQLite authority; corruption or deletion is non-destructive and self-healing on the next `ds doctor` run. -->

<!-- Last reviewed 2026-05-21 — TA0 SDLC entity creation events: interfaces/cli/ds.py change in this PR is a CLI handler refactor only. _project_register now delegates to core.projects.mutations.register_project() instead of containing an inline INSERT. This aligns the CLI with the A2 refactor pattern already applied to all other project/milestone/work-order handlers. No new CLI surface, no new permissions, no installer change, no runtime path change, no adapter boundary change. No policy or contract change in this doc. -->

<!-- Last reviewed: TA2 (2026-05-22) — no structural change required for this workstream -->

<!-- Last reviewed 2026-05-22 — TA3 reviewed; no changes required for this doc. -->

<!-- Last reviewed 2026-05-22 — Phase 18.1.5: projection runner troubleshooting: if `ds projection daemon status` shows a stale PID (process no longer running), use `ds projection daemon stop` to clear it. If projection_dead_letter accumulates, use `ds projection dead-letter list` to inspect and `ds projection dead-letter retry <event_id>` to re-queue after the root cause is fixed. Dead-letter events do not block the daemon — the runner continues processing other events while dead-lettered events await manual review. Use `ds projection rebuild <name>` to replay all canonical events into an L3 table after a schema fix. -->


<!-- Last reviewed 2026-05-23 -- Phase 18.1.7: ds_* project-spine tables renamed to business_* via migration 070. No policy or boundary change in this doc; runtime table names updated. -->


<!-- Last reviewed 2026-05-24 — Phase 18.1.13: ds validate and ds doctor --help text updated to explicitly identify each command's health-check plane. ds validate description now reads: DB authority plane (schema version, migrations, module profiles). ds doctor description now reads: Claude Code integration plane (skills, agents, hooks, routing, version). Each help text cross-references the other command. README.md health-checks section expanded; docs/operations/fresh-install-validation.md updated to require both commands. No runtime behavior change. No new CLI surface. No policy or contract change in this doc. -->

<!-- Last reviewed 2026-05-26 — Phase 18.1.15b: ds.py updated to read skip_hook_install from config.json in _integrate_dispatch. No changes to the installed runtime contract, adapter routing, or global command surface described in this doc. -->

<!-- Last reviewed 2026-05-27 — Phase 18.2.5: ds.py gains --include-deleted flag on ds project list subcommand to surface soft-deleted projects. No changes to installed runtime paths, adapter routing contracts, global command surface, productization lifecycle, or platform hardening policy described in this doc. -->
