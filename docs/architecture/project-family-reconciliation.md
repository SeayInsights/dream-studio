# Project Entity Family Reconciliation

**Phase:** 18.1.6  
**Status:** EXECUTED — Phase 18.1.7 (migration 070) renamed all ds_* tables to business_* naming  
**Date:** 2026-05-22  
**Author:** SeayInsights / Dannis Seay  
**Architecture Reference:** `.planning/data-model-v2.md`  
**Audit Reference:** `docs/audits/2026-05-22-full-stock/01b-database-audit.md`

This document records the investigation, decision, and migration plan for reconciling Dream Studio's two parallel table families: `ds_*` and `project_*`. It is the output artifact of Phase 18.1.6 and the authoritative source for naming and migration decisions in Phases 18.4 and 18.6.

---

## Background

The Phase 1b database audit (2026-05-22) flagged two parallel table families operating in the same database:

- **`ds_*` family** — 8 core tables (plus FTS shadows). Has live data. Backs every active CLI command.
- **`project_*` family** — 8 tables. All have 0 rows. Has an active writer module that has never been invoked in production.

The v2 architecture (`.planning/data-model-v2.md` Commitment 3) mandates `business_*` naming for all hub-and-spoke L3 tables. Neither family is v2-compliant by name. The question was not just _which family wins_ but _what should the v2 `business_*` tables look like and where does each family fit in the migration path?_

---

## Piece 1 — Complete Enumeration

### 1a. `ds_*` Family

| Table | Rows | Migration Origin | Purpose |
|-------|------|-----------------|---------|
| `ds_projects` | 2 (real) | 048 `project_spine.sql` | SDLC project entity. UUID PK. Drives all project-scoped operations. |
| `ds_milestones` | 4 | 048 `project_spine.sql` | Operational milestone tracking. FK → ds_projects. Has order_index. |
| `ds_work_orders` | 14 | 048 `project_spine.sql` | Work order lifecycle (open/in_progress/blocked/complete). FK → ds_milestones, ds_projects. |
| `ds_tasks` | 9 | 048 `project_spine.sql` | Task records per work order. FK → ds_work_orders, ds_projects. |
| `ds_design_briefs` | 1 | 053 `design_brief.sql` | Design brief per project (draft/locked). Stores UX/brand fields. |
| `ds_documents` | 12 | 007 `document_system.sql` | Generic document store (architecture_decision, session_handoff). FTS5 backed. |
| `ds_work_order_types` | 10 | 049 `work_order_type.sql` | Static type registry. Defines gates, executors, templates per type. |
| `ds_technology_signals` | 54 | 055 `technology_signals.sql` | File extension counts from session harvesting. Last-write intelligence. |

**Last-write evidence:** All ds_* tables were written to during the 2026-05-22 audit session and remain active.

**Active writers:**

| Table | Writer file | Operation |
|-------|------------|-----------|
| `ds_projects` | `core/projects/mutations.py` | INSERT, UPDATE status, DELETE |
| `ds_milestones` | `core/milestones/mutations.py`, `core/milestones/close.py` | INSERT, UPDATE status |
| `ds_work_orders` | `core/work_orders/mutations.py`, `core/work_orders/start.py`, `core/work_orders/close.py` | INSERT, UPDATE status/block |
| `ds_tasks` | `core/work_orders/mutations.py` | INSERT, UPDATE status |
| `ds_design_briefs` | `core/design_briefs/mutations.py` | INSERT, UPDATE fields, UPDATE status |
| `ds_documents` | `core/storage/document_store.py`, `spool/session_harvester.py` | INSERT, UPDATE |
| `ds_work_order_types` | Seeded at migration init only | No live writers |
| `ds_technology_signals` | `spool/session_harvester.py` | UPSERT (INSERT OR IGNORE ON CONFLICT) |

**Active readers:**

