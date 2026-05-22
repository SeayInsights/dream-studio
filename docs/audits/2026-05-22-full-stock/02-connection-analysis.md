# Dream Studio — Connection Analysis
*Phase 2 Cross-Reference Audit | 2026-05-22*

---

## Purpose

This document traces the actual data flows across Dream Studio's production system: which tables writers write to, which paths readers read from, which hooks fire which downstream effects, which skills produce which events, and how adapters, workflows, and migrations connect (or fail to connect) to the canonical v2 data architecture.

Every finding is classified against the v2 target:

- **Aligned** — the path matches the v2 model: writers emit canonical events; projections populate hub-and-spoke tables; views derive from hub-and-spoke.
- **Drift** — partial or inverted alignment: a write path that bypasses the canonical event spine, or a hub table populated by direct INSERT rather than projection.
- **Gap** — the path does not exist at all, or a v2 design element has zero implementation.

**v2 Architecture Target (evaluation criterion):**

| Layer | Tables | Population rule |
|-------|--------|----------------|
| L1 raw | per-adapter input tables | adapters write directly |
| L2 canonical | `canonical_events` only | the ONLY place writers write |
| L3 hub-and-spoke | business/AI execution/bridge tables | populated by PROJECTIONS from canonical events |
| L4 projections | SQL views | derived from hub-and-spoke |

Population model: writers emit canonical events → projections populate hub-and-spoke → views derive from hub-and-spoke.

---

## Section 1 — Table Reader/Writer Graph

### Aligned Paths

**`canonical_events` (L2) — 5 distinct writers, all via spool:**

| Writer | Module | Path |
|--------|--------|------|
| `work_order.started`, `work_order.closed`, `work_order.blocked` | `core/work_orders/mutations.py`, `core/work_orders/start.py`, `core/work_orders/close.py` | `CanonicalEventEnvelope` → spool → `spool/ingestor.py` → `canonical_events` |
| `task.created`, `task.completed` | `core/work_orders/mutations.py` | Same spool path |
| `milestone.closed` | `core/milestones/close.py` | Same spool path |
| `project.registered` | `core/projects/mutations.py` | Same spool path |
| `token.consumed` | `core/telemetry/token_capture.py` | Same spool path |

**`execution_events` (L3 hub) — populated by projection:**

`projections/core/execution_events_projection.py` holds the only active `INSERT INTO execution_events` in production code. The ingestor calls this projection immediately after writing to `canonical_events`. This is textbook v2 compliance: L2 write → projection fires → L3 hub populated.

**`ds_projects`, `ds_work_orders`, `ds_tasks`, `ds_milestones` (L3 hub SDLC tables) — written by CLI mutations, emit events:**

`core/work_orders/mutations.py` is the sole production writer for `ds_tasks` and `ds_work_orders` via `INSERT INTO`. These mutations also fire `CanonicalEventEnvelope` events. The INSERT and the event emission are paired at the same call site.

### Drift Paths

**`hook_invocations` and `tool_invocations` — 917 rows each, written directly:**

`core/telemetry/emitters.py` and `core/telemetry/tool_tracking.py` insert directly into `hook_invocations` and `tool_invocations` via `emit_hook_tool_activity`. These tables receive direct INSERTs triggered by `on-tool-activity` hook — bypassing the canonical event spine entirely. No corresponding `canonical_events` rows exist for most of these records.

**`raw_sessions` — direct INSERT:**

`core/event_store/studio_db.py` line 1088 inserts directly into `raw_sessions`. The `on-session-start` and `on-session-end` hooks write here without emitting through spool. `raw_sessions` has 51 rows; `canonical_events` has no `session.started` or `session.ended` event types.

**`raw_handoffs` — direct INSERT:**

`core/event_store/studio_db.py` line 1305 inserts directly into `raw_handoffs`. Written by `on-stop-handoff.py` dispatch. 26 rows, no canonical event spine linkage.

**`raw_workflow_runs` — direct INSERT:**

