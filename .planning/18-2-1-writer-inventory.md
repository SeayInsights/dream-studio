# Phase 18.2.1 — Writer Inventory
# Direct-Write Call Site Catalog for v2 Projection Migration

**Status:** Complete
**Date:** 2026-05-23
**Author:** SeayInsights / Dannis Seay
**Phase reference:** `.planning/phase-18-architectural-realignment.md` § Phase 18.2
**Architecture reference:** `docs/architecture/dream-studio-structured-authority-projection-model.md`

---

## 1. Summary Statistics

| Metric | Count |
|---|---|
| Total in-scope direct-write call sites | 30 |
| Tier 1 — Attribution-broken (missing or wrong events) | 7 |
| Tier 2 — Security-sensitive | 1 |
| Tier 3 — High-traffic (invocation telemetry) | 7 |
| Tier 4 — Remaining (partial migrations: have events, still direct-write) | 15 |
| Architectural violations (writes to v2 raw/canonical from wrong place) | 0 |
| Out-of-scope for 18.2 (Phase 18.3 file-state targets, studio_db.py) | ~10 |

**Tables receiving direct writes (in-scope):**

| Table | Writer Count | Existing Projection? |
|---|---|---|
| business_projects | 4 | No |
| business_milestones | 2 | No |
| business_work_orders | 5 | **Yes** (WorkOrderProjection, Phase 18.1.5) |
| business_tasks | 2 | No |
| business_design_briefs | 4 | No |
| hook_invocations | 1 | No (Phase 18.5.3) |
| tool_invocations | 1 | No (Phase 18.5.4 → retire to raw) |
| skill_invocations | 1 | No |
| agent_invocations | 1 | No |
| workflow_invocations | 1 | No |
| process_runs | 1 | No |
| token_usage_records | 1 | No |
| security_findings | 1 | No |
| route_decision_records | 1 | No |
| dashboard_attention_items | 1 | No |
| research_evidence_records | 1 | No |
| blocker_resolution_records | 1 | No |
| authority_projection_records | 1 | No |

---

## 2. Per-Writer Table

### 2.1 Business Table Writers

All business-table writers live in the `core/` mutation modules. They are called by the `ds` CLI and by skills/workflows that import them directly.

| # | File | Function | Table | Op | Trigger | Events Emitted | Tier |
|---|---|---|---|---|---|---|---|
| W01 | `core/projects/mutations.py:294` | `register_project()` | business_projects | INSERT | `ds project create` / `ds-project scope` | `project.created` | T4 |
| W02 | `core/projects/mutations.py:48` | `set_active_project()` | business_projects | UPDATE | `ds project set-active` | **NONE** | **T1** |
| W03 | `core/projects/mutations.py:75` | `deactivate_project()` | business_projects | UPDATE | `ds project deactivate` | **NONE** | **T1** |
| W04 | `core/projects/mutations.py:158-165` | `delete_project()` | business_projects + 4 cascades | DELETE | `ds project delete` | `project.deleted`, `task.deleted` (per task) — **missing** cascade events for WOs, milestones, briefs | T4 |
| W05 | `core/milestones/mutations.py:62` | `create_milestone()` | business_milestones | INSERT | `ds milestone create` | `milestone.created` | T4 |
| W06 | `core/milestones/close.py:200` | `close_milestone()` | business_milestones | UPDATE | `ds milestone close` | `milestone.completed`, `gate.bypassed` (if forced) | T4 |
| W07 | `core/work_orders/mutations.py:366` | `create_work_order()` | business_work_orders | INSERT | `ds work-order create` | `work_order.created` | T4 |
| W08 | `core/work_orders/start.py:441` | `start_work_order()` | business_work_orders | UPDATE | `ds work-order start` | `work_order.started` | T4 |
| W09 | `core/work_orders/close.py:410` | `close_work_order()` | business_work_orders | UPDATE | `ds work-order close` | `work_order.closed` | T4 |
| W10 | `core/work_orders/mutations.py:191` | `block_work_order()` | business_work_orders | UPDATE | `ds work-order block` | `work_order.blocked` | T4 |
| W11 | `core/work_orders/mutations.py:229` | `unblock_work_order()` | business_work_orders | UPDATE | `ds work-order unblock` | **NONE** — `work_order.unblocked` is in registry but not wired | **T1** |
| W12 | `core/work_orders/mutations.py:58` | `mark_task_done()` | business_tasks | UPDATE | `ds work-order task-done` | `task.completed` | T4 |
| W13 | `core/work_orders/mutations.py:285` | `add_tasks_from_file()` | business_tasks | INSERT | `ds work-order start` (parses tasks file) | `task.created` (per task) | T4 |
| W14 | `core/design_briefs/mutations.py:68` | `create_design_brief()` | business_design_briefs | INSERT | `ds design-brief create` / `ds-website discover` | **NONE** — no registry entry | **T1** |
| W15 | `core/design_briefs/mutations.py:110` | `lock_design_brief()` | business_design_briefs | UPDATE | `ds design-brief lock` | **NONE** — no registry entry | **T1** |
| W16 | `core/design_briefs/mutations.py:142` | `update_design_brief_field()` | business_design_briefs | UPDATE (f-string field) | `ds design-brief update` / `ds-website discover` | **NONE** — no registry entry | **T1** |
| W17 | `core/design_briefs/mutations.py:176` | `set_design_system()` | business_design_briefs | UPDATE | `ds design-brief update` | **NONE** — no registry entry | **T1** |