| Table | Reader file | Purpose |
|-------|------------|---------|
| `ds_projects` | `core/projects/queries.py`, `core/work_orders/start.py`, `core/work_orders/close.py` | Project listing, state queries, WO context |
| `ds_milestones` | `core/milestones/queries.py`, `core/projects/queries.py`, `core/work_orders/start.py`, `core/work_orders/close.py`, `core/milestones/close.py` | Milestone listing, project state, WO ordering |
| `ds_work_orders` | `core/work_orders/queries.py`, `core/projects/queries.py`, `core/work_orders/start.py`, `core/work_orders/close.py`, `core/milestones/close.py` | WO listing, state queries, next-WO resolution |
| `ds_tasks` | `core/work_orders/queries.py`, `core/work_orders/mutations.py`, `core/projects/queries.py`, `core/work_orders/start.py` | Task listing, completion tracking |
| `ds_design_briefs` | `core/design_briefs/queries.py`, `core/projects/queries.py`, `core/work_orders/start.py` | Brief state, gate checking, context loading |
| `ds_documents` | `core/storage/document_store.py`, `core/work_orders/close.py` | Document search/retrieval, gate fallback |
| `ds_work_order_types` | `core/work_orders/start.py`, `core/work_orders/close.py`, `core/projects/queries.py` | Gate definitions, executor resolution, template lookup |
| `ds_technology_signals` | No active readers found | Populated but unqueried in current SDLC paths |

---

### 1b. `project_*` Family

| Table | Rows | Migration Origin | Purpose |
|-------|------|-----------------|---------|
| `project_intake_records` | 0 | 047 `prd_lifecycle_authority.sql` | PRD intake session record. Captures question_mode, project_type, autonomy_level, security_classification, critical_blockers, assumptions. |
| `project_intake_questions` | 0 | 047 `prd_lifecycle_authority.sql` | Per-question records within an intake session. Tracks criticality, answer status, inferred vs operator responses. |
| `project_assumption_records` | 0 | 047 `prd_lifecycle_authority.sql` | Assumptions extracted during intake or PRD authoring. FK to intake_id and prd_id. Evidence-ref tracked. |
| `project_change_order_records` | 0 | 047 `prd_lifecycle_authority.sql` | PRD change order records. Rich schema: 26+ columns covering affected_milestones, affected_work_orders, risk_classification, validation_impact, approval_requirement. |
| `project_work_order_authority_records` | 0 | 047 `prd_lifecycle_authority.sql` | Authority specification for a work order. Scope, approved_surfaces, stop_gates, final_verdict_taxonomy. Complementary to ds_work_orders (authority vs operational). |
| `project_milestone_records` | 0 | 047 `prd_lifecycle_authority.sql` | Authority specification for a milestone. Stage gates, validation expectations, security readiness checks, evidence requirements. Complementary to ds_milestones. |
| `project_health_scorecards` | 0 | 040 `production_readiness_authority.sql` | Health assessment scores with confidence, missing evidence, blocking factors. |
| `project_readiness_scorecards` | 0 | 040 `production_readiness_authority.sql` | Readiness assessment scores with confidence, missing evidence, blocking factors. |

**Active writers:**

| Table | Writer file | Operation | Note |
|-------|------------|-----------|------|
| `project_intake_records` | `core/shared_intelligence/prd_authority.py` | INSERT | Never called in production — 0 rows |
| `project_intake_questions` | `core/shared_intelligence/prd_authority.py` | INSERT | Never called in production — 0 rows |
| `project_assumption_records` | `core/shared_intelligence/prd_authority.py` | INSERT | Never called in production — 0 rows |
| `project_change_order_records` | `core/shared_intelligence/prd_authority.py` | INSERT | Never called in production — 0 rows |
| `project_work_order_authority_records` | `core/shared_intelligence/prd_authority.py` | INSERT | Never called in production — 0 rows |
| `project_milestone_records` | `core/shared_intelligence/prd_authority.py` | INSERT | Never called in production — 0 rows |
| `project_health_scorecards` | Production readiness module (stubs) | INSERT (stubbed) | Writer exists but not wired |
| `project_readiness_scorecards` | Production readiness module (stubs) | INSERT (stubbed) | Writer exists but not wired |

**Active readers (post Phase 18.6.2):**