`core/event_store/studio_db.py` line 364 inserts directly into `raw_workflow_runs` from `control/execution/workflow/state.py:_try_archive_and_prune`. The companion `workflow_invocations` table is also populated (via `upgrade/canonical_event_reconciliation.py`) but these are not projection-from-canonical writes.

**`hook_executions` — direct INSERT:**

`core/event_store/studio_db.py` line 2406. Only `on_pulse` events write here (45 rows). This is a direct INSERT from a hook, not a projection.

**`ds_design_briefs` — no event emission:**

Design brief mutations (`ds design-brief update`, `lock`, `fill`) write directly to `ds_design_briefs` with no canonical event emitted. The 1 row in `ds_design_briefs` (Dream Command brief, status=locked) has no canonical event spine record. These are pure L3 direct writes — a Drift.

### Gaps

**`execution_nodes`, `execution_outputs` — 0 rows:**

These L3 hub tables exist for workflow execution graph tracking. `workflow_invocations` has 2 rows; `execution_nodes` and `execution_outputs` are empty. No projection or writer populates them.

**`reg_skills`, `reg_workflows` — 0 rows:**

Registry tables created in migration 003 have never been populated by any active writer. `first-run.log` records that `hydrate_registry_once` ran, but it does not INSERT into these tables.

---

## Section 2 — CLI → Handler → Table Graph

### Well-Wired Paths (emit events + write SDLC tables)

| CLI command | Handler module | Tables written | Event emitted |
|-------------|---------------|---------------|---------------|
| `ds project register` | `core/projects/mutations.py` | `ds_projects` | `project.registered` |
| `ds work-order start` | `core/work_orders/start.py` | `ds_work_orders` | `work_order.started` |
| `ds work-order close` | `core/work_orders/close.py` | `ds_work_orders` | `work_order.closed` |
| `ds work-order block` | `core/work_orders/mutations.py` | `ds_work_orders` | `work_order.blocked` (CanonicalEventEnvelope, TA4 fixed) |
| `ds work-order task-done` | `core/work_orders/mutations.py` | `ds_tasks` | `task.completed` |
| `ds milestone close` | `core/milestones/close.py` | `ds_milestones` | `milestone.completed` |

**v2 classification: Aligned** — these commands write L3 SDLC tables and emit L2 canonical events.

### Drift Paths (write tables, no event emission)

| CLI command | Handler module | Tables written | Event emitted |
|-------------|---------------|---------------|---------------|
| `ds project set-active` | `core/projects/mutations.py` | `ds_projects` (status field) | None |
| `ds project deactivate` | `core/projects/mutations.py` | `ds_projects` (status field) | None |
| `ds work-order unblock` | `core/work_orders/mutations.py` | `ds_work_orders` | None |
| `ds design-brief update` | `core/design_briefs/mutations.py` | `ds_design_briefs` | None |
| `ds design-brief lock` | `core/design_briefs/mutations.py` | `ds_design_briefs` | None |
| `ds design-brief fill` | `core/design_briefs/mutations.py` | `ds_design_briefs` | None |

**v2 classification: Drift** — state mutations with no L2 spine record. These transitions are invisible to any projection, dashboard, or downstream consumer relying on `canonical_events`.

### File-Backed Violations (no table write, no event)

| CLI command group | Handler | State written | Event emitted |
|-------------------|---------|--------------|---------------|
| `ds task set-active` | `core/sdlc/active_task.py` | `active_task.json` | None |
| `ds workflow start/status/list` | `control/execution/workflow/state.py` | `workflows.json` | None (until completion) |
| `ds diagnostics list/clear` | `interfaces/cli/ds.py` | `.jsonl` files | None |

**v2 classification: Gap** — no L2, no L3. These are pure file-backed paths with no SQLite write of any kind during the operation.

---

## Section 3 — Hook → Event → Projection Graph

### Active Hook Dispatch Architecture

Two registered entry points: `emitters/claude_code/run.py` (PreToolUse/PostToolUse/Stop) and `runtime/hooks/dispatch/hooks.py` (routes to 22+ handlers by hook type and matcher patterns).

**Hooks that produce canonical events:**

