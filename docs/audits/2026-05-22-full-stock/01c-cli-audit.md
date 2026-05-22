# Pass 1c — CLI Audit
*Phase 1 analysis | 2026-05-22*
*Source: Phase 0c Gap 2 handler mapping + spot-check reads*

---

## Stated Architectural Intents

| # | Intent |
|---|--------|
| 1 | **SQLite-first authority** — all runtime STATE must be SQLite-backed. File-based state is v1 rot. |
| 2 | **Security audit during brownfield onboarding** — security skills run during project intake, findings stored in SQLite. |
| 3 | **Security audit as SDLC lifecycle gate** — greenfield projects must pass security audit before going live. |
| 4 | **Canonical events as the spine** — all state changes flow through canonical_events. Direct table writes without event emission are anomalies. |
| 5 | **Marker file authority for attribution** — `.dream-studio-project` markers are identity source; `ds_projects` is metadata storage. |

---

## Command Groups

### 1. Project Management Group (9 commands)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 4 (Events) | Intent 5 (Marker) | Notes |
|---------|---------|---------|--------|-------------------|-------------------|-------------------|-------|
| `ds project register` | `ds.py:_project_register` → `core.projects.mutations.register_project` | Register a new project | active | SQLite: `ds_projects` INSERT | YES: `project.created` | YES: writes `.dream-studio-project` | Only event-emitting mutator in group that also writes marker |
| `ds project list` | `ds.py:_project_list` → `core.projects.queries.get_project_list` | List all registered projects | active | SQLite: `ds_projects` SELECT | NO | N/A | Read-only; no event needed |
| `ds project status` | `ds.py:_project_status` → `core.projects.queries.get_project_status` | Show project summary counts | active | SQLite: `ds_projects`, `ds_milestones`, `ds_work_orders` | NO | NO | Read-only |
| `ds project next` | `ds.py:_project_next` → `core.projects.queries.get_next_work_order` | Get next open work order | active | SQLite: `ds_work_orders` SELECT | NO | NO | Read-only |
| `ds project set-active` | `ds.py:_project_set_active` → `core.projects.mutations.set_active_project` | Set a project as active | active | SQLite: `ds_projects` UPDATE (status swap) | NO | NO | State mutation without event — gaps Intent 4 |
| `ds project deactivate` | `ds.py:_project_deactivate` → `core.projects.mutations.deactivate_project` | Pause an active project | active | SQLite: `ds_projects` UPDATE | NO | NO | State mutation without event — gaps Intent 4 |
| `ds project start` | `ds.py:_project_start` → `core.projects.start.start_project` | Load project context for operator | active | SQLite: reads 6 tables, writes `ds_projects` + `ds_work_orders` | YES: `work_order.started` | NO | Also writes `context.md` to `.planning/` — file-based side-effect |
| `ds project delete` | `ds.py:_project_delete` → `core.projects.mutations.delete_project` | Delete project and all dependents | active | SQLite: reads + deletes 5 tables | YES: `project.deleted`, `task.deleted` per task | NO | Emits per-task deletion events; cascade through SQLite |
| `ds project state` | `ds.py:_project_state` → `core.projects.queries.get_project_state` | Full active project summary | active | SQLite: reads 5 tables | NO | NO | Also checks `.planning/` gate files on filesystem — partial file dependency |

**Group summary:** 6 of 9 commands use SQLite correctly. `project start` and `project state` have file-based side-effects (`.planning/context.md` write and `.planning/` gate file reads). `project set-active` and `project deactivate` are silent mutators — they write SQLite but emit no canonical events.

---