| Table | Reader file | Purpose |
|-------|------------|---------|
| `prd_version_records` (and other staying prd_* tables) | `core/shared_intelligence/prd_authority.py` | `project_prd_authority_summary()` — guarded; returns empty state when project_* tables absent |

`context_packet_prd_authority()` removed in Phase 18.6.2 (vestigial chain — tables 0 rows, stop_gates/forbidden_context never enforced).
`core/analytics_ingestion.py` SECTION_TABLES references to `project_health_scorecards` / `project_readiness_scorecards` removed in Phase 18.6.2.

**Status as of Phase 18.6.2 (migration 099):** All 8 project_* tables dropped. Writers removed from prd_authority.py. prd_authority.py reduced from 1,250+ lines to ~716 lines. See `.planning/specs/prd-authority-harvest-preflight.md` and `.planning/specs/contract-atlas-prd-authority-removal-preflight.md` for the full investigation.

---

## Piece 2 — Concept Overlap Map

| Concept | `ds_*` table | `project_*` table | v2 placement | Overlap verdict |
|---------|-------------|-------------------|-------------|-----------------|
| Project | `ds_projects` | — | `business_projects` | No overlap — ds_* only |
| Milestone (operational tracking) | `ds_milestones` | — | evolves into `business_milestones` | No overlap — ds_* only |
| Milestone (authority specification) | — | `project_milestone_records` | input schema for `business_milestones` | No overlap — project_* only. Complementary concept, not duplicate. |
| Work order (operational tracking) | `ds_work_orders` | — | evolves into `business_work_orders` | No overlap — ds_* only |
| Work order (authority specification) | — | `project_work_order_authority_records` | input schema for `business_work_orders` | No overlap — project_* only. Complementary concept, not duplicate. |
| Task | `ds_tasks` | — | `business_tasks` | No overlap — ds_* only |
| Design brief | `ds_design_briefs` | — | `business_design_briefs` | No overlap — ds_* only |
| Document store | `ds_documents` | — | `business_documents` | No overlap — ds_* only |
| Work order type registry | `ds_work_order_types` | — | `business_work_order_types` | No overlap — ds_* only |
| Technology signals | `ds_technology_signals` | — | `raw_technology_signals` (or `business_technology_signals`) | No overlap — ds_* only |
| Change order | — | `project_change_order_records` | `business_change_orders` | No overlap — project_* only. Required by v2/OD4. |
| Intake record | — | `project_intake_records` | `business_intake_records` | No overlap — project_* only. Required by v2 brownfield onboarding (18.4.9). |
| Intake questions | — | `project_intake_questions` | `business_intake_questions` | No overlap — project_* only. Required by v2 PRD intake flow. |
| Assumption records | — | `project_assumption_records` | `business_assumption_records` | No overlap — project_* only. Required by v2 intake flow. |
| Health scorecard | — | `project_health_scorecards` | `business_health_scorecards` | No overlap — project_* only. Required by v2 Pre-Launch Milestone (OD4). |
| Readiness scorecard | — | `project_readiness_scorecards` | `business_readiness_scorecards` | No overlap — project_* only. Required by v2 Pre-Launch Milestone (OD4). |

### Surprising finding: no true duplicates

**The two families do not actually overlap on any concept.** The apparent overlap on "milestones" and "work orders" is a false positive:

- `ds_milestones` is an *operational tracking record* — status transitions, ordering, date tracking.
- `project_milestone_records` is an *authority specification* — what gates must pass, what validation is expected, what evidence is required. It carries `stage_gate_json`, `validation_expectations_json`, `security_readiness_checks_json`, `evidence_requirements_json`, and `adapter_context_requirements_json`.

These serve fundamentally different purposes. In v2, `business_milestones` should carry *both* the operational state (from `ds_milestones`) and the authority specification (from `project_milestone_records`) as it is projected from business canonical events that encode both. The same analysis applies to work orders.

### v2 concept gaps (concepts neither family addresses today)

The v2 architecture documents several concepts that have no table in either family yet:

| v2 Concept | Current gap | Phase that closes it |
|-----------|------------|---------------------|
| PRD documents | `prd_documents` table exists (migration 047) but in PRD namespace, 0 rows | 18.4 — ds-project scope activation |
| PRD version records | `prd_version_records` exists, 0 rows | 18.4 |
| Security findings (v2 business) | No `business_security_findings` yet — `sec_sarif_findings` / `security_findings` exist but are legacy | 18.4.3 |
| Product readiness findings | `production_readiness_findings` exists, 0 rows | 18.4.4 |
| Spool lifecycle tables | Not yet implemented | 18.3.6 |

These gaps are noted for the Phase 18.4 team but are out of scope for 18.1.6.

---

## Piece 3 — Decision Recommendation

**Decision: Approach A — `ds_*` is the canonical operational layer; `project_*` tables retire after v2 `business_*` equivalents are built in Phase 18.4.**

### Rationale

**1. The v2 architecture document already chose Approach A implicitly.**

`data-model-v2.md` (Change Orders section, line 444-446) states:
> "`business_change_orders` table (the target; legacy `project_change_order_records` may be the migration source — to be reconciled per Phase 18.1 work)"

This language — "legacy" source, `business_*` as the "target" — reflects Approach A thinking. The architecture document does not say "rename `project_change_order_records` to `business_change_orders`." It says build `business_change_orders` and decide whether to use `project_change_order_records` as the migration source. Since `project_change_order_records` has 0 rows, no migration is needed.

**2. Commitment 1 (projection model) makes `project_*` rename non-viable.**

v2 Commitment 1: "Writers do not write to hub-and-spoke tables directly. Writers emit canonical events. Projections populate hub-and-spoke."

`prd_authority.py` writes directly to `project_*` tables — this is a Commitment 1 violation. Renaming `project_*` to `business_*` would just be renaming violating tables. The correct v2 approach is to:
- Build new `business_*` tables as proper projection targets
- Migrate `prd_authority.py` logic to emit canonical events
- Retire the old direct-write pattern

**3. `ds_*` tables ARE the projection-ready operational layer.**

`ds_*` tables have live data and active code paths. Phase 18.2 (writer migration) will convert their writers to emit canonical events → projection. The tables themselves survive with renames in Phase 18.6.

**4. No data migration needed for `project_*` retirement.**

All 8 `project_*` tables have 0 rows. Retiring them requires only DDL (DROP TABLE) and code path removal — no data movement.

**5. `project_*` schemas are preserved as design reference, not as migration source.**

`prd_authority.py` represents sophisticated PRD lifecycle design — intake questions with criticality tracking, rich change order schema, evidence refs. This logic should be harvested by Phase 18.4 when building `business_*` tables, not discarded. The schemas inform v2 table design; they don't need to survive as-is.

### Trade-offs

| Trade-off | Approach A | Approach C (hybrid rename) |
|-----------|-----------|--------------------------|
| Compliance with v2 naming | Full — fresh `business_*` tables designed for projection model | Partial — renamed tables still carry direct-write history |
| prd_authority.py investment | Preserved in Phase 18.4 rebuild; logic harvested | Preserved by rename but still violates Commitment 1 |
| Data migration risk | None — 0 rows in project_* | None — 0 rows (same for this family) |
| ds_* code path disruption | Renames in Phase 18.6 (medium effort) | Same in both approaches |
| Schema purity | Clean v2 tables from day one | Carries historical v1 schema patterns |
| Phase 18.4 build effort | Must build 6 new business_* tables | Saves 6 table builds but inherits v1 direct-write pattern |

Approach A is recommended because schema purity and Commitment 1 compliance outweigh the modest Phase 18.4 build cost — especially when `prd_authority.py` must be rewritten anyway to comply with the projection model.

---

## Piece 4 — Migration Plan Sketch

This is a plan sketch only. No DDL executes in this PR. Phases 18.4 and 18.6 execute against this plan.

### New `business_*` tables to create

**Phase 18.4 creates (net-new, projection-populated):**