| Hook | Event produced | Path |
|------|---------------|------|
| `run.py` (every tool use) | `tool.execution.completed` (822), `prompt.lifecycle.submitted` (250), `token.consumption.recorded` (148+) | Direct via `emitters/claude_code/emitter.py` → spool |
| `on-stop-handoff.py` → `on-stop-dispatch.py` | Handoff-related events | Indirect via `core/event_store/studio_db.py` |
| `on-post-tool-use` handler | `token.consumed` | Via `core/telemetry/token_capture.py` → CanonicalEventEnvelope → spool |

**v2 classification: Aligned** for these three. The spool pipeline is correct: hook emits envelope → spool file → `ingest_pending()` → `canonical_events`.

**Hooks that do NOT produce canonical events (20 of 22):**

These include `on-tool-activity`, `on-security-scan`, `on-agent-correction`, `on-workflow-progress`, `on-context-threshold`, `on-skill-metrics`, `on-skill-telemetry`, `on-session-start`, `on-session-end`, `on-pulse`, and all `on-edit-dispatch` sub-handlers. They write to file-based stores (`hook-timing.jsonl`, `skill-usage.jsonl`, `activity.json`, `pending-handoff.json`) or `hook_invocations`/`tool_invocations` direct INSERTs.

**v2 classification: Drift** — 20 hooks write L3 tables via direct INSERT or write no SQLite at all. They bypass L2.

**Projection consumers wired to canonical events:**

`projections/core/execution_events_projection.py` is the only confirmed production projection that reads `canonical_events` and writes an L3 table. `core/projections/workflow_consumer.py` and `core/projections/framework.py` exist but their write targets are not confirmed active.

**Broken spool emitter:**

`on-context-threshold.py` imports `from spool.emitter import write_harvest_event`. `spool/emitter.py` does not exist. Every harvest invocation silently fails with `ImportError`. No canonical event is emitted for context threshold crossings.

**v2 classification: Gap** — the harvest event path is fully broken. The import error means L2 is never populated for this event type.

---

## Section 4 — Skill → Event → SDLC Chains

### Confirmed Chains (events with skill attribution)

Only 3 of 11 skills have confirmed `skill.invoked` events in `canonical_events`:

| Skill | Event count | Attribution status | SDLC chain |
|-------|-------------|-------------------|-----------|
| `ds-core` (mode: plan) | 19 events | All `work_order_id: null` | No SDLC linkage — 13 fired in ~3 seconds, suggest workflow runner over-emission |
| `ds-project` | 1 event | Present | Partial chain |
| `ds-workflow` (studio-onboard) | Backfilled via migration | `backfill` attribution | Chain exists only retroactively |

**v2 classification: Drift** — skill invocations reach L2 (`canonical_events`) but most have broken SDLC attribution. The `ds-core:plan` burst shows skill events without work order linkage, breaking the L3 hub-and-spoke traceability requirement.

### Broken Chains (8 skills with zero invocation events)

`ds-quality`, `ds-security`, `ds-analyze`, `ds-domains`, `ds-website`, `ds-fullstack`, `ds-setup`, `ds-career` — zero `skill.invoked` events in 6 days of observation.

**v2 classification: Gap** — these skills produce no L2 records when invoked. The `skill_invocations` table has 1 row with `skill_id=unknown`. No downstream projection or hub table reflects skill execution for these packs.

### skill_invocations as L3 Hub Table

`skill_invocations` was populated by the reconciliation pipeline (`core/upgrade/canonical_event_reconciliation.py` line 891) via `INSERT INTO skill_invocations`. This is a Drift: L3 was populated by the upgrade tool, not by a live projection from L2.

---

## Section 5 — Adapter → Integration Surfaces

### Active Adapter: claude_code only

The adapter system has one implemented adapter (`claude_code`). The install state is file-backed: `~/.dream-studio/integrations/claude_code/manifest.json` (515 installed files). The adapter L1 raw tables (`adapter_authority_profiles`, `adapter_executions`, `adapter_result_records`) all have 0 rows.