### 2. Work Order Group (8 commands)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 4 (Events) | Notes |
|---------|---------|---------|--------|-------------------|-------------------|-------|
| `ds work-order start` | `ds.py:_work_order_start` → `core.work_orders.start` | Load WO brief for operator | active | SQLite: reads 6 tables, writes `ds_work_orders` UPDATE | YES: `work_order.started` | Also writes `context.md` to `.planning/`; reads marker file |
| `ds work-order list` | `ds.py:_work_order_list` → `core.work_orders.queries.list_work_orders` | List work orders | active | SQLite: `ds_work_orders` SELECT | NO | Read-only |
| `ds work-order close` | `ds.py:_work_order_close` → `core.work_orders.close.close_work_order` | Close WO with gate check | active | SQLite: reads 4 tables, writes `ds_work_orders` UPDATE | YES: `work_order.closed`; `gate.bypassed` if `--force` | Checks `.planning/` gate artifact files — file dependency for gate logic |
| `ds work-order block` | `ds.py:_work_order_block` → `core.work_orders.mutations.block_work_order` | Block WO with reason | active | SQLite: `ds_work_orders` UPDATE | YES: `work_order.blocked` | Full SQLite+event chain |
| `ds work-order unblock` | `ds.py:_work_order_unblock` → `core.work_orders.mutations.unblock_work_order` | Unblock a blocked WO | active | SQLite: `ds_work_orders` UPDATE | NO | Unblock emits no event — asymmetric with `block` |
| `ds work-order task-done` | `ds.py:_work_order_task_done` → `core.work_orders.mutations.mark_task_done` | Mark task complete | active | SQLite: `ds_tasks` UPDATE | YES: `task.completed` | Also updates `context.md` in `.planning/`; may call `clear_active_task()` which clears `active_task.json` |
| `ds work-order tasks` | `ds.py:_work_order_tasks` → `core.work_orders.queries.list_tasks` | List tasks for a WO | active | SQLite: `ds_work_orders` + `ds_tasks` SELECT | NO | Read-only |
| `ds work-order add-tasks` | `ds.py:_work_order_add_tasks` → `core.work_orders.mutations.add_tasks_from_file` | Add tasks from markdown file | active | SQLite: `ds_tasks` INSERT per task | YES: `task.created` per task | Reads `tasks.md` from disk — intentional input path, not state |

**Group summary:** 5 of 8 commands emit canonical events. Gaps: `work-order list`, `work-order tasks` (read-only, acceptable), and `work-order unblock` (state change, no event — asymmetric with `work-order block`). Gate logic in `work-order close` depends on `.planning/` artifact files rather than SQLite.

---

### 3. Milestone Group (3 commands)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 4 (Events) | Notes |
|---------|---------|---------|--------|-------------------|-------------------|-------|
| `ds milestone close` | `ds.py:_milestone_close` → `core.milestones.close.close_milestone` | Close milestone with gate check | active | SQLite: `ds_milestones`, `ds_work_orders` UPDATE | YES: `milestone.completed`; `gate.bypassed` if `--force` | Checks `.planning/` gate files — same pattern as WO close |
| `ds milestone list` | `ds.py:_milestone_list` → `core.milestones.queries.list_milestones` | List milestones | active | SQLite: `ds_milestones`, `ds_work_orders` COUNT | NO | Read-only |
| `ds milestone status` | `ds.py:_milestone_status` → `core.milestones.queries.get_milestone_status` | Show milestone detail | active | SQLite: `ds_milestones`, `ds_work_orders` SELECT | NO | Also checks `.planning/` gate files |

**Group summary:** Only `milestone close` emits an event. Gate evaluation for both `close` and `status` depends on `.planning/` gate artifact files.

---

### 4. Task Group (3 commands)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 4 (Events) | Notes |
|---------|---------|---------|--------|-------------------|-------------------|-------|
| `ds task set-active` | `ds.py:_task_set_active` → `core.sdlc.active_task.set_active_task` | Set current operator task pointer | active | SQLite READ only (resolves task chain); writes `active_task.json` | NO | **File-based write violation.** SQLite is read to resolve, but result persisted to file |
| `ds task active` | `ds.py:_task_get_active` → `core.sdlc.active_task.get_active_task` | Show current active task | active | None — reads `active_task.json` only | NO | **Pure file-read.** Zero DB involvement on query path |
| `ds task clear-active` | `ds.py:_task_clear_active` → `core.sdlc.active_task.clear_active_task` | Clear current task pointer | active | None — deletes `active_task.json` | NO | **Pure file-delete.** Zero DB involvement |

**Group summary:** Flagged file-based violation. See Special Focus section below.

---

### 5. Design Brief Group (5 commands)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 4 (Events) | Notes |
|---------|---------|---------|--------|-------------------|-------------------|-------|
| `ds design-brief show` | `ds.py:_design_brief_show` → `core.design_briefs.queries.get_design_brief` | Show brief for project | active | SQLite: `ds_design_briefs` SELECT | NO | Read-only |
| `ds design-brief create` | `ds.py:_design_brief_create` → `core.design_briefs.mutations.create_design_brief` | Create draft brief | active | SQLite: `ds_design_briefs` INSERT | NO | No existence guard before insert; no event emitted |
| `ds design-brief lock` | `ds.py:_design_brief_lock` → `core.design_briefs.mutations.lock_design_brief` | Lock brief (gate transition) | active | SQLite: `ds_design_briefs` UPDATE | NO | State transition to `locked` without event — significant for Intent 4 |
| `ds design-brief update` | `ds.py:_design_brief_update` → `core.design_briefs.mutations.update_design_brief_field` | Update single field | active | SQLite: `ds_design_briefs` UPDATE | NO | Guards: must be in `draft` status |
| `ds design-brief set-system` | `ds.py:_design_brief_set_system` → `core.design_briefs.mutations.set_design_system` | Set design system | active | SQLite: `ds_design_briefs` UPDATE | NO | Constrained to 5 allowed values |