| New table | Source schema reference | Phase workstream |
|-----------|------------------------|-----------------|
| `business_change_orders` | `project_change_order_records` schema + `prd_authority.py:create_project_change_order()` logic | 18.4.6 |
| `business_intake_records` | `project_intake_records` schema + `prd_authority.py:record_project_intake()` logic | 18.4.9 (brownfield onboarding) or 18.4.8 |
| `business_intake_questions` | `project_intake_questions` schema | 18.4.9 or 18.4.8 |
| `business_assumption_records` | `project_assumption_records` schema | 18.4.9 or 18.4.8 |
| `business_health_scorecards` | `project_health_scorecards` schema | 18.4.4 (product readiness) |
| `business_readiness_scorecards` | `project_readiness_scorecards` schema | 18.4.4 |

**Phase 18.6 renames (ds_* → business_*, with schema evolution):**

| Old name | New name | Schema evolution notes |
|----------|----------|----------------------|
| `ds_projects` | `business_projects` | No schema change needed |
| `ds_milestones` | `business_milestones` | Add fields from `project_milestone_records` (stage_gate_json, validation_expectations_json, security_readiness_checks_json, evidence_requirements_json) per Phase 18.6 schema evolution |
| `ds_work_orders` | `business_work_orders` | Add fields from `project_work_order_authority_records` (scope_json, approved_surfaces_json, stop_gates_json, final_verdict_taxonomy_json) per Phase 18.6 schema evolution |
| `ds_tasks` | `business_tasks` | No schema change needed |
| `ds_design_briefs` | `business_design_briefs` | No schema change needed |
| `ds_documents` | `business_documents` | No schema change needed |
| `ds_work_order_types` | `business_work_order_types` | No schema change needed |
| `ds_technology_signals` | `raw_technology_signals` | Move to raw_* namespace since it is source-specific operational intelligence, not a planned SDLC entity |

### Existing tables to drop

**Phase 18.6 drops (all have 0 rows, no data migration needed):**

| Table | Migration that created it | Replacement |
|-------|--------------------------|-------------|
| `project_intake_records` | 047 | `business_intake_records` (built in 18.4) |
| `project_intake_questions` | 047 | `business_intake_questions` (built in 18.4) |
| `project_assumption_records` | 047 | `business_assumption_records` (built in 18.4) |
| `project_change_order_records` | 047 | `business_change_orders` (built in 18.4) |
| `project_work_order_authority_records` | 047 | Folded into `business_work_orders` schema |
| `project_milestone_records` | 047 | Folded into `business_milestones` schema |
| `project_health_scorecards` | 040 | `business_health_scorecards` (built in 18.4) |
| `project_readiness_scorecards` | 040 | `business_readiness_scorecards` (built in 18.4) |

Note: Drop occurs AFTER Phase 18.4 builds the replacement tables. Phase 18.6.1 executes the DROP statements.

### Code paths needing update

**Phase 18.4 (alongside new table builds):**

- `core/shared_intelligence/prd_authority.py` — rewrite to emit canonical events rather than direct writes. The `PRD_AUTHORITY_SOURCE_TABLES` constant references 11 tables; update to reference `business_*` equivalents. This is medium effort — 1,250 lines with complex write logic.
- `projections/api/routes/shared_intelligence.py` — update `project_prd_authority_summary()` to query `business_*` tables.
- `core/analytics_ingestion.py` — update `SECTION_TABLES` constant from `project_health_scorecards` / `project_readiness_scorecards` to `business_health_scorecards` / `business_readiness_scorecards`.

**Phase 18.6 (alongside ds_* renames):**

- `core/projects/mutations.py` and `queries.py` — table references ds_projects → business_projects
- `core/milestones/mutations.py`, `close.py`, `queries.py` — ds_milestones → business_milestones
- `core/work_orders/mutations.py`, `start.py`, `close.py`, `queries.py` — ds_work_orders → business_work_orders
- `core/design_briefs/mutations.py`, `queries.py` — ds_design_briefs → business_design_briefs
- `core/storage/document_store.py` — ds_documents → business_documents
- `spool/session_harvester.py` — ds_technology_signals → raw_technology_signals (namespace change)
- All `interfaces/cli/` commands that reference ds_* tables by name
- All `projections/api/routes/` that JOIN or query ds_* tables
- All migration files that reference ds_* names in comments (for documentation clarity)