**L1 raw layer (adapter input tables):** In the v2 model, L1 tables receive per-adapter raw input before events are canonicalized. The `adapter_*` tables exist in schema but are never written. The claude_code adapter writes directly to the spool (L2) without staging in L1 first.

**v2 classification: Gap** — L1 does not exist in practice. The adapter bypasses L1 and writes to L2 (spool) directly, which is partially aligned (L2 is correct) but leaves L1 permanently empty.

### adapter-projections/ Directory

The `adapter-projections/` directory contains 8 files including `adapter-projections/claude/CLAUDE.md`. Six of 8 files have no live readers. `adapter-projections/claude/CLAUDE.md` is still read by the installer compiler as a live input. This is a superseded directory (since Slice 3) that partially persists.

**v2 classification: Drift** — a superseded artifact still has one active read path.

### Integration Health Circuit

The `last_health_state` field in `manifest.json` is always `null`. The `integration.health.changed` event is never emitted. The health circuit from adapter → L2 canonical event → L3 `adapter_authority_profiles` is fully broken at the L2 emission stage.

**v2 classification: Gap** — adapter health has no L2 record, no L3 state.

---

## Section 6 — Workflow → Execution Paths

### Only Active Workflow: studio-onboard (2 runs, 2026-05-18)

**Execution path:**

`ds workflow start studio-onboard` → `control/execution/workflow/state.py:cmd_start` → writes `workflows.json` (file-based live state) → `WorkflowRunner.run` executes 13 nodes → `_try_archive_and_prune` → `INSERT INTO raw_workflow_runs` + `INSERT INTO raw_workflow_nodes`.

**v2 classification: Drift** — the execution flow uses a file buffer (`workflows.json`) during the run. L3 tables (`raw_workflow_runs`, `raw_workflow_nodes`) are written at completion via direct INSERT, not via projection from L2. There are no `workflow.started` or `workflow.node.completed` canonical events in `canonical_events` for these runs — the `canonical_events` rows for studio-onboard are all prefixed `backfill-activity-log-*`, written by a migration, not the runner.

### 22 Dormant Workflows

22 of 23 workflows in `canonical/workflows/` have never executed. The most critical dormant workflow is `production-readiness.yaml` — the intended gate for both security intake and SDLC readiness. Its `persist-authority-records` node would write to L3 production readiness tables, but this node has never fired.

**v2 classification: Gap** — for 22 of 23 workflows, no L2 or L3 records exist from workflow execution.

### Workflow Security Node Disconnect

`idea-to-pr.yaml`, `comprehensive-review.yaml`, and `project-audit.yaml` have `review-security` nodes that invoke `skill: pr-security-scan`. When/if these run, the security skill findings write to `.md` files in `.dream-studio/secure/reports/`, not to any L3 security table. GitHub issues are created for HIGH/CRITICAL findings via GitHub API.

**v2 classification: Gap** — security findings from workflows would bypass L3 SQLite entirely, writing to files and external GitHub, not to `security_findings` or `sec_sarif_findings`.

---

## Section 7 — Migration → Current State Mapping

### Migration Eras and Their L3 Contributions

| Era | Migrations | L3 tables created | Currently active |
|-----|-----------|-------------------|-----------------|
| Foundation (001-010) | `ds_projects`, `ds_work_orders`, `ds_milestones`, `ds_tasks`, `reg_skills`, `reg_workflows`, `canonical_events` | Core SDLC spine + event store | SDLC spine: active. `reg_skills`/`reg_workflows`: empty |
| First Expansion (012-034) | Security tables, workflow tables, PRD tables, career tables, adapter tables | All L3 hub domains | Most empty (security: 0 rows; PRD: 0 rows; career: 0 rows; adapters: 0 rows) |
| Post-Gap Expansion (037-050) | `execution_events`, `token_usage_records`, `hook_invocations`, `tool_invocations` | Telemetry L3 hub tables | `hook_invocations`/`tool_invocations`: active (direct write). `execution_events`: active (projection). `token_usage_records`: 0 rows |
| TA Series (051-064) | Backfill spine events, add `_built_from_event_id` to `execution_events`, dismantle `activity_log` | Retroactive L2→L3 wiring | SDLC backfill: complete. `activity_log` hub-and-spoke: built (018-025) then reversed (062-063) |