**Group summary:** All 5 commands use SQLite exclusively. Zero canonical events emitted by any design-brief command. The `lock` transition is a meaningful state gate but leaves no event trace.

---

### 6. Skill Group (2 commands)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 4 (Events) | Intent 5 (Marker) | Notes |
|---------|---------|---------|--------|-------------------|-------------------|-------------------|-------|
| `ds skill invoke` | `ds.py:_skill_invoke` → `core.skills.invocation` | Invoke a skill | active | SQLite: reads `ds_work_orders`, `ds_design_briefs`; writes `ds_design_briefs` (website:discover) | YES: `skill.invoked` (best-effort) | YES: reads `.dream-studio-project` | Writes gate artifact files to `.planning/`; event is best-effort not guaranteed |
| `ds skill list` | `ds.py:_skill_list` → `core.skills.queries.list_skills` | List available skills | active | None — reads `canonical/skills/` filesystem only | NO | NO | Pure filesystem read; no DB involvement |

**Group summary:** `skill invoke` is the primary hook between CLI and the skill system. It emits `skill.invoked` as best-effort. Gate artifacts (design-critique.md, security-scan.md) written to `.planning/` are read by WO/milestone close gates.

---

### 7. Workflow Group (5 commands)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 4 (Events) | Notes |
|---------|---------|---------|--------|-------------------|-------------------|-------|
| `ds workflow start` | `ds_workflow.py:cmd_start` → `control.execution.workflow.state.cmd_start` | Start a named workflow | active | None — reads YAML, writes `workflows.json` | NO (spool events per node, not at start) | **File-based write violation.** See Special Focus section |
| `ds workflow status` | `ds_workflow.py:cmd_status` → `control.execution.workflow.state.cmd_status` | Show active workflow status | active | None — reads `workflows.json` | NO | Pure file-read |
| `ds workflow list` | `ds_workflow.py:cmd_list` → `control.execution.workflow.state.cmd_status(key=None)` | List all active workflows | active | None — reads `workflows.json` | NO | Pure file-read |
| `ds workflow advance` | `ds_workflow.py:cmd_advance` → `WorkflowRunner.advance` | Advance a workflow one node | active | None direct — may write via spool on completion | PARTIAL: spool event per node via `spool.writer.write_event` | Spool events are queued, not immediately canonical |
| `ds workflow run` | `ds_workflow.py:cmd_run` → `WorkflowRunner.run` | Run workflow to completion | active | None direct; pre-push path reads source | PARTIAL: spool events per wave | On completion, `_try_archive_and_prune` writes `raw_workflow_runs` + `raw_workflow_nodes`, then prunes from `workflows.json` |

**Group summary:** Flagged file-based violation. See Special Focus section below.

---

### 8. Spool Group (1 command)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 4 (Events) | Notes |
|---------|---------|---------|--------|-------------------|-------------------|-------|
| `ds spool ingest` | `ds_spool.py:cmd_ingest` → `spool.ingestor.ingest_pending` | Consume pending spool events into DB | active | SQLite: reads `canonical_events` for dedup; writes `canonical_events` | Consumer role — not an emitter | Also writes `reg_gotchas`, `raw_approaches`, `ds_documents`, `ds_technology_signals` via session harvester path |

**Group summary:** This is the ingestion boundary — the point where file-queued events become SQLite records. Operates correctly per intent.

---

### 9. Memory Group (2 commands)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 4 (Events) | Notes |
|---------|---------|---------|--------|-------------------|-------------------|-------|
| `ds memory ingest` | `ds_memory.py:cmd_memory_ingest` → `run_memory_ingest` | Ingest handoffs/gotchas from filesystem | active | SQLite: reads + writes `reg_gotchas`, `ds_documents`, `reg_projects` | NO | Reads `~/.sessions/`, `~/.planning/` tree — intentional ingestion from external source |
| `ds memory ingest-sessions` | `ds_memory.py:cmd_memory_ingest_sessions` → `SessionHarvester` | Harvest Claude session JSONL files | active | SQLite: reads + writes `reg_gotchas`, `raw_approaches`, `ds_documents`, `ds_technology_signals` | NO | Reads `~/.claude/projects/` JSONL files; interactive consent prompt |

