# Phase 18 — Architectural Realignment Roadmap

**Status:** Active
**Date:** 2026-05-22 (updated)
**Author:** SeayInsights / Dannis Seay
**Architecture Reference:** `docs/architecture/data-model-v2.md`
**Audit Reference:** `docs/audits/2026-05-22-full-stock/`

This document is the operational roadmap for executing Dream Studio's architectural realignment to v2. It consolidates the audit findings, the v2 architecture commitment, the eight operator decisions, and discoveries made during execution into a phased workstream plan.

This is a living document. Update it as phases complete, scope shifts, or new discoveries emerge. Future sessions (with the operator or with Claude Code) should reference this to know what's next.

**Update history:**
- 2026-05-22 — Initial commit
- 2026-05-22 — Update 1: Reflect Phase 18.1.1-18.1.6 completion; add Phase 18.1.7 (renames); incorporate 18.1.6 findings (prd_authority harvest, schema enrichment fields); document harvest-before-building principle

---

## Where we are

**Phase 18.0 — Foundation hardening:** DONE (PR #46)
**Phase 18.1.1 — Raw layer infrastructure:** DONE (PR #47)
**Phase 18.1.2 — Dual canonical structure + Event type registry:** DONE (PR #48)
**Phase 18.1.3 — Correlation ID infrastructure:** DONE (PR #49)
**Phase 18.1.6 — Project family reconciliation:** DONE (PR #50) — Approach A chosen (ds_* canonical, project_* retires)
**Phase 18.1.5 — Projection framework:** DONE (PR #51)
**Phase 18.1.7 — ds_* → business_* renames:** DONE (PR #52)
**Phase 18.3.6 — Spool lifecycle policy (OD8):** DONE (PR #53)
**Phase 18.2.1 — Writer inventory:** DONE (PR #54) — 30 writers cataloged; 7 Tier 1, 1 Tier 2, 7 Tier 3, 15 Tier 4; 0 architectural violations

The architecture is committed (v2, amended 3 times). The full audit is complete (16 documents). All 8 operator decisions are resolved. The v2 foundational substrate exists: raw layer, dual canonical, event type registry, correlation IDs, projection framework with first projection.

After 18.1.7 lands, Phase 18.1 is complete. Phase 18.2 (writer migration) becomes the long mechanical work.

---

## Phase structure overview

```
18.0 — Foundation hardening                    [DONE]
   ↓
18.1 — Architectural foundation                [100% COMPLETE]
   ├─ 18.1.1 Raw layer                         [DONE]
   ├─ 18.1.2 Dual canonical + Event registry   [DONE]
   ├─ 18.1.3 Correlation IDs                   [DONE]
   ├─ 18.1.5 Projection framework              [DONE]
   ├─ 18.1.6 Project family reconciliation     [DONE]
   └─ 18.1.7 ds_* → business_* renames         [DONE (PR #52)]
   ↓
   ├─→ 18.2 — Writer migration                 [parallel after 18.1]
   ├─→ 18.3 — File-state migration             [parallel after 18.1]
   ├─→ 18.5 — Telemetry spine completion       [parallel after 18.1]
   ↓
18.4 — Security, product readiness, onboarding  [after 18.1]
   ↓
18.6 — Schema rationalization                  [after 18.2 + 18.3]
   ↓
18.7 — Documentation and cleanup               [final consolidation]
```

The critical path: 18.0 → 18.1 → 18.4 → 18.6 → 18.7. Phases 18.2, 18.3, 18.5 run in parallel after 18.1.

---

## Operating Principles (added during execution)

### Harvest before building

**Origin:** Phase 18.1.6 investigation surfaced that `prd_authority.py` is 1,250+ lines of fully designed PRD lifecycle logic that has never been invoked. Without the investigation, Phase 18.4 would have designed `business_change_orders` from scratch and missed an entire existing implementation.

**Principle:** Before designing new infrastructure in any Phase 18 workstream, check whether existing Dream Studio code already implements the concept (even if unactivated). Harvest > rebuild.

**Application:** This applies especially to Phase 18.4 (Pre-Launch Milestone, change orders, brownfield onboarding). Before each major workstream starts, do a brief investigation pass: "is there existing implementation we can harvest?"

### Daemon operational surface

**Origin:** Phase 18.1.5 introduces the projection runner daemon — the first long-running background process in Dream Studio.

**Implications:**
- Daemon currently starts via `py -m core.projections.runner` (manual or process-manager-configured)
- Lifecycle commands available: `ds projection daemon start/stop/status`
- PID file at `~/.dream-studio/state/projection_runner.pid`
- Configurable via `PROJECTION_POLL_INTERVAL` and `PROJECTION_EVENT_TRIGGER` env vars

**Operational considerations to address in later phases:**
- Phase 18.3: daemon lifecycle integration with Dream Studio's overall lifecycle (install, uninstall, machine startup)
- Phase 18.4: dashboard surface for daemon status, retry queue depth, dead-letter count

### Schema enrichment from project_* family

**Origin:** Phase 18.1.6 found that `project_milestone_records` carries fields (`stage_gate_json`, `validation_expectations_json`, `security_readiness_checks_json`) that `ds_milestones` lacks.

**Implication for Phase 18.4:** The Pre-Launch Milestone (and milestones generally) should incorporate these fields. They provide structured specification of milestone gates beyond simple state tracking. This wasn't obvious before the investigation but is now built into the plan.

---

## Phase 18.0 — Foundation hardening [DONE]

**Status:** Complete. Shipped in PR #46 on 2026-05-22.

**Scope:** Address the 5 Critical findings from the audit synthesis plus M8 (broken self-audit cron).

**Workstreams completed:**

- C1: Created `spool/emitter.py` for broken on-context-threshold hook import
- C2: TTL guards on pending-handoff.json
- C3: Migration 065 removed 23 test fixture rows; `guard_real_homedir` hardened
- C4: Updated `guardrails/evaluator.py` to query canonical_events instead of removed activity_log
- C5: Stale workflow-checkpoint.json TTL guards
- M8: Self-audit cron fixed

**Outcome:** PR #46 merged. 63/63 tests passing. Production DB at exactly 2 rows. All ongoing pollution stopped.

---

## Phase 18.1 — Architectural foundation [100% COMPLETE]

The v2 substrate. After this phase, all subsequent phases have something to build against.

### Workstreams

**18.1.1 — Raw layer infrastructure** [DONE — PR #47]

- Created `raw_claude_code_events` table (migration 066)
- Spool ingestor dual-writes (raw + canonical_events)
- Backfilled 1,909 historical rows
- Drill-down verification working

**18.1.2 — Dual canonical structure + Event type registry** [DONE — PR #48]

- Created `business_canonical_events` and `ai_canonical_events` (migration 067)
- 85-entry event type registry at `config/event_type_registry.py` governs routing
- Backfill: 56 business / 743 AI / 1,139 raw-only / 0 failures
- Per OD2 + OD7: hook telemetry will project from AI canonical at meaningful boundaries (implemented in Phase 18.5)

**18.1.3 — Correlation ID infrastructure** [DONE — PR #49]

- `core/correlation/composer.py` — canonical composition module
- Format: `sess-<id>:wf-<id>:skill-<id>:agent-<id>:hook-<id>:tool-<id>`
- Propagation pattern: caller passes base, callee extends
- Backfill: 756 valid, 2,014 unfixable (historical events lack reconstruction context — known limitation)
- 0 malformed correlation IDs in live DB

**18.1.5 — Projection framework** [DONE — PR #51]

- `core/projections/framework.py` — Projection ABC, RetryPolicy, ProjectionRegistry, ProjectionEngine
- `core/projections/runner.py` — ProjectionRunner daemon (5s/100-event trigger, graceful SIGTERM)
- `core/projections/work_order_projection.py` — first v2 projection (skeleton-row out-of-order pattern, 5-event state machine)
- Migrations 068-069 — projection_state, projection_dead_letter, projection_retry_queue, business_work_orders
- `ds projection` CLI — list, status, rebuild, dead-letter, daemon commands
- Live statistics: 33 events → 14 work orders projected
- 59 new tests + 121 prior Phase 18 tests passing

Framework contracts (enforced by tests): deterministic, idempotent, out-of-order tolerant.

This is the template for every future v2 projection in Phases 18.2, 18.4, 18.5.

**18.1.6 — Project family reconciliation** [DONE — PR #50]

- Investigation document at `docs/architecture/project-family-reconciliation.md`
- **Approach A chosen:** ds_* is canonical; project_* retires after Phase 18.4 builds v2-compliant business_* equivalents
- **Headline finding:** The two families have zero true concept duplicates — they're complementary (operational tracking vs PRD authority specification)
- **prd_authority.py is 1,250+ lines of unactivated infrastructure to harvest** in Phase 18.4 rather than rebuilding change orders from scratch
- `project_milestone_records` carries gate-specification fields that `ds_milestones` lacks — `business_milestones` must incorporate both schemas
- Effort estimate: Large overall (renames touch every CLI/API in Phase 18.6); project_* retirement is small (0 rows)

**18.1.7 — ds_* → business_* renames** [DONE — PR #52]

- **Scope:** Mechanical rename of ds_* tables to business_* naming per Approach A. Also reorganize related CLI commands and API routes that reference these tables. Done now so Phase 18.2 (writer migration) writes to the right names from the start.
- **Workstreams completed:**
  - Schema migration 070 (`070_ds_to_business_renames.sql`) — RENAME TABLE operations on all 6 tables: ds_projects, ds_milestones, ds_work_orders, ds_tasks, ds_design_briefs, ds_work_order_types
  - Skill markdown files updated (ds-project/SKILL.md, ds-project/modes/manage/SKILL.md, core/modes/plan/SKILL.md)
  - Documentation updated (docs/schema/README.md, docs/architecture/project-family-reconciliation.md, docs/MIGRATION_AUTHORITY.md, CHANGELOG.md, this file)
  - All data preserved: 2 projects, 5 milestones, 14 work orders, 9 tasks, 1 design brief, 10 work order types
  - FKs updated via CASCADE on all table renames

### Phase 18.1 exit criteria

- v2 substrate fully operational (raw, dual canonical, correlation IDs, registry, framework, business_* naming)
- First projection running successfully (business_work_orders)
- Daemon operational

After 18.1.7, Phase 18.1 is complete. Phase 18.2-18.5 unlocked.

---

## Phase 18.2 — Writer migration

**Status:** Not started. Runs in parallel after 18.1 lands.

**Scope:** Convert every direct-write path in Dream Studio to the projection model. CLI commands, API endpoints, hooks, and skill code that currently INSERT into structured tables must instead emit canonical events. Projections (built in 18.1.5) populate the structured tables.

### Workstreams

**18.2.1 — Inventory and prioritize writers** [DONE — PR #54]

- **Scope:** Catalog every direct-write call site from the audit. Prioritize by current impact: attribution-broken writers, security-sensitive writers, high-traffic writers.
- **Outcome:** 30 writers across 18 tables. 7 Tier 1 (attribution-broken, including full design_brief dark zone). 1 Tier 2 (security_findings). 7 Tier 3 (execution_spine.py invocation telemetry). 15 Tier 4 (partial migrations with event emission already in place). 0 architectural violations. WorkOrderProjection already handles business_work_orders — Phase 18.2.2 starts by removing those direct writes.
- **Document:** `.planning/18-2-1-writer-inventory.md`

**18.2.2 — Convert tier 1 writers (attribution-broken)**

- **Scope:** Writers identified in audit as producing wrong or missing attribution. Convert to event-emit pattern.
- **Dependencies:** 18.2.1
- **Risk:** Each writer has its own quirks
- **Exit criteria:** All tier 1 writers converted. Attribution validated.

**18.2.3 — Convert tier 2 writers (security-sensitive)**

- **Scope:** Writers touching security findings, audit trails, governance traces. Higher bar for correctness.
- **Dependencies:** 18.2.2 (proves the pattern first)
- **Risk:** Security-sensitive writes need extra validation
- **Exit criteria:** All tier 2 writers converted with security-focused test coverage

**18.2.4 — Convert tier 3 writers (high-traffic)**

- **Scope:** Hook writes (hook_invocations, tool_invocations) and other high-volume direct writes. Per OD7, AI canonical receives summaries, not per-call writes.
- **Dependencies:** 18.2.3
- **Risk:** Volume changes when migrating from direct-write to event-emit
- **Exit criteria:** Hook telemetry projection populated from AI canonical. Tool-level detail in raw.

**18.2.5 — Convert tier 4 writers (remaining)**

- **Scope:** The long tail
- **Dependencies:** 18.2.4
- **Risk:** Mechanical but tedious; easy to miss edge cases
- **Exit criteria:** No direct-write call sites remain in CLI/API/hook/skill code

### Phase 18.2 exit criteria

- Every L3 table populates from projections, not direct writes
- Lint/test rules in place to prevent regression
- Audit shows projection model is the only write path

This phase runs for weeks. Mechanical but high-volume work. Can split across multiple PRs.

---

## Phase 18.3 — File-state migration

**Status:** Not started. Runs in parallel after 18.1 lands.

**Scope:** Migrate the 24 file-based runtime state stores from audit 01l to SQLite per Commitment 5. Implement spool lifecycle policy per OD8. Daemon lifecycle integration.

### Workstreams

**18.3.1 — workflows.json → workflow_runs table**

- **Scope:** Workflow execution state moves to SQLite. Writers emit workflow lifecycle events; projection populates workflow_runs.
- **Dependencies:** 18.1.5 (projection framework)
- **Risk:** Must preserve in-flight workflow state during migration
- **Exit criteria:** workflows.json no longer used at runtime

**18.3.2 — active_task.json → active_task table**

- **Scope:** Active task context moves to SQLite. Hook readers updated.
- **Dependencies:** 18.1.5
- **Risk:** Many hook readers to update
- **Exit criteria:** SQLite is single source of truth for active task

**18.3.3 — JSONL diagnostic files → SQLite tables**

- **Scope:** hook-timing.jsonl, skill-usage.jsonl, telemetry-buffer.jsonl, token-capture.jsonl migrated. Per Commitment 9, summaries in AI canonical; per-tool in raw.
- **Dependencies:** 18.1.5
- **Risk:** High-volume telemetry needs proper indexing
- **Exit criteria:** No JSONL diagnostic files in active use

**18.3.4 — Session files → sessions table**

- **Scope:** Files in `.sessions/` move to SQLite. Session lifecycle becomes event-driven.
- **Dependencies:** 18.1.5
- **Risk:** Markdown content storage schema
- **Exit criteria:** Session lifecycle queryable from SQLite

**18.3.5 — Machine identity and platform → machine_profile table**

- **Scope:** machine_id, platform.json, installed-version migrated.
- **Dependencies:** 18.1.5
- **Risk:** Read early in process startup; SQLite must be available
- **Exit criteria:** Files no longer at runtime

**18.3.6 — Spool lifecycle policy (OD8 implementation)**

- **Scope:** Weekly + yearly archive cron jobs for `~/.dream-studio/spool/processed/`. Verify-then-delete pattern.
- **Dependencies:** None
- **Risk:** Archive verification must be airtight
- **Exit criteria:** Weekly + yearly archives running. Disaster recovery path tested.

**18.3.7 — Daemon lifecycle integration**

- **Scope:** Projection runner daemon integrated with Dream Studio lifecycle. Auto-start on install/login, clean shutdown on uninstall, status visibility.
- **Dependencies:** 18.1.5 (daemon exists)
- **Risk:** Platform-specific (Windows scheduled task vs systemd vs launchd)
- **Exit criteria:** Operator doesn't need to manually start daemon after install

**18.3.8 — Remaining file-state stores**

- **Scope:** Long tail from audit 01l
- **Dependencies:** 18.1.5
- **Exit criteria:** Only legitimate file-based state remains

### Phase 18.3 exit criteria

- All 24 file-based runtime stores migrated to SQLite
- Spool lifecycle operational
- Daemon lifecycle integrated

---

## Phase 18.4 — Security, product readiness, and onboarding

**Status:** Not started. The big feature phase. Starts after 18.1 complete.

**Scope:** Build the Pre-Launch Milestone (OD4). Compile catalogs. Wire ds-security skill suite as the security audit engine. Wire product readiness workflow. Implement the triage step. Build brownfield onboarding.

### Workstreams

**18.4.1 — Compile security audit catalog**

- **Scope:** Document the 47 enterprise security checks as `docs/architecture/security-audit-catalog.md`. Each check gets: description, role assignment (A/B/C/D), execution mechanism, finding schema, severity criteria.
- **Dependencies:** None
- **Exit criteria:** Catalog document with all 47 checks specified

**18.4.2 — Compile product readiness catalog**

- **Scope:** Industry-standard product readiness checks at `docs/architecture/product-readiness-catalog.md`. Similar structure.
- **Dependencies:** None
- **Risk:** Less reference material; need to compile from multiple standards
- **Exit criteria:** Catalog document exists

**18.4.3 — Security audit workflow implementation**

- **Scope:** Implement `security-audit.yaml` using existing ds-security skill suite (scan, review, dast, binary-scan, mitigate, comply, netcompat — minus retired dashboard mode). v2-align each skill to emit canonical events.
- **Dependencies:** 18.4.1, 18.1.5
- **Risk:** ds-security suite is file-based; v2 alignment is real work
- **Exit criteria:** security-audit.yaml runs end-to-end. Findings in business_security_findings.

**18.4.4 — Product readiness workflow implementation**

- **Scope:** Implement `product-readiness.yaml`. More net-new than 18.4.3.
- **Dependencies:** 18.4.2, 18.1.5
- **Risk:** Substantial net-new skill work
- **Exit criteria:** product-readiness.yaml runs end-to-end

**18.4.5 — Triage skill (Pre-Launch Milestone WO3)**

- **Scope:** New skill — `ds-triage:findings`. Reads findings from any audit. Walks operator through accept/fix/defer. Emits change_order events.
- **Dependencies:** 18.4.3, 18.4.4
- **Risk:** UX matters; bad triage flow makes milestone painful
- **Exit criteria:** Triage skill efficient even with dozens of findings

**18.4.6 — Change order entity (HARVEST FROM prd_authority.py)**

- **Scope:** Implement `business_change_orders` table as projection. **Harvest from `prd_authority.py` (1,250+ lines of unactivated infrastructure per 18.1.6 finding) rather than designing from scratch.** Wire change-orders-to-work-orders flow.
- **Dependencies:** 18.4.5 (need triage skill to produce change orders)
- **Risk:** prd_authority.py may need updates to align with v2 (it pre-dates the dual canonical decision)
- **Exit criteria:** business_change_orders populated correctly. Approved change orders generate work orders.

**18.4.7 — Lightweight scan at PRD intake**

- **Scope:** Combined lightweight scanner during `ds-project scope` PRD intake. Covers both security and product readiness in lightweight form.
- **Dependencies:** 18.4.3, 18.4.4
- **Risk:** Must be fast (<30s)
- **Exit criteria:** Lightweight scan runs in <30s. Findings surface at milestone review.

**18.4.8 — Pre-Launch Milestone integration**

- **Scope:** Wire all of the above into milestone structure. Pre-Launch Milestone auto-generated during PRD intake. WO1-WO5 sequence. Skip-to-deferred. **Incorporates schema enrichment from project_milestone_records (stage_gate_json, validation_expectations_json, security_readiness_checks_json) into business_milestones.**
- **Dependencies:** 18.4.3, 18.4.4, 18.4.5, 18.4.6, 18.4.7
- **Risk:** Integration complexity
- **Exit criteria:** New project intake produces Pre-Launch Milestone that walks through both audits and triage

**18.4.9 — Brownfield onboarding workflow**

- **Scope:** Build the missing brownfield import. Operator brings existing project into Dream Studio; ds-analyze creates PRD draft, milestones, work orders from codebase analysis.
- **Dependencies:** 18.4.7, 18.1 substrate, harvest investigation (check existing infrastructure)
- **Risk:** Big feature; lots of net-new capability
- **Exit criteria:** `ds project import <repo>` produces structured project from codebase

**18.4.10 — ds-security:review pre-commit/pre-PR wiring**

- **Scope:** Per OD6, wire ds-security:review as hook on pre-commit and pre-PR.
- **Dependencies:** 18.4.3
- **Risk:** Hook performance
- **Exit criteria:** Pre-commit and pre-PR security review running

### Phase 18.4 exit criteria

- Pre-Launch Milestone is default for new projects
- Both audits run end-to-end
- Findings flow through triage to change orders to work orders
- Brownfield onboarding works
- Catalogs documented
- ds-security:review wired for continuous coverage

---

## Phase 18.5 — Telemetry spine completion

**Status:** Not started. Parallel after 18.1.

**Scope:** Complete v2 migration for hook and tool telemetry per OD7.

### Workstreams

**18.5.1 — AI canonical event design for hooks**

- **Scope:** Define event_type and payload structure for hook events. Granularity rule: one per hook execution (start/complete/error), NOT per tool call.
- **Dependencies:** 18.1.4 (event type registry)
- **Exit criteria:** Event types registered. Payload schema defined.

**18.5.2 — Hook emitter migration**

- **Scope:** Update hook code to emit canonical events at boundaries. Stop direct INSERT into hook_invocations.
- **Dependencies:** 18.5.1
- **Exit criteria:** No direct writes to hook_invocations from hook code

**18.5.3 — hook_invocations projection**

- **Scope:** Projection reading AI canonical hook events, populating hook_invocations.
- **Dependencies:** 18.5.2, 18.1.5
- **Exit criteria:** hook_invocations populated entirely via projection

**18.5.4 — Tool telemetry to raw**

- **Scope:** Per-tool detail in raw_claude_code_events with indexes. tool_invocations either dropped or repurposed.
- **Dependencies:** 18.1.1
- **Exit criteria:** Tool-level detail queryable via raw

**18.5.5 — Telemetry projection completeness**

- **Scope:** All telemetry pipelines (skill_invocations, agent_invocations, workflow nodes) via projection.
- **Dependencies:** 18.5.2
- **Exit criteria:** Telemetry-related L3 tables all populated via projection

### Phase 18.5 exit criteria

- Hook telemetry uses event-emit + projection pattern
- Per-tool detail in raw, accessible via correlation_id
- No direct-write paths remain for telemetry

---

## Phase 18.6 — Schema rationalization

**Status:** Not started. After 18.2 + 18.3 substantially complete.

**Scope:** Execute OD3 decisions. Drop tables marked for retirement. Drop project_* family (per 18.1.6 Approach A). Verify keep tables populating correctly.

### Workstreams

**18.6.1 — Drop retired tables (OD3 drop list)**

- **Scope:** Execute migration to drop ~73 tables across domains: career (14), alerting (2), generic monitoring (5), research (5), advanced execution graph (3), authority/capability framework (5), artifact tracking (2), process_runs (1), decision/governance (5), learning (4), raw legacy (4), session_tasks (1), tool registry (2), connector/ingestion (3), demo (1), misc operational (9), and similar.
- **Dependencies:** Verify no remaining code references
- **Risk:** Hidden dependencies
- **Exit criteria:** Migration drops listed tables. Tests pass.

**18.6.2 — Drop project_* family**

- **Scope:** Per 18.1.6 Approach A, drop the project_* family after Phase 18.4 builds v2-compliant equivalents. 0 rows so trivially small migration.
- **Dependencies:** Phase 18.4 complete (business_* equivalents exist)
- **Exit criteria:** project_* tables dropped

**18.6.3 — Verify keep tables populated**

- **Scope:** For tables in OD3 keep list, verify they're populated by their planned writers.
- **Dependencies:** 18.2, 18.3 substantially complete
- **Exit criteria:** Keep tables either populated or have documented reason for being empty

**18.6.4 — View and index cleanup**

- **Scope:** Drop orphan views and indexes. Add missing indexes from audit.
- **Dependencies:** 18.6.1, 18.6.2
- **Exit criteria:** Schema consistent

**18.6.5 — Final schema audit**

- **Scope:** Re-run schema introspection. Compare to v2 target.
- **Dependencies:** 18.6.1-18.6.4
- **Exit criteria:** Schema audit shows v2 compliance

### Phase 18.6 exit criteria

- ~73 tables dropped per OD3
- project_* family dropped
- Keep tables verified
- Schema aligned with v2

---

## Phase 18.7 — Documentation and cleanup

**Status:** Not started. Final consolidation.

**Scope:** Update documentation. Handle Phase 16A contracts per OD5. Compile AI governance framework document.

### Workstreams

**18.7.1 — Phase 16A contracts handling (OD5)**

- **Scope:** Per-contract hybrid: rewrite contracts describing surviving semantics, retire pure storage layouts.
- **Dependencies:** v2 implementations exist
- **Exit criteria:** All six contracts handled

**18.7.2 — Compile AI governance framework document**

- **Scope:** Create `docs/architecture/ai-governance-framework.md`. Stripped-down generalized version of NIST AI RMF + ISO 42001. Each governance question maps to architecture component that answers it.
- **Dependencies:** None
- **Exit criteria:** Document exists; questions map to queryable answers

**18.7.3 — Update pre-v2 documentation**

- **Scope:** Per audit 01h, update or archive documentation describing pre-v2 patterns.
- **Dependencies:** None
- **Exit criteria:** Documentation review shows no pre-v2 patterns described as canonical

**18.7.4 — Retire dashboard mode (ds-security:dashboard)**

- **Scope:** Per OD6 acknowledgment, retire Power BI dataset generation. Dashboard reads from SQLite projections.
- **Dependencies:** 18.4.3
- **Exit criteria:** Mode removed

**18.7.5 — Phase 18 retrospective and v3 forecast**

- **Scope:** Document what worked, what didn't, identify v3 candidates.
- **Dependencies:** All prior phases substantially complete
- **Exit criteria:** Retrospective document exists

### Phase 18.7 exit criteria

- All v1/v2 transition documentation completed
- Phase 16A contracts handled
- AI governance framework document exists
- Pre-v2 patterns no longer present
- Retrospective captured

---

## Master workstream index

| Workstream | Phase | Status |
|---|---|---|
| Test isolation hardening | 18.0 | DONE |
| Stale handoff cleanup | 18.0 | DONE |
| Broken imports fixed | 18.0 | DONE |
| Test fixture contamination | 18.0 | DONE |
| Guardrails evaluator | 18.0 | DONE |
| Self-audit cron | 18.0 | DONE |
| Raw layer infrastructure | 18.1.1 | DONE (PR #47) |
| Dual canonical structure | 18.1.2 | DONE (PR #48) |
| Event type registry | 18.1.4 | DONE (embedded in #48) |
| Correlation ID infrastructure | 18.1.3 | DONE (PR #49) |
| Project family reconciliation | 18.1.6 | DONE (PR #50) |
| Projection framework | 18.1.5 | DONE (PR #51) |
| ds_* → business_* renames | 18.1.7 | NEXT |
| Writer inventory | 18.2.1 | DONE (PR #54) |
| Tier 1 writer migration (attribution) | 18.2.2 | Not started |
| Tier 2 writer migration (security) | 18.2.3 | Not started |
| Tier 3 writer migration (high-traffic) | 18.2.4 | Not started |
| Tier 4 writer migration (remaining) | 18.2.5 | Not started |
| workflows.json → workflow_runs | 18.3.1 | Not started |
| active_task.json → SQLite | 18.3.2 | Not started |
| JSONL diagnostics → SQLite | 18.3.3 | Not started |
| Session files → SQLite | 18.3.4 | Not started |
| Machine identity → SQLite | 18.3.5 | Not started |
| Spool lifecycle (OD8) | 18.3.6 | DONE (PR #53) |
| Daemon lifecycle integration | 18.3.7 | Not started |
| Remaining file-state | 18.3.8 | Not started |
| Security audit catalog | 18.4.1 | Not started |
| Product readiness catalog | 18.4.2 | Not started |
| security-audit.yaml | 18.4.3 | Not started |
| product-readiness.yaml | 18.4.4 | Not started |
| Triage skill | 18.4.5 | Not started |
| Change order entity (harvest prd_authority) | 18.4.6 | Not started |
| Lightweight scan at intake | 18.4.7 | Not started |
| Pre-Launch Milestone integration | 18.4.8 | Not started |
| Brownfield onboarding | 18.4.9 | Not started |
| Pre-commit/PR security review | 18.4.10 | Not started |
| AI canonical event design (hooks) | 18.5.1 | Not started |
| Hook emitter migration | 18.5.2 | Not started |
| hook_invocations projection | 18.5.3 | Not started |
| Tool telemetry to raw | 18.5.4 | Not started |
| Telemetry projection completeness | 18.5.5 | Not started |
| Drop retired tables (OD3) | 18.6.1 | Not started |
| Drop project_* family | 18.6.2 | Not started |
| Verify keep tables populated | 18.6.3 | Not started |
| View and index cleanup | 18.6.4 | Not started |
| Final schema audit | 18.6.5 | Not started |
| Phase 16A contracts handling | 18.7.1 | Not started |
| AI governance framework document | 18.7.2 | Not started |
| Update pre-v2 documentation | 18.7.3 | Not started |
| Retire dashboard mode | 18.7.4 | Not started |
| Phase 18 retrospective | 18.7.5 | Not started |

---

## Decisions reference

The 8 operator decisions made during architecture work, plus discoveries during execution:

| Decision | Summary | Affects |
|---|---|---|
| **OD1** | Security findings to SQLite only; deliverables generated on-demand. `sec_sarif_findings` retired. | 18.4.3, 18.4.6 |
| **OD2** | Dual canonical resolves volume concern. hook_invocations projection-populated. | 18.1.2, 18.5 |
| **OD3** | Drop ~73 tables; keep ~68; project_* family reconciliation in 18.1.6. | 18.1.6, 18.6 |
| **OD4** | Pre-Launch Milestone with security + product readiness audits. Lightweight scan + skip-to-deferred. Change orders as first-class. | 18.4 entire |
| **OD5** | Phase 16A contracts: per-contract hybrid. | 18.7.1 |
| **OD6** | ds-security:review as diff scanner. ds-security suite is security-audit engine. Triage skill new in 18.4.5. | 18.4.3, 18.4.5, 18.4.10 |
| **OD7** | hook_invocations projection-derived from AI canonical. | 18.5.3 |
| **OD8** | Weekly + yearly spool archives, calendar-aligned. | 18.3.6 |
| **18.1.6 finding** | Approach A: ds_* canonical, project_* retires. prd_authority.py to harvest. Schema enrichment fields for milestones. | 18.1.7, 18.4.6, 18.4.8 |

---

## Update protocol

This document is updated as phases complete and decisions are made.

When a phase or workstream completes:
1. Update status in the relevant phase section
2. Update status in the master workstream index
3. Add any retrospective notes that should propagate forward

When a new decision or discovery emerges:
1. Add it to the decisions reference (or operating principles)
2. Note which phases/workstreams it affects
3. Update the affected phase sections

When scope shifts:
1. Document why
2. Update affected sections
3. Re-evaluate phase exit criteria

Drift between this document and reality is the failure mode this document exists to prevent.

---

*End of Phase 18 Roadmap — updated 2026-05-22*