### 2.2 Telemetry Writers (execution_spine.py)

All telemetry writes funnel through `core/telemetry/execution_spine.py`. The entry point `record_invocation()` dispatches to the correct table based on `invocation_type`. Called from `core/telemetry/emitters.py` at hook/skill/workflow/tool boundaries.

| # | File | Function | Table | Op | Trigger | Events Emitted | Tier |
|---|---|---|---|---|---|---|---|
| W18 | `core/telemetry/execution_spine.py:309` | `record_invocation("hook")` | hook_invocations | INSERT | Every hook execution (via emitters.py) | **NONE** — OD7: should derive from AI canonical | **T3** |
| W19 | `core/telemetry/execution_spine.py:309` | `record_invocation("tool")` | tool_invocations | INSERT | Every tool call (via emitters.py) | **NONE** — OD7: should move to raw layer | **T3** |
| W20 | `core/telemetry/execution_spine.py:309` | `record_invocation("skill")` | skill_invocations | INSERT | Every skill execution (via emitters.py) | **NONE** | **T3** |
| W21 | `core/telemetry/execution_spine.py:309` | `record_invocation("agent")` | agent_invocations | INSERT | Every agent execution (via emitters.py) | **NONE** | **T3** |
| W22 | `core/telemetry/execution_spine.py:309` | `record_invocation("workflow")` | workflow_invocations | INSERT | Every workflow execution (via emitters.py) | **NONE** | **T3** |
| W23 | `core/telemetry/execution_spine.py:220` | `record_process_run()` | process_runs | INSERT | Execution run start/end (via emitters.py) | **NONE** | **T3** |
| W24 | `core/telemetry/execution_spine.py:340` | `record_token_usage()` | token_usage_records | INSERT | Token consumption logging (via emitters.py) | Partial — `token.consumed` canonical events exist but direct write remains | **T3** |
| W25 | `core/telemetry/execution_spine.py:391` | `record_security_finding()` | security_findings | INSERT | Security scan results (ds-security skill) | **NONE** | **T2** |
| W26 | `core/telemetry/execution_spine.py:434` | `record_route_decision()` | route_decision_records | INSERT | Route evaluation (ds-quality coach) | **NONE** | T4 |
| W27 | `core/telemetry/execution_spine.py:470` | `record_dashboard_attention()` | dashboard_attention_items | INSERT | Dashboard surfacing (various skills) | **NONE** | T4 |
| W28 | `core/telemetry/execution_spine.py:507` | `record_research_evidence()` | research_evidence_records | INSERT | Research outputs (ds-analyze) | **NONE** | T4 |
| W29 | `core/telemetry/execution_spine.py:542` | `record_blocker_resolution()` | blocker_resolution_records | INSERT | Blocker resolution tracking | **NONE** | T4 |
| W30 | `core/telemetry/execution_spine.py:578` | `record_authority_projection()` | authority_projection_records | INSERT | Authority lineage records | **NONE** | T4 |