### Rough size of effort

| Phase | Work type | Effort estimate |
|-------|-----------|----------------|
| 18.1.6 (this PR) | Investigation + decision document | Complete |
| 18.4.6 | Build business_change_orders + change order event flow | Medium |
| 18.4.8/.9 | Build business_intake_records/questions/assumptions | Medium |
| 18.4.4 | Build business_health/readiness_scorecards | Small-Medium |
| 18.4 — prd_authority rewrite | Migrate prd_authority.py to event-emit model | Medium-Large |
| 18.6 — ds_* renames | Schema migration + all code references updated | Large |
| 18.6.1 — project_* drops | DROP TABLE statements + code cleanup | Small (0 rows, minimal code paths) |

Overall migration size: **Large** — mostly because ds_* rename touches every CLI command and API route. The project_* retirement itself is trivially small.

### Phase assignment summary

| Work | Phase | Depends on |
|------|-------|-----------|
| Decision document (this PR) | 18.1.6 | Complete |
| Build business_change_orders table + canonical events | 18.4.6 | 18.1.5 (projection framework) |
| Build business_intake_*, business_assumption_* tables | 18.4.8/.9 | 18.1.5 |
| Build business_health_scorecards, business_readiness_scorecards | 18.4.4 | 18.1.5 |
| Rewrite prd_authority.py to projection model | 18.4 (alongside table builds) | 18.1.5 |
| Rename ds_* → business_* (schema + code) | 18.6 (new sub-workstream 18.6.x) | 18.2 substantially complete |
| Drop project_* tables | 18.6.1 | 18.4 business_* tables exist |

---

## Appendix: Raw Schema Comparison

### `ds_milestones` vs `project_milestone_records`

**ds_milestones** (operational tracking, 8 columns):
```
milestone_id, project_id, title, description, due_date, status, created_at, updated_at, order_index
```

**project_milestone_records** (authority specification, 18 columns):
```
milestone_id, project_id, prd_id, prd_version_id, sequence_number, milestone_name, status,
scope_json, stage_gate_json, validation_expectations_json, security_readiness_checks_json,
rollback_strategy, evidence_requirements_json, adapter_context_requirements_json,
source_refs_json, evidence_refs_json, supersedes_milestone_id, superseded_by_milestone_id
```

**v2 business_milestones** should incorporate: title/name + status + order from ds_milestones; scope + stage gates + validation + security readiness + evidence requirements from project_milestone_records.

### `ds_work_orders` vs `project_work_order_authority_records`

**ds_work_orders** (operational tracking, 10 columns):
```
work_order_id, project_id, milestone_id, title, description, status, created_at, updated_at, work_order_type, block_reason
```

**project_work_order_authority_records** (authority specification, 22 columns):
```
work_order_id, project_id, milestone_id, prd_id, prd_version_id, purpose, status,
scope_json, approved_surfaces_json, dependencies_json, validation_json,
evidence_requirements_json, stop_gates_json, final_verdict_taxonomy_json,
route_decision_expectations_json, rollback_strategy,
source_refs_json, evidence_refs_json, supersedes_work_order_id, superseded_by_work_order_id
```

**v2 business_work_orders** should incorporate: title/type/status/block_reason from ds_work_orders; scope + approved_surfaces + stop_gates + validation + evidence requirements from project_work_order_authority_records.

---

*End of Phase 18.1.6 — Project Entity Family Reconciliation*  
*Decision committed 2026-05-22 | Migration executed Phase 18.6.2 (migration 099, 2026-06-05)*

<!-- 2026-06-05: Phase 18.6.2 complete. All 8 project_* tables dropped (migration 099 — 0 rows each, no FK deps). prd_authority.py writers and helpers deleted (-1158 lines). context_packet_prd_authority() removed. Audit trail: .planning/specs/prd-authority-harvest-preflight.md, context-packets-production-value-preflight.md, agent-independence-and-enforcement-plan.md. -->