### activity_log Reversal (Key Finding)

Migrations 017-025 built a complete hub-and-spoke architecture centered on `activity_log`. Migrations 062-063 (TA0c workstream) dismantled it — `activity_log` was removed as a hub. This represents the system's most complete prior attempt at L3 hub population: built in 8 migrations, reversed in 2. The reversal was intentional (activity_log was identified as a misplaced hub) but left L3 hub tables in the telemetry domain (hook_invocations, tool_invocations) without a projection-from-canonical path.

**v2 classification: Drift** — the L3 telemetry hub tables that replaced `activity_log` are populated via direct INSERT (Drift) rather than projection (Aligned).

### Empty Table Ratio

141 of 182 tables (77%) are empty. The schema has grown substantially ahead of the write paths. Migrations have created valid L3 structure that no projection currently populates.

---

## Section 8 — Documentation → Code Drift

### Aligned Contracts

- `event-contract.md` ↔ implementation: Aligned. The spool pipeline, `CanonicalEventEnvelope`, and `canonical_events` as described in the contract match the live code in `spool/ingestor.py` and `core/event_store/event_store.py`.
- `event-store.md` ↔ implementation: Aligned. `execution_events` is populated by `projections/core/execution_events_projection.py` as documented.
- `hook-contract.md` ↔ implementation: Minor drift. Three orphaned handlers (`on-startup-health.py`, `on-periodic-health.py`, `on-skill-gate.py`) exist but are not reachable via dispatchers. The contract does not address their disposition.

### Active Drift

- **Six Phase 16A contracts describe file-based state as canonical:** `approval-contract`, `eval-artifact-contract`, `work-ledger-contract`, `work-order-contract`, `work-result-contract`, and the workflow row in `state-contract`. These contracts accurately document current Phase 16A state. Intent #1 ("SQLite-first") describes the target. The documentation is not wrong — it reflects intentional phase gating.
- **`skill-contract.md` does not reflect the SKILL.md/`config.yml` split** introduced in the YAML mode config work. Required Fields in the contract include metadata that now lives in `config.yml`. Skill authors reading only the contract would place fields in the wrong file.
- `workflow-contract.md` contains no security requirement. A workflow can be fully contract-compliant with no security node.

### Gap Documentation

- `security-by-default-development-lifecycle-gate.md` states security review is required at `project_intake` and `deployment`. No operations document gives the CLI commands to execute this. The contract is policy; the operational path is undocumented.
- `studio-onboard.yaml` has no companion doc. No `docs/operations/` entry explains what studio-onboard does, what its security gate expectations are, or what SQLite tables it writes.

---

## Section 9 — Security Infrastructure Wiring

### The Security Write Path Does Not Exist

All 12 security SQLite tables have 0 rows. The full chain from security event to L3 security table has never been traversed in production:

```
[security finding]
  → on-security-scan.py (fires 5 times) → PRINT warning only → no SQLite write
  → sec_hook_checks (0 rows)
  → hook_findings (0 rows)
  → guardrail_decisions (0 rows)
```

**v2 classification: Gap** — the security domain has no active L2 or L3 paths. `canonical_events` contains 0 security-namespace events. L3 security tables have 0 rows. The infrastructure is schema-present but write-path absent.

### Security Gate: File Presence, Not Spine

The `security_scan` gate in `core/work_orders/close.py` reads `.planning/work-orders/<id>/security-scan.md`. This resolves against a gitignored file, not against `security_findings` or `canonical_events`. The gate is named as a security control but does not invoke any security skill or query any security table.

**v2 classification: Gap** — the gate that is supposed to enforce security has no connection to L2 or L3.

### guardrails/evaluator.py: Complete but Unwired

`guardrails/evaluator.py` has a complete implementation: reads `guardrails/rules/security.yaml`, queries `activity_log` (now removed — this is a stale dependency), emits `CanonicalEventEnvelope` on decision, writes to `guardrail_decisions`. It is not registered in `settings.json`. The rules it would evaluate trigger on `hook_finding.created` — an event type never emitted by any hook.