### 2.3 Out-of-Scope Writers (Phase 18.3 targets)

These write to pre-v2 operational tables in `core/event_store/studio_db.py`. They are managed correctly by their legacy system and are Phase 18.3 (file-state migration) targets, not Phase 18.2 targets. Not architectural violations.

| File | Functions | Tables Written | Phase |
|---|---|---|---|
| `core/event_store/studio_db.py` | `archive_workflow()` | raw_workflow_runs, raw_workflow_nodes | 18.3.1 |
| `core/event_store/studio_db.py` | `import_buffer()`, `rebuild_summaries()`, `rolling_window_prune()` | raw_skill_telemetry | 18.3.3 |
| `core/event_store/studio_db.py` | `insert_operational_snapshot()`, `capture_approach()` | raw_approaches | 18.3 |
| `core/event_store/studio_db.py` | `insert_session()`, `end_session()`, `mark_handoff_consumed()` | raw_sessions | 18.3.4 |
| `core/event_store/studio_db.py` | `insert_handoff()` | raw_handoffs | 18.3 |
| `core/event_store/studio_db.py` | `upsert_spec()` | raw_specs | 18.3 |
| `core/event_store/studio_db.py` | `upsert_prd_task()` | raw_tasks | 18.3 |
| `core/event_store/studio_db.py` | `insert_token_usage()` | raw_token_usage | 18.3.3 |
| `core/upgrade/canonical_event_reconciliation.py` | `persist_import_plan_entry()`, etc. | legacy_canonical_event_import_map, skill_invocations, hook_invocations | One-time upgrade script |
| `control/research/engine.py` | `save_research()`, `increment_references()` | raw_research | 18.3 |

---

## 3. Per-Table Summary

### L3 Business Tables

**business_projects**
- Direct writers: W01, W02, W03, W04
- Existing projection: None
- Events in registry: `project.created`, `project.deleted`, `project.registered`, `project.updated`
- Complications: `set_active_project` and `deactivate_project` have no events and no registry entries. Require new event types (`project.activated`, `project.deactivated`) before migration.
- Projection needed: `ProjectProjection` — business_projects from project.created/deleted/activated/deactivated

**business_milestones**
- Direct writers: W05, W06
- Existing projection: None
- Events in registry: `milestone.created`, `milestone.deleted`, `milestone.completed`
- Complications: None significant. Both writers already emit events. Projection straightforward.
- Projection needed: `MilestoneProjection` — business_milestones from milestone.* events

**business_work_orders**
- Direct writers: W07, W08, W09, W10, W11
- Existing projection: **WorkOrderProjection** (`core/projections/work_order_projection.py`) — built in Phase 18.1.5
- Events in registry: `work_order.created`, `work_order.started`, `work_order.blocked`, `work_order.unblocked`, `work_order.closed`
- Complications: W11 (`unblock_work_order`) does NOT emit `work_order.unblocked` despite the registry entry existing. This is a simple bug fix. All other writers emit correct events. The projection already handles these events.
- Migration path: Fix W11 event emission, then remove direct writes from W07-W11. Existing projection takes over.