**Group summary:** Both commands are ingest/ETL paths from external sources into SQLite. File reads here are intentional (source data, not state). Neither emits canonical events — the DB writes are direct. This is a partial gap for Intent 4 (ingest operations leave no event trace).

---

### 10. Diagnostics Group (2 commands)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 4 (Events) | Notes |
|---------|---------|---------|--------|-------------------|-------------------|-------|
| `ds diagnostics list` | `ds.py:_diagnostics_dispatch` branch `list` (inline) | List diagnostic log entries | active | None — reads `*.jsonl` files from `~/.dream-studio/state/diagnostics/` | NO | **File-based read violation.** See Special Focus section |
| `ds diagnostics clear` | `ds.py:_diagnostics_dispatch` branch `clear` (inline) | Clear diagnostic log entries | active | None — truncates `*.jsonl` files | NO | **File-based write violation.** |

**Group summary:** Flagged file-based violation. See Special Focus section below.

---

### 11. Integration Group (5 commands)

| Command | Handler | Purpose | Status | Intent 1 (SQLite) | Intent 2 (Security intake) | Intent 4 (Events) | Notes |
|---------|---------|---------|--------|-------------------|-----------------------------|-------------------|-------|
| `ds integrate detect` | `ds.py:_integrate_dispatch` → `integrations.detector.detect_all` | Detect installed AI tools | active | None — filesystem scan only | N/A | NO | Read-only filesystem probe |
| `ds integrate status` | `ds.py:_integrate_dispatch` → `integrations.health.doctor` per tool | Show integration health | active | None — reads `~/.claude/` config files | N/A | NO | Read-only |
| `ds integrate doctor` | `ds.py:_integrate_dispatch` → `integrations.health.doctor` | Diagnose integration issues | active | None — reads config roots | N/A | NO | Read-only |
| `ds integrate plan` | `ds.py:_integrate_dispatch` → `ClaudeCodeInstaller.plan` | Preview installation changes | active | None — dry-run only | N/A | NO | Reads `canonical/` + existing configs |
| `ds integrate install` | `ds.py:_integrate_dispatch` → `ClaudeCodeInstaller.install(mode)` | Install adapter surfaces | active | None — writes `~/.claude/` files | N/A | NO | Writes skills/, agents/, settings.json, CLAUDE.md; git pre-push hook if `--execute` |

**Group summary:** All 5 commands are filesystem-only. None touch SQLite, none emit events. Integration install is the adapter surface bootstrap operation. No security-intake hooks in this group.

---

### 12. Infrastructure Group (26 single-action commands)

These commands are top-level with no subcommands. Most are read-only health checks or operational utilities.

| Command | Handler | SQLite | Events | Notes |
|---------|---------|--------|--------|-------|
| `status` | `core.health.status.get_runtime_status` | No | No | Reads filesystem paths only |
| `version` | `core.health.version.get_version` | No | No | Reads VERSION file |
| `doctor` | `core.health.doctor.run_doctor_checks` | No | No | Reads `~/.claude/`, `~/.dream-studio/` |
| `repair` | inline `_repair_plan` | No | No | Calls doctor; planning-mode only |
| `update` | `ClaudeCodeInstaller.install` | No | No | Writes `~/.claude/` files |
| `validate` | `core.health.validate.run_validation` | No | No | Reads source tree |
| `contract-atlas` | `core.shared_intelligence.contract_atlas.build_contract_atlas(conn)` | YES: reads multiple registry tables | No | Read-only |
| `contract-atlas-refresh` | `core.shared_intelligence.contract_atlas_lifecycle.refresh_contract_atlas_exports(conn)` | YES: reads registry tables | No | Writes export files to `--output-dir` |
| `adapters` | `core.installed_runtime.adapter_router_status(conn)` | YES: reads adapter tables | No | Read-only |
| `router` | same as `adapters` | YES | No | Alias of `adapters` |
| `modules` | `core.module_profiles.module_profiles()` | No | No | Reads source tree YAML |
| `platform-hardening` | `core.shared_intelligence.platform_hardening.platform_hardening_summary(conn)` | YES: reads platform tables | No | Read-only |
| `policy` | `core.shared_intelligence.platform_hardening.evaluate_policy_decision()` | No | No | Stateless |
| `analytics-ingest` | `core.analytics_ingestion.ingest_analytics_payload(conn, payload)` | YES: reads + writes analytics tables | No | Reads JSON file; writes analytics tables without event |
| `install` | `core.installed_productization.first_run_setup()` | No | No | Writes `~/.dream-studio/`, `~/.claude/` |
| `install-command` | `core.installed_productization.install_global_command_surface()` | No | No | Writes launcher scripts |
| `acceptance` | `core.installed_productization.productization_acceptance_report()` | No | No | Reads rehearsal home |
| `backup` | `core.installed_productization.backup_runtime()` | No | No | Copies `~/.dream-studio/` |
| `restore-check` | `core.installed_productization.restore_runtime_check()` | No | No | Reads backup archive |
| `update-check` | `core.installed_productization.update_runtime_check()` | No | No | Reads VERSION + installed-version |
| `uninstall-check` | `core.installed_productization.uninstall_runtime_check()` | No | No | Scans install targets |
| `migrate-legacy` | `core.installed_productization.migrate_legacy_install()` | No | No | Moves legacy files |
| `repair-adapters` | `core.installed_productization.repair_adapter_surfaces()` | No | No | Writes adapter surface files |
| `rollback-check` | `core.installed_productization.rollback_runtime_check()` | No | No | Reads backup path |
| `context-packet` | `core.shared_intelligence.context_packets.generate_shared_context_packet(conn)` | YES: reads projects/work_orders/briefs | No | Preview only (`persist=False`) |
| `rehearsal-install` | `core.installed_runtime.bootstrap_rehearsal_runtime()` | No | No | Creates rehearsal dir tree |