**v2 classification: Gap** — the guardrail system has both a broken trigger (`hook_finding.created` never emitted) and a stale data dependency (`activity_log` removed in TA0c). Two separate fixes required before it could function.

---

## Section 10 — Storage Architecture vs v2 Target

### The Spool Pipeline: The Only Correctly Implemented v2 Path

The spool pipeline is the system's one correctly implemented L2→L3 projection chain:

```
hook fires → emitter writes CanonicalEventEnvelope → events/spool/ file
  → Stop hook triggers ingest_pending()
  → spool/ingestor.py reads file
  → INSERT INTO canonical_events (L2)
  → execution_events_projection.apply() → INSERT INTO execution_events (L3)
  → file moved to events/processed/
```

This path is well-tested (`tests/integration/spool/`) and demonstrably correct. It is the single model for how v2 should work for all other domains.

**v2 classification: Aligned.**

### Direct-Write Bypasses (Drift)

24 file-based runtime state stores and 5 direct-INSERT SQLite paths bypass the canonical event spine:

| Store | Type | V2 impact |
|-------|------|-----------|
| `hook_invocations` / `tool_invocations` | Direct INSERT | 917 rows each — the most populated non-spool L3 tables, all written directly |
| `raw_sessions` | Direct INSERT | 51 rows — session lifecycle invisible to canonical event consumers |
| `raw_handoffs` | Direct INSERT | 26 rows — handoff lifecycle not in L2 |
| `hook-timing.jsonl` | File (392 KB) | The highest-volume operational record, entirely outside SQLite |
| `workflows.json` | File | Live workflow state during execution — not in L2 or L3 |
| `active_task.json` | File | Attribution pointer — feeds `token.consumed` attribution but itself has no canonical record |
| `skill-usage.jsonl` + `telemetry-buffer.jsonl` | File (broken pipeline) | Skill telemetry triple-store with no authoritative target |

**v2 classification: Drift** for direct-INSERT paths; **Gap** for file-only paths.

### Schema Overreach: L3 Tables Without Projections

The v2 model requires L3 tables to be populated by projections from L2. In practice, over 100 empty L3 tables exist with no projection assigned:

- All 12 security tables: no projection, no writer
- All 9 PRD tables: no projection, no writer
- All 14 career tables: no projection (external dependency)
- All 8 project intelligence tables: no projection
- All 5 production readiness tables: no projection

**v2 classification: Gap** — these are structural scaffolding: L3 tables with valid schemas but no L2→L3 projection path.

---

## Section 11 — Reversal and Decay Patterns

This section observes without prescribing. These patterns represent points where the architecture changed direction or implementations degraded.

### Pattern 1: Build-Then-Reverse (activity_log hub)

The most complete v2 precursor in the system was built and then dismantled. Migrations 017-025 created an `activity_log` hub that aggregated events from multiple domains. Migrations 062-063 reversed this. The tables that replaced `activity_log` as the L3 telemetry hub (`hook_invocations`, `tool_invocations`) are populated by direct INSERT, not projection. The hub-and-spoke architecture was attempted, judged incorrect, and partially rebuilt in a less compliant form.

### Pattern 2: Schema Ahead of Implementation

141 of 182 tables are empty. The pattern across every domain (security, PRD, career, adapters, project intelligence) is: migration creates L3 table → no projection is implemented → table remains empty. The migration cadence created complete schema ahead of any write-path work.

### Pattern 3: Triple-Store Fragmentation

Three domains show triple-store fragmentation — the same data exists in three places with no authoritative source:

- **Skill telemetry:** `skill-usage.jsonl` + `telemetry-buffer.jsonl` + `raw_skill_telemetry` (0 rows). Pipeline broken at flush stage.
- **Workflow state:** `workflows.json` (live) + `raw_workflow_runs` + `workflow_invocations`. The latter two are parallel tables for the same 2 runs.
- **Hook execution:** `hook-timing.jsonl` (3,645 lines) + `hook_executions` (45 rows, on_pulse only) + `hook_invocations` (917 rows, on-tool-activity only).