**business_tasks**
- Direct writers: W12, W13
- Existing projection: None
- Events in registry: `task.created`, `task.started`, `task.deleted`, `task.completed`
- Complications: W12 and W13 both emit correct events. Projection straightforward.
- Projection needed: `TaskProjection` — business_tasks from task.* events

**business_design_briefs**
- Direct writers: W14, W15, W16, W17
- Existing projection: None
- Events in registry: **NONE for design_brief events**
- Complications: Most complete gap in the system. No events, no registry entries, no projection. All 4 writers need event emission added AND 4+ new event types registered AND a new projection built.
- W16 uses dynamic f-string field name (`UPDATE business_design_briefs SET {field} = ?`). Field is validated against `BRIEF_UPDATABLE_FIELDS` allow-list, so no SQL injection, but requires event payload to carry field name.
- Projection needed: `DesignBriefProjection` — business_design_briefs from design_brief.* events
- Event types needed: `design_brief.created`, `design_brief.updated`, `design_brief.locked`

### L3 Telemetry Tables

**hook_invocations**
- Direct writers: W18
- Existing projection: None — OD7 says this should be projection-derived from AI canonical
- Per OD7: After Phase 18.5.2 (hook emitter migration), this table should be populated by `HookInvocationProjection` reading AI canonical events.
- Handled by: Phase 18.5.3

**tool_invocations**
- Direct writers: W19
- Existing projection: None — Per OD7, tool-level detail moves to raw layer
- Handled by: Phase 18.5.4 (tool_invocations retired or repurposed; tool detail → raw_claude_code_events)

**skill_invocations**
- Direct writers: W20
- Existing projection: None
- Projection needed: `SkillInvocationProjection` from `skill.invoked`/`skill.executed` events
- Handled by: Phase 18.5.5

**agent_invocations**
- Direct writers: W21
- Existing projection: None
- Projection needed: `AgentInvocationProjection`
- Handled by: Phase 18.5.5

**workflow_invocations**
- Direct writers: W22
- Existing projection: None
- Projection needed: `WorkflowInvocationProjection`
- Handled by: Phase 18.5.5

**process_runs**
- Direct writers: W23
- Existing projection: None
- Projection needed: `ProcessRunProjection` from `execution.started`/`execution.completed` events
- Handled by: Phase 18.5.5

**token_usage_records**
- Direct writers: W24
- Existing projection: None
- Partial migration: canonical events `token.consumed` exist, but direct write to this table also occurs
- Projection needed: `TokenUsageProjection` from `token.consumed` events
- Handled by: Phase 18.2.4 (high-traffic)

**security_findings**
- Direct writers: W25
- Existing projection: None
- Per OD1: Security findings to SQLite only; deliverables generated on-demand
- Projection needed: `SecurityFindingProjection` from security audit events
- Event types needed: `security.finding.recorded`, `security.finding.resolved`
- Handled by: Phase 18.2.3 (security-sensitive)

**route_decision_records, dashboard_attention_items, research_evidence_records, blocker_resolution_records, authority_projection_records**
- Direct writers: W26, W27, W28, W29, W30
- Existing projections: None
- Low urgency; no attribution impact
- Handled by: Phase 18.2.5 (remaining)

---

## 4. Projection Backlog

Projections needed during Phase 18.2 work. All should follow the `WorkOrderProjection` pattern from Phase 18.1.5.