**Group summary:** 7 of 26 infrastructure commands use SQLite (all read-only or analytics ingest). None emit canonical events. The infrastructure group is operational tooling; event emission would be inappropriate for most of these. The `analytics-ingest` command writes analytics tables directly without events — this is a mild Intent 4 gap.

---

### 13. Dashboard Group (4 sub-modes)

| Command | Handler | SQLite | Events | Notes |
|---------|---------|--------|--------|-------|
| `dashboard --status` | `ds.py:_dashboard_status` (inline) | No — checks `sqlite_path.exists()` only | No | Returns static capability dict |
| `dashboard --serve` | `ds.py:_dashboard_serve` (inline) | No | No | Spawns uvicorn as foreground process |
| `dashboard --open` | `ds.py:_dashboard_open` (inline) | No | No | Spawns uvicorn background + opens browser |
| `dashboard --check` | `ds.py:_dashboard_check` (inline) | No | No | HTTP probe to running server |

---

## Special Focus: File-Based Violations

### ds task commands — active_task.json

**File location:** `~/.dream-studio/state/active_task.json` (env-overridable via `DS_ACTIVE_TASK_PATH`)

**Schema of active_task.json:**
```json
{
  "task_id": "<uuid>",
  "work_order_id": "<uuid>",
  "milestone_id": "<uuid or empty>",
  "project_id": "<uuid>",
  "set_at": "<ISO timestamp>"
}
```

**Write path:** `core.sdlc.active_task.set_active_task(task_id)` — resolves the full SDLC chain from SQLite (`ds_tasks` JOIN `ds_work_orders`), then writes result to disk.

**Read path:** `core.sdlc.active_task.get_active_task()` — reads the JSON file directly, returns `None` if absent or corrupt. Zero SQLite involvement on read.

**Clear path:** `core.sdlc.active_task.clear_active_task()` — deletes the file. Zero SQLite involvement.

**Who reads it (beyond CLI):**
- `core.skills.invocation` — reads before skill invocation to attach task context
- `core.telemetry.token_capture` — reads to associate token usage with task
- `core.work_orders.mutations` — reads in `mark_task_done` to auto-clear if the completed task matches

**Assessment vs Intent 1:**
The file exists as a fast-path "current cursor" pointer. The authoritative task data is in `ds_tasks`. The issue is that the pointer itself is stateless from SQLite's perspective — if `active_task.json` is lost, deleted, or diverges from reality (e.g., task deleted from DB), the CLI has no SQLite fallback for "what's currently active."

**SQLite replacement candidate:** `ds_tasks` already has a `status` column. An `active` status value per project (or a separate `active_task_context` single-row table in studio.db) could replace this file. The env-override `DS_ACTIVE_TASK_PATH` suggests the design anticipated test isolation but not necessarily permanent file authority.

---

### ds workflow commands — workflows.json

**File location:** `~/.dream-studio/state/workflows.json` (via `core.config.paths.state_dir()`)
**Companion file:** `~/.dream-studio/state/workflow-checkpoint.json` (checkpoint tracking)