### Pattern 4: Broken Emitter Chain

`on-context-threshold.py` imports `from spool.emitter import write_harvest_event`. The module does not exist. This ImportError means every context threshold crossing silently fails to emit any canonical event. The `pending-handoff.json` file is written instead (file-based fallback), but the L2 record is never created. This is a specific example of the broader pattern: file-based fallback that survives when the canonical event path breaks.

### Pattern 5: Backfill as the Primary L2 Population Path

Of the 1,853 rows in `canonical_events`, a significant fraction carry `attribution_status: "backfill"` — these were generated by migration scripts (TA series, 051-064), not by live event emission. The SDLC spine events for projects, milestones, and work orders that existed before TA0 were created retroactively. The migrations serve as retroactive event producers, not forward-flowing projections.

### Pattern 6: Test Data in Production Database

23 of 25 `ds_projects` rows are pytest test fixtures. The `guard_real_homedir` fixture is supposed to prevent tests from touching the real database, but these rows exist in `studio.db`. This suggests tests ran against the live database at some point before or during the fixture's introduction. The contamination is structural — removing them requires a migration or manual DELETE, not a code fix.

### Pattern 7: Stale State Files

Three file-based state stores contain stale data from prior sessions:

- `pending-handoff.json`: `status: "in_progress"` from 2026-05-21 — ~17 hours stale with no TTL enforcement
- `workflow-checkpoint.json`: `wf-fail-1 / n1 / failed` — a pytest artifact from 2026-05-20
- `skill-usage.jsonl`: all 3 records have `skill=unknown` — the skill name resolution is broken at the write site, so even if the flush pipeline were fixed, the data would be semantically empty

---

## Cross-Category Findings

**XF1 — The spool pipeline is the only v2-compliant L2→L3 path, and it covers only SDLC + token telemetry events.**

The correct pattern (emitter → L2 canonical events → projection → L3 hub) is implemented and tested for SDLC events (project/milestone/work order/task) and token telemetry (`token.consumed`). For all other domains — security, workflow, skill telemetry, hook execution, session lifecycle, adapter health — the write path either bypasses L2 (direct INSERT to L3), uses files instead of SQLite, or does not exist at all.

**XF2 — hook_invocations and tool_invocations are the largest active L3 tables by row count, and both are written in violation of the v2 population model.**

With 917 rows each, these are the most-used non-spool tables in the system. They are written by `core/telemetry/emitters.py` via direct INSERT triggered by `on-tool-activity`. The v2 model requires L3 to be populated by projection from L2, not by direct write from a hook. These 1,834 rows represent the largest Drift in the system by data volume.

**XF3 — The security domain is simultaneously the most schema-complete and the most operationally empty domain.**

12 L3 security tables, 6 security API routes, 8 skill modes, a complete guardrail evaluator, 5 guardrail rules, and a 172-line policy contract — all with zero operational data. The `security_scan` gate in `close.py` is named as a security enforcement point but resolves against a gitignored file. The gap between schema completeness and operational activation is wider in the security domain than in any other.

**XF4 — Design brief mutations are L3 writes with no L2 record — making design brief lifecycle invisible to any projection or consumer.**

The `ds_design_briefs` table has 1 row (Dream Command brief, locked). No canonical events exist for `design_brief.created`, `design_brief.updated`, or `design_brief.locked`. The design brief is one of the most operator-visible SDLC artifacts (it gates WO3 from starting) but its entire lifecycle is a Drift: mutations write L3 directly with no L2 spine.

**XF5 — 24 file-based runtime state stores represent a systematic inversion of the v2 model: file is the authority, SQLite is empty or secondary.**

In a v2-compliant system, SQLite is the authority and files (the spool) are transient buffers. The current system has 24 stores where the opposite is true: file is the populated store and the corresponding SQLite table is either empty or disconnected. The most impactful are `hook-timing.jsonl` (3,645 lines, zero equivalent in `hook_timing_records`), `.sessions/` files (58 files, 26 `raw_handoffs` rows — 55% not ingested), and `skill-usage.jsonl` (the only skill telemetry data, in a file with broken flush pipeline).