| Priority | Projection | Source Events | Tables Populated | Phase |
|---|---|---|---|---|
| P1 | `ProjectProjection` | project.created, project.deleted, project.activated, project.deactivated | business_projects | 18.2.2 |
| P2 | `TaskProjection` | task.created, task.completed, task.deleted | business_tasks | 18.2.2 |
| P3 | `MilestoneProjection` | milestone.created, milestone.completed, milestone.deleted | business_milestones | 18.2.2 |
| P4 | `DesignBriefProjection` | design_brief.created, design_brief.updated, design_brief.locked | business_design_briefs | 18.2.2 |
| P5 | `SecurityFindingProjection` | security.finding.recorded, security.finding.resolved | security_findings | 18.2.3 |
| P6 | `TokenUsageProjection` | token.consumed | token_usage_records | 18.2.4 |
| P7 | `HookInvocationProjection` | hook.invoked, hook.completed | hook_invocations | 18.5.3 |
| P8 | `SkillInvocationProjection` | skill.invoked, skill.executed | skill_invocations | 18.5.5 |
| P9 | `AgentInvocationProjection` | agent.invoked, agent.completed | agent_invocations | 18.5.5 |
| P10 | `WorkflowInvocationProjection` | workflow.node.completed, workflow.completed | workflow_invocations | 18.5.5 |
| P11 | `ProcessRunProjection` | execution.started, execution.completed, execution.failed | process_runs | 18.5.5 |

**Already exists:** `WorkOrderProjection` for business_work_orders (Phase 18.1.5)

---

## 5. Event Type Backlog

New event types needed in `config/event_type_registry.py` before writers can be migrated.

| Event Type | Routes To | Needed By | Registry Gap |
|---|---|---|---|
| `project.activated` | business | W02 (set_active_project) | Missing — no project status-change event |
| `project.deactivated` | business | W03 (deactivate_project) | Missing — no project status-change event |
| `design_brief.created` | business | W14 (create_design_brief) | Missing — entire design_brief domain absent |
| `design_brief.updated` | business | W16 (update_design_brief_field) | Missing |
| `design_brief.locked` | business | W15 (lock_design_brief) | Missing |
| `security.finding.recorded` | business | W25 (record_security_finding) | Missing |
| `security.finding.resolved` | business | W25 follow-up | Missing |
| `work_order.cascade_deleted` | business | W04 cascade (delete_project) | Missing — project delete cascades WOs without per-WO event |
| `milestone.cascade_deleted` | business | W04 cascade (delete_project) | Missing — project delete cascades milestones without per-milestone event |

**Already in registry, not yet wired:**
- `work_order.unblocked` — in registry, not emitted by W11. Simple bug fix.
- `milestone.deleted` — in registry, needs confirmation it's emitted (not verified during this investigation)

---

## 6. Complications and Dependencies

### Writers with synchronous-state callers (may need lag tolerance)

| Writer | Caller dependence | Migration complication |
|---|---|---|
| W07 `create_work_order` | `ds work-order start` reads the newly created row | After migration, start command must wait for projection or use event-local state |
| W08 `start_work_order` | `ds work-order close` reads status | Same — projection must converge before close |
| W12 `mark_task_done` | Reads back `tasks_remaining` immediately after write | Post-migration: pass remaining count in event payload, avoid synchronous read |
| W13 `add_tasks_from_file` | Returns inserted task IDs to caller | Task IDs generated before insert; can put in event payload |

All business_work_orders writers benefit from the existing WorkOrderProjection which already handles convergence. The real concern is the ~5s projection poll cycle: CLI commands that read immediately after writing need to either wait for projection or skip the projection for synchronous read-back (query the event, not the projection).

**Recommended approach:** During Phase 18.2, remove the direct write but keep the read. The projection handles eventual consistency for dashboard/reporting. Real-time reads from the CLI continue to query the structured table (which is populated by the projection). This avoids a read-after-write lag problem.

### W16 — Dynamic SQL field (design_brief update)

`update_design_brief_field()` at `core/design_briefs/mutations.py:142` uses an f-string to build the SET clause:
```python
f"UPDATE business_design_briefs SET {field} = ?, updated_at = ? WHERE brief_id = ?"
```
Field is validated against `BRIEF_UPDATABLE_FIELDS` allow-list before reaching SQL — no injection risk. For projection migration: event payload must carry both `field` and `value`. The projection must handle multi-field update events mapping field name to column. Not complex but requires careful event schema design.

### Reconciliation script