**Schema of workflows.json (inferred from state.py):**
```json
{
  "schema_version": 1,
  "active_workflows": {
    "<run_key>": {
      "workflow": "<name>",
      "yaml_path": "<path>",
      "status": "running|completed|aborted|...",
      "started": "<ISO>",
      "finished": "<ISO>",
      "nodes": {
        "<node_id>": {"status": "...", "output": "...", "duration_ms": ...}
      }
    }
  }
}
```

**Write path:** All workflow state mutations go through `control.execution.workflow.state` and `runner.py`, which call `_write_state(data)` — atomic JSON file write with a file lock.

**Archival path (on completion):** `state.py:_try_archive_and_prune()` calls `core.event_store.studio_db.archive_workflow()`, which writes to `raw_workflow_runs` + `raw_workflow_nodes` in SQLite, then removes the key from `workflows.json`. This is the point where file state becomes permanent DB record.

**`workflow_invocations` table status:**
The table exists and has 2 rows (both from `studio-onboard` workflow runs). However, `workflow_invocations` is **not populated by the CLI workflow commands directly**. It is populated by `core.telemetry.emitters.emit_workflow_invocation_record()` which is called by the telemetry layer, not by the CLI workflow runner. The CLI workflow runner writes to `raw_workflow_runs` via `archive_workflow()`. The `workflow_invocations` table is a separate telemetry record with richer metadata, not the primary completion record.

**Gap:** The workflow CLI is fully file-backed during execution. SQLite is only touched: (a) on completion via `archive_workflow` → `raw_workflow_runs`/`raw_workflow_nodes`, and (b) independently by the telemetry emitter layer. No event is emitted at workflow start. Spool events are written per-node during execution but only become canonical after `ds spool ingest` runs.

---

### ds diagnostics commands — .jsonl files

**File location:** `~/.dream-studio/state/diagnostics/` (env-overridable via `DS_DIAGNOSTICS_DIR`)

**File naming convention:** `<source-prefix>.jsonl` — the prefix is derived from the source identifier by replacing `_` with `-`. Example: `source='token_capture.handle'` → `token-capture.jsonl`.

**Implementation note:** The `diagnostics list` and `diagnostics clear` commands are implemented fully inline in `ds.py:_diagnostics_dispatch()` with no delegation to a core module. This is the only handler in `ds.py` with no core delegate function — the business logic lives directly in the CLI layer.

**What writes these files:** The `core.telemetry.diagnostics.write_diagnostic()` function appends structured JSONL entries. Callers are hook-level and telemetry modules that detect anomalies. The diagnostic system is explicitly "two-tier" and "best-effort" — designed to never raise exceptions.

**No `write_diagnostic` callers found in source scan:** The scan of the entire source tree found zero explicit `write_diagnostic(source="...")` call patterns. This suggests either: (a) the diagnostic write path uses a different calling convention, (b) callers are in hook dispatch code that wasn't matched by the pattern, or (c) the diagnostics system is infrastructure that was built but not yet fully wired to production callers.

**Assessment vs Intent 1:** This is an intentional design choice for a "last-resort" diagnostic stream that runs even when SQLite is unavailable or broken. However, the CLI commands that read and clear this data (`diagnostics list`, `diagnostics clear`) are purely file-based with no SQLite involvement — there is no mirroring, archival, or event emission for diagnostic entries. The data is ephemeral by design.

---

## Special Focus: Event Emission Map

### Commands that emit canonical events (via CanonicalEventEnvelope → spool)

| Command | Event Type(s) | Notes |
|---------|---------------|-------|
| `project register` | `project.created` | Guaranteed |
| `project start` | `work_order.started` | Guaranteed |
| `project delete` | `project.deleted`, `task.deleted` (per task) | Guaranteed |
| `work-order start` | `work_order.started` | Guaranteed |
| `work-order close` | `work_order.closed`; `gate.bypassed` if `--force` | Guaranteed |
| `work-order block` | `work_order.blocked` | Guaranteed |
| `work-order task-done` | `task.completed` | Guaranteed |
| `work-order add-tasks` | `task.created` (per task) | Guaranteed |
| `milestone close` | `milestone.completed`; `gate.bypassed` if `--force` | Guaranteed |
| `skill invoke` | `skill.invoked` | Best-effort only |
| `workflow advance` / `run` | spool events per node via `spool.writer.write_event` | Queued, not yet canonical until `spool ingest` |

### Commands that modify SQLite state WITHOUT emitting canonical events