**XF6 — The test data contamination of `ds_projects` (23/25 rows are test fixtures) means the SDLC authority table is structurally unreliable.**

The active project resolver queries `ds_projects WHERE status='active' ORDER BY updated_at DESC`. With 23 test fixture rows in the table, any query that does not filter carefully could return a test row as the active project. The MEMORY.md / live state mismatch (MEMORY says Dream Command is active; DB shows Dream Studio active) is likely a symptom of this contamination.

**XF7 — The migration system created over 100 empty L3 tables across 11 domains without corresponding projection implementations, creating a false impression of architectural completeness.**

A reader of the SQLite schema would see tables for adapters, security, PRD, career, project intelligence, production readiness, compliance, and risk management — and might conclude these domains are implemented. All 100+ tables are empty. The correct v2 characterization: schema is aspirational, projections are absent, L3 is unpopulated for 11 of the 12+ domains modeled in the database.

---

## v2 Migration Summary

The current state against each v2 layer:

| V2 Layer | State | Notes |
|----------|-------|-------|
| L1 raw (adapter input tables) | Gap | `adapter_*` tables exist but are never written. The claude_code adapter bypasses L1 and writes to L2 spool directly |
| L2 canonical (`canonical_events`) | Aligned (partial) | SDLC + token telemetry: aligned via spool. Hook execution, session, handoff, workflow, security: no L2 record |
| L3 hub-and-spoke | Mixed | `execution_events`: Aligned (projection from L2). `hook_invocations`/`tool_invocations`: Drift (direct INSERT). SDLC tables: Drift (direct INSERT + event — paired but not projection-from-event). Security/PRD/career/adapters: Gap (0 rows) |
| L4 projections (SQL views) | Gap | The v4 projections layer is not implemented. The `projections/api/routes/` FastAPI routes are read surfaces, not SQL views over L3 |

**Summary:** L2 is partially correct for the SDLC domain. The L1→L2→L3→L4 chain as specified exists only in the spool pipeline (L2→L3 for execution events). For all other domains, the chain either starts at L3 (Drift) or does not exist (Gap).

---

## Appendix: Key File-to-Table Cross-Reference

| File-based store | Corresponding SQLite table | Population state |
|-----------------|---------------------------|-----------------|
| `hook-timing.jsonl` (3,645 lines) | None (`hook_timing_records` would be new) | File: active. Table: does not exist |
| `skill-usage.jsonl` (3 lines, all `unknown`) | `raw_skill_telemetry` (0 rows) | File: broken data. Table: 0 rows |
| `telemetry-buffer.jsonl` (1 line) | `raw_skill_telemetry` | Buffer: active. Flush: broken |
| `workflows.json` (currently empty) | `workflow_invocations` (2 rows) | File: live state during run. Table: archive only |
| `workflow-checkpoint.json` (stale test artifact) | `automation_checkpoints` (0 rows) | File: stale. Table: 0 rows |
| `active_task.json` (currently absent) | `ds_tasks` (9 rows) | File: write-on-set-active. Table: authority for task data |
| `pending-handoff.json` (stale, in_progress) | `shared_context_packets` (0 rows) | File: stale. Table: 0 rows |
| `.sessions/` files (58 files) | `raw_handoffs` (26 rows), `ds_documents` (12 rows) | File: primary. Table: 55% ingested |
| `pulse-*.md` / `pulse-latest.json` | `raw_pulse_snapshots` (0 rows) | File: active. Table: write broken |
| `token-log.md` | `raw_token_usage` (3 rows, all zero) | File: active. Table: effectively empty |
| `director-corrections.md` (18 lines) | `cor_skill_corrections` (0 rows) | File: active. Table: write not wired |
| `first-run.log` | `reg_skills` (0 rows), `reg_workflows` (0 rows) | File: active. Table: hydration not persisting |
| `security/scans/{client}/` | `sec_sarif_findings` (0 rows) | File: intended store per SKILL.md. Table: no ETL |