`core/upgrade/canonical_event_reconciliation.py` writes to `skill_invocations`, `hook_invocations`, and other tables. This is a one-time backfill/upgrade script invoked via `interfaces/cli/reconcile_canonical_events.py`. It is NOT production runtime code. Excluded from migration scope — it exists to seed historical data and should be replaced or retired as Phase 18.2 migrations make its targets projection-derived.

---

## 7. Architectural Violations

**None found.** The v2 raw layer (`raw_claude_code_events`) is written exclusively by the spool ingestor (`spool/ingestor.py`). The v2 canonical tables (`business_canonical_events`, `ai_canonical_events`) are written exclusively by the ingestor after event type routing.

The pre-v2 `raw_*` tables (raw_sessions, raw_workflow_runs, etc.) are written by `core/event_store/studio_db.py` — this is correct for the legacy system and these are Phase 18.3 migration targets, not violations.

---

## 8. Recommended Phase 18.2.2 Starting Point

### Recommended first batch: W11 + business_work_orders full migration

**Why:** WorkOrderProjection already exists and handles all 5 work order events. The path is:

1. **W11 first (10-minute fix):** Wire `work_order.unblocked` event emission in `unblock_work_order()`. The registry entry exists, the projection handles it, just the emit was missing.
2. **W07-W11 migration:** Remove direct writes from all 5 work order writers. The projection already receives the events and populates business_work_orders. This is the only table where the projection pre-exists.
3. **Validate:** Run `ds work-order create`, `start`, `close`, `block`, `unblock`. Verify business_work_orders still shows correct state (populated by projection, not direct write).

**Why work orders first:** Projection already exists. Pattern proved. Tests already cover the projection path. Validates the removal pattern before building new projections.

### Recommended second batch: business_tasks + business_milestones (Phase 18.2.2 continued)

Both writers already emit correct events. Build TaskProjection and MilestoneProjection following the WorkOrderProjection pattern. Remove direct writes. These are lower complexity than design_briefs (no missing event types) and lower risk than business_projects (no status-change edge cases).

### Recommended third batch: business_design_briefs (Phase 18.2.2 end or 18.2.3 start)

Most work: need 3 new event types in registry, event emission in 4 functions, and a new DesignBriefProjection. Worth doing early because design_brief state is currently invisible to the event stream (no attribution at all — Tier 1).

### Start of Phase 18.2.3: business_projects status-change writers (W02, W03)

Need new event types (`project.activated`, `project.deactivated`). Simple UPDATEs but require new registry entries. Post-migration, the active project dashboard surface depends on projection convergence.

---

## 9. Top 5 Findings That Should Drive Sequencing

1. **WorkOrderProjection already exists** — business_work_orders migration is 80% done. Just remove the direct writes and fix W11. This should be the first PR of Phase 18.2.2.

2. **Design briefs are completely dark** — 4 writers, 0 events, 0 registry entries. No attribution at all for design brief lifecycle. If an operator creates, fills, and locks a brief, it leaves no event trace. Highest-priority gap from an operational visibility standpoint.

3. **unblock_work_order is a 10-line bug fix** — `work_order.unblocked` is in the registry and handled by the projection. The emit call was simply never added to the function. Fix this before anything else.

4. **record_invocation fans to 5 tables in one function** — Migrating hook/tool/skill/agent/workflow invocations is one migration target (Phase 18.5), not five. OD7 governs the hook and tool paths specifically; skill/agent/workflow need standard projection paths. Design the migration of `record_invocation` as a single coordinated change.

5. **Synchronous read-after-write is the real migration blocker** — Several CLI commands read immediately after writing (e.g., `start_work_order` checks for context, `mark_task_done` returns remaining count). The migration must handle this. Recommended: keep the direct read for synchronous CLI feedback; only the write goes away. The projection handles the durable record.

---

*End of Phase 18.2.1 Writer Inventory — 2026-05-23*