| Command | State Change | Gap Severity |
|---------|--------------|--------------|
| `project set-active` | `ds_projects` status swap (active ↔ paused) | Medium — active project changes are operationally significant |
| `project deactivate` | `ds_projects` UPDATE status='paused' | Medium — same concern |
| `work-order unblock` | `ds_work_orders` status change blocked→in_progress | Low-Medium — asymmetric with `work-order block` which does emit |
| `design-brief create` | `ds_design_briefs` INSERT | Low — creation without event |
| `design-brief lock` | `ds_design_briefs` UPDATE status='locked' | Medium — lock is a lifecycle gate transition |
| `design-brief update` | `ds_design_briefs` UPDATE field | Low — field update |
| `design-brief set-system` | `ds_design_briefs` UPDATE design_system | Low — field update |
| `analytics-ingest` | analytics tables INSERT/UPDATE | Low — ingest path |

### Commands with no state change (read-only) — event absence acceptable

- `project list`, `project status`, `project next`, `project state`
- `work-order list`, `work-order tasks`
- `milestone list`, `milestone status`
- `design-brief show`
- `skill list`
- `workflow status`, `workflow list`
- `task active`
- All infrastructure/health commands

---

## Special Focus: Security Commands

There is **no `ds security` top-level command group** in the CLI.

Security capabilities are accessible only through:
1. **Skill interface:** `ds skill invoke ds-security/<mode>` — runs security skills (scan, dast, binary-scan, review, etc.)
2. **`work-order close` gate:** `security-scan.md` artifact in `.planning/` is checked as a gate condition for certain work order types
3. **`workflow run security-audit`:** The `canonical/workflows/security-audit.yaml` workflow can be invoked via `ds workflow run`

**Assessment vs Intents 2 and 3:**

- **Intent 2 (security during brownfield onboarding):** There is no CLI enforcement that runs a security skill during `ds project register` or `ds integrate install`. The `studio-onboard` workflow (only 2 rows in `raw_workflow_runs`) could serve this purpose but is not triggered automatically.
- **Intent 3 (security as SDLC gate):** The gate mechanism exists — `work-order close` checks for `security-scan.md` artifact if the work order type requires it. But the gate is artifact-file-based, not event-based, and is only enforced at WO close, not at any earlier lifecycle point.

Security is CLI-reachable but not CLI-enforced at intake or deployment boundaries.

---

## Findings

1. **F01 — active_task.json is file-backed state (Intent 1 violation):** The task pointer is written and read purely through `~/.dream-studio/state/active_task.json`. Three callers outside the CLI (`skills/invocation.py`, `telemetry/token_capture.py`, `work_orders/mutations.py`) depend on this file path. No SQLite fallback or mirror exists. Impact: if the file is missing or stale, task attribution breaks silently.

2. **F02 — workflows.json is file-backed live state (Intent 1 violation):** All in-flight workflow execution state lives in `workflows.json`. SQLite (`raw_workflow_runs`, `raw_workflow_nodes`) is only populated on completion via the archival path. The `workflow_invocations` table is populated by a separate telemetry emitter path, not by the CLI workflow runner. Live status queries (`ds workflow status`) bypass SQLite entirely.

3. **F03 — diagnostics directory is a standalone file-based system (Intent 1 gap):** The `~/.dream-studio/state/diagnostics/*.jsonl` system is explicitly designed as a "best-effort" fallback. It has no SQLite mirror or archival path. Data is ephemeral; `ds diagnostics clear` permanently discards it.

4. **F04 — diagnostics handler has no core delegate (design anomaly):** `_diagnostics_dispatch` is the only handler in `ds.py` that contains business logic inline with no delegation to a `core.*` module. All other handlers delegate to core modules.

5. **F05 — gate artifact files are file-based (mixed Intent 1):** Gate enforcement for `work-order close` and `milestone close` reads `.planning/` files (`security-scan.md`, `design-critique.md`) rather than SQLite records. These artifacts are created by `skill invoke` and written to disk. The gate check is reliable within a session but cannot be queried historically from SQLite.

6. **F06 — work-order unblock emits no event (Intent 4 asymmetry):** `work-order block` emits `work_order.blocked`. `work-order unblock` emits nothing. A blocked→in_progress transition leaves no canonical trace.

7. **F07 — design-brief lifecycle produces zero events (Intent 4 gap):** All 5 design-brief commands — including the `lock` transition which is a formal lifecycle gate — emit no canonical events. The design brief lifecycle is invisible to the event spine.

8. **F08 — project set-active and deactivate emit no events (Intent 4 gap):** Active project changes are operationally significant but leave no canonical trace. The `canonical_events` table has 1,831 rows but none from these commands.

9. **F09 — no `ds security` command group (Intent 2 + 3 gap):** Security is skill-invocable and gate-checkable but has no dedicated CLI surface. It cannot be called programmatically from scripts without going through the skill invoke path. There is no CLI command to trigger a security scan as part of project registration or work-order start.

10. **F10 — workflow spool events are not immediately canonical (Intent 4 note):** `ds workflow advance` and `ds workflow run` write spool events via `spool.writer.write_event`. These become canonical only after `ds spool ingest` is subsequently run. There is a window during which workflow execution events exist as files but not as DB records.

11. **F11 — `context.md` writes are file-based side-effects of SQLite commands (Intent 1 note):** `work-order start`, `project start`, and `work-order task-done` all write or update `~/.planning/context.md`. This file serves as the operator's working context document during a session. It is a derived output, not authority, but it creates a persistent file artifact that no SQLite query can reconstruct.

12. **F12 — `skill list` reads canonical/skills/ directly (no registry):** `ds skill list` reads the `canonical/skills/` filesystem and `packs.yaml` directly. The `reg_skills` table exists in the DB schema but has 0 rows. The skill registry is not populated by the CLI.

---

## Intent Divergence

| Intent | Assessment |
|--------|-----------|
| **Intent 1: SQLite-first authority** | **Partially implemented.** Project/work-order/milestone/design-brief groups are SQLite-backed. Three groups are file-backed for live state: task pointer (`active_task.json`), workflow execution (`workflows.json`), and diagnostics (`.jsonl` files). Gate artifact files (`.planning/`) are a fourth file-based pattern used for gate enforcement. |
| **Intent 2: Security audit during brownfield onboarding** | **Not implemented at CLI level.** No CLI command enforces or triggers a security scan during project registration or integration install. The security-audit workflow exists but is not auto-invoked. |
| **Intent 3: Security audit as SDLC lifecycle gate** | **Partially implemented via file artifact.** The `security-scan.md` gate artifact is checked by `work-order close` for qualifying work order types. However: (a) the gate is file-based, not SQLite-based; (b) enforcement is only at WO close, not at deploy/ship; (c) there is no CLI enforcement at project start or milestone close. |
| **Intent 4: Canonical events as the spine** | **Partially implemented.** Key lifecycle transitions emit events: `project.created`, `work_order.started/closed/blocked`, `task.completed/created`, `milestone.completed`, `project.deleted`. Gaps: `project set-active/deactivate`, all design-brief transitions (including `lock`), `work-order unblock`, all memory/spool ingest, all integration commands. The `skill.invoked` event is best-effort only. |
| **Intent 5: Marker file authority for attribution** | **Implemented narrowly.** Only `project register` writes the `.dream-studio-project` marker. `work-order start` and `skill invoke` read it. The marker is used for attribution context in skill invocation, not as a general project identity lookup. `ds_projects` is the authoritative table for project queries. |

---

## Open Questions

1. **active_task.json migration path:** Is there a planned migration to store the active task pointer in `ds_tasks` (e.g., an `is_active` flag or a separate `active_task_context` row)? The env override `DS_ACTIVE_TASK_PATH` suggests test isolation was designed for, implying the path was considered semi-permanent.

2. **workflows.json vs workflow_invocations:** The CLI workflow runner writes to `raw_workflow_runs` on completion and `workflow_invocations` gets populated by the telemetry emitter separately. Are these two records always in sync? Is there a reconciliation path if `archive_workflow` succeeds but the telemetry emitter fails?

3. **diagnostics write_diagnostic callers:** The scan found no explicit `write_diagnostic(source=...)` call patterns in the source tree. Where is the diagnostic stream actually being written from in production? Is it from hook dispatch code using a different pattern?

4. **gate artifact files and SQLite:** The `.planning/security-scan.md` and `.planning/design-critique.md` artifacts drive gate enforcement. Are there plans to record gate pass/fail status directly in `ds_work_orders` or a separate gate table, making historical gate queries possible?

5. **design-brief lock event:** A `design_brief.locked` canonical event would make the brief lifecycle visible in the event spine and allow dashboard queries over brief lock frequency and timing. Is this planned?

6. **`ds security` CLI surface:** Is a `ds security` command group planned, or is the expectation that security always runs through `ds skill invoke ds-security/scan`? The SDLC gate intents suggest security needs to be triggerable from automation scripts.

7. **spool ingest timing:** There is currently no automatic trigger for `ds spool ingest` after `ds workflow run`. The window between spool file creation and canonical event insertion could be hours if the operator doesn't run ingest manually. Is auto-ingest on session stop or post-workflow a design intent?

8. **`reg_skills` table:** The skill registry table exists with 0 rows. Is `ds skill list` expected to populate it? Or is there a separate `ds skill register` command planned? Currently skill discovery is 100% filesystem-based.
