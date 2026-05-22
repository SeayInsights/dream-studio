# Pass 1g — Migrations Audit
*Phase 1 analysis | 2026-05-22*

---

## Stated Architectural Intents

1. **SQLite-first authority** — all runtime state must be SQLite-backed. File-based state is v1 rot.
2. **Security audit during brownfield onboarding** — security skills run during project intake, findings stored in SQLite.
3. **Security audit as SDLC lifecycle gate** — greenfield projects must pass security audit before going live.
4. **Canonical events as the spine** — all state changes flow through `canonical_events`.
5. **Marker file authority for attribution** — `.dream-studio-project` markers are identity source of truth.

---

## Migration Era Analysis

### Era 1: Foundation (001–010)

| Migration | Purpose | Tables Created / Modified | Status | Notes |
|-----------|---------|--------------------------|--------|-------|
| 001 | Initial schema — workflow runs, telemetry, analytics | Creates: `raw_workflow_runs`, `raw_workflow_nodes`, `raw_skill_telemetry`, `cor_skill_corrections`, `sum_skill_summary`, `log_batch_imports`, `raw_pulse_snapshots`, `raw_planning_specs`, `sum_analytics_run`, `raw_operational_snapshots` (10 tables); View: `effective_skill_runs` | Applied | Pure file-free SQLite foundation. All 10 tables currently empty except `raw_workflow_runs` (2 rows), `raw_workflow_nodes` (25 rows). Others dead. |
| 002 | Approach capture (what works vs fails per skill) | Creates: `raw_approaches`; View: `vw_approach_patterns` | Applied | `raw_approaches` currently empty. |
| 003 | Skill registry | Creates: `reg_skills`, `reg_gotchas`, `reg_workflows`, `reg_skill_deps` | Applied | `reg_gotchas` has 1,488 rows (live). `reg_skills`, `reg_workflows`, `reg_skill_deps` empty. |
| 004 | Operational tables, FTS5, column additions | Creates: `reg_projects`, `raw_sessions`, `raw_handoffs`, `raw_specs`, `raw_tasks`, `raw_lessons`, `raw_sentinels`, `raw_token_usage`; Alters: `raw_approaches`, `raw_skill_telemetry`; FTS5: `fts_gotchas` | Applied | `raw_sessions` (51 rows), `raw_handoffs` (26 rows), `raw_sentinels` (113 rows), `raw_token_usage` (3 rows) active. `raw_specs`, `raw_tasks`, `raw_lessons` empty. |
| 005 | Automation tracking tables | Creates: `automation_log` | Applied | `automation_log` empty. Note: file header says the table was "present in production DB but missing from migrations" — indicates migration was added retroactively to fix test failures. |
| 006 | Alert system | Creates: `alert_rules`, `alert_history` | Applied | Both empty. Migration 039 re-creates and backfills these. |
| 007 | Document system and analyzed repos registry | Creates: `ds_documents`, `reg_analyzed_repos`, `reg_repo_extractions`, `reg_repo_research_links`; FTS5: `ds_documents_fts` | Applied | `ds_documents` has 12 rows (live). `reg_analyzed_repos`, `reg_repo_extractions`, `reg_repo_research_links` empty. `file_path` column present on `ds_documents` — stores relative file paths, not used as authority pointer. |
| 008 | Research caching and wave execution | Creates: `raw_research`, `reg_research_sources`, `pi_waves`, `pi_wave_tasks` | Applied | All 4 tables empty. |
| 009 | Project Intelligence Wave 2 — core analysis | Creates: `pi_components`, `pi_dependencies`, `pi_violations`, `pi_bugs`, `pi_improvements`, `pi_analysis_runs`; Alters: `reg_projects` (10 ADD COLUMN) | Applied | All 6 created tables empty. `reg_projects` has 2 rows (active). |
| 010 | Workflow Learning System — Project Intelligence Wave 6 | Alters: `reg_workflows` (4 ADD COLUMN); Indexes only | Applied | No new tables. `reg_workflows` empty. |

**Intent 1 (SQLite-first):** Era 1 is clean SQLite-first. No file-based stores created. Migration 019 later added `planning_path` / `sessions_path` columns to `reg_projects` — those reference file system paths but are stored as columns (SQLite records the path; resolution happens at runtime). This is a reference, not a file authority.

**Intent 4 (Events):** Era 1 has zero event pathway. `raw_workflow_runs` and related telemetry are direct-write tables with no canonical event linkage.

---

### Missing Migration: 011

**Status:** No file exists. Not in `_schema_version`. Permanent gap.

**Evidence for what 011 likely contained:**

- Migration 010 (`workflow_learning`) completed "Project Intelligence Wave 6" — it added learning columns to `reg_workflows`. It is a small migration (ADD COLUMN + indexes only).
- Migration 012 (`prd_schema`) is a large, fully formed schema refactor dated 2026-05-05 that introduces the entire PRD tracking subsystem (6 tables, 2 views, 12 indexes). Its comment says "Replaces: Text-based plan_path in raw_handoffs with relational PRD tracking."
- The gap between "Wave 6 workflow learning" and "PRD schema refactor" is the domain boundary, not a functional gap.
- Header numbers in files 012–019 are correctly aligned (012 = "Migration 012"). The numbering discontinuity at 011 is the only case before the 020–029 renumbering block where a number skips with no header mismatch.

**Conclusion:** Migration 011 was deliberately skipped or a draft file was deleted before being applied. The most likely candidate would have been an intermediate PRD planning step or a "raw_handoffs to prd_handoffs" bridge migration that was replaced by the comprehensive 012 refactor. No evidence of a lost migration with functional content — the gap appears intentional and harmless.

---

### Era 2: First Expansion (012–034)

| Migration | Purpose | Tables Created / Modified | Status | Notes |
|-----------|---------|--------------------------|--------|-------|
| 012 | PRD Schema Refactor | Creates: `prd_documents`, `prd_plans`, `prd_tasks`, `prd_sessions`, `session_tasks`, `prd_handoffs`; Views: `vw_prd_progress`, `vw_task_details` | Applied | All 6 tables empty. Intended to supersede `raw_handoffs` for PRD-tracked work but `raw_handoffs` (26 rows) is still the live handoff store. Dead subsystem — Intent 1 partial failure. |
| 013 | Discovery System Tables | Creates: `tool_registry`, `research_cache` | Applied | Both empty. |
| 014 | Graph Analysis Views | Creates views: `vw_graph_edges`, `vw_component_stats` | Applied | Both views **permanently retired** in migration 062 (broken since initial publication commit 790965e, note says "no production readers"). |
| 015 | Performance Indexes | Indexes only (on `pi_components`, `pi_dependencies`) | Applied | No tables. |
| 016 | Tool Embeddings Cache | Creates: `tool_embeddings_cache` | Applied | `tool_embeddings_cache` empty. |
| 017 | Central Activity Log (hub table) | Creates: `activity_log` | Applied | `activity_log` **DROPPED** in migration 063 (TA0c retirement). The hub-and-spoke architecture based on `activity_log` was conceived here and then completely dismantled in Era 4. |
| 018 | Hook Execution Tracking (spoke tables) | Creates: `hook_executions`, `hook_findings` | Applied | `hook_executions` has 45 rows (live). `hook_findings` empty. Tables recreated with nullable `activity_id` in migration 062. |
| 019 | Update project paths to new structure | Alters: `reg_projects` (ADD `planning_path`, `sessions_path`); UPDATE backfill | Applied | Adds file path reference columns — the only migration that writes relative filesystem paths into SQLite rows. Not a file-based authority; it is SQLite storing paths to optional file exports. |
| 020 | Security Findings Tracking (spoke tables) | Creates: `sec_sarif_findings`, `sec_manual_reviews`, `sec_cve_matches`, `sec_hook_checks` | Applied | All 4 empty. Tables recreated with nullable `activity_id` in migration 062. File header says "Migration 019" — off-by-one header mismatch (first of the 020–029 renumbering block). |
| 021 | Risk Register (spoke tables) | Creates: `risk_register`, `risk_mitigations` | Applied | Both empty. |
| 022 | Workflow Connections — cross-domain traceability | Recreates `raw_workflow_runs` and `raw_workflow_nodes` with FK columns; drops/recreates temp tables | Applied | Table recreations add activity_id, prd_id, task_id FKs. All FKs now orphaned because `activity_log` was dropped. |
| 023 | Research Connections — cross-domain traceability | Recreates `research_cache` and `raw_research` with FK columns | Applied | Same pattern as 022 — `activity_id` columns added, now nullable orphans. |
| 024 | Learning Connections | Alters: `raw_lessons` (ADD COLUMN: `activity_id`, `task_id`, `prd_id`, `skill_id`) | Applied | `raw_lessons` empty. |
| 025 | Audit Run Tracking | Creates: `audit_runs` | Applied | `audit_runs` empty. |
| 026 | Consolidate Databases — prepare for dream-studio.db → studio.db merge | No table creates. Adds indexes to `automation_log`. SELECT statements for pre-merge validation (these execute as no-ops) | Applied | Migration is mostly documentation + index creation. Header says "Migration 021" (mismatch). The merge was supposed to be completed by TA-004 script (never confirmed). |
| 027 | Guardrail Metadata | Creates: `guardrail_decisions`, `guardrail_rules_audit` | Applied | Both empty. |
| 028 | Create `automation_checkpoints` | Creates: `automation_checkpoints` | Applied | Empty. Header says "Migration 023" (mismatch). Note says this table "was present in production DB but missing from migrations, causing failures." |
| 029 | Analytics Views | Creates views (DROP/CREATE pattern for `vw_security_summary` and others) | Applied | `vw_security_summary` later replaced by 039. No numeric header (just "Migration: Analytics Views"). |
| 030 | Adapter Metadata | Creates: `adapter_executions` | Applied | `adapter_executions` **DROPPED** and recreated with nullable `activity_id` in migration 062. Currently empty. |
| 031 | Decision Log and Causal Links | Creates: `decision_log`, `decision_event_link` | Applied | Both empty. |
| 032 | Semantic Memory Convergence | Alters: `memory_entries` (8 ADD COLUMN) | Applied | `memory_entries` empty (FTS tables have minimal config rows). |
| 033 | FTS5 Retrieval Index for memory_entries | Creates virtual table: `memory_fts` | Applied | `memory_fts` empty (only config rows). |
| 034 | Execution Graph Layer (promoted from legacy 003) | Creates: `execution_nodes`, `execution_dependencies`, `execution_outputs`, `execution_event_links`; Views: `v_active_execution`, `v_blocked_nodes`, `v_completion_rate` | Applied | All 4 tables empty. Note says "promoted from legacy 003" — suggests this was extracted from an older unreleased migration. Views dropped in migration 062, some recreated. |

**Intent 1 (SQLite-first):** Era 2 is conceptually correct but execution is incomplete. The PRD schema (012) was built to replace `raw_handoffs` but `raw_handoffs` is still active. The hub-and-spoke `activity_log` architecture (017-025) was fully dismantled in Era 4 — a complete architectural reversal.

**Intent 4 (Events):** Era 2 creates no event pathway. `activity_log` was the intended event hub but it was a write-only table without canonical_events linkage. It was superseded by the canonical_events spine in Era 4.

**Header/number mismatches in Era 2:** Files 020–029 have internal header numbers that are 1–4 off from their file names. This is a confirmed renumbering pass (files renamed, headers not updated). The file names are authoritative.

---

### Missing Migrations: 035, 036

**Status:** No files exist. Not in `_schema_version`. Permanent gaps.

**Evidence for what 035/036 likely contained:**

- Migration 034 (`execution_graph`) was explicitly described as "promoted from legacy 003" and dated 2026-05-07, promoted 2026-05-09.
- Migration 037 (`execution_telemetry_traceability_spine`) is the massive 14,531-byte migration creating 20 new authority tables — the backbone of the canonical execution telemetry system.
- The file 037 is the first migration NOT to have `activity_log` as a hub; it operates independently.
- The gap of 035–036 (2 missing) combined with 034's note about "promotion from legacy 003" strongly suggests that 035 and 036 were draft/experimental versions of what became the 037 spine migration. The promotion of 034 from legacy code and the subsequent redesign of the telemetry spine required discarding two drafts before landing on 037.
- Alternative interpretation: 035 and 036 may have been intermediate bridge migrations between the `activity_log` hub architecture and the `execution_events` spine architecture that were squashed into 037.

**Conclusion:** The 035/036 gap represents a deliberate design reset point. The `activity_log` hub-and-spoke design was abandoned and replaced by the canonical events spine. Two draft migrations were discarded. No functional content was lost — 037 is a clean replacement.

---

### Era 3: Post-Gap Expansion (037–050)

| Migration | Purpose | Tables Created / Modified | Status | Notes |
|-----------|---------|--------------------------|--------|-------|
| 037 | Execution Telemetry Traceability Spine | Creates: `execution_events`, `process_runs`, `telemetry_module_registry`, `telemetry_entity_registry`, `agent_invocations`, `skill_invocations`, `workflow_invocations`, `hook_invocations`, `tool_invocations`, `token_usage_records`, `security_findings`, `decision_records`, `research_evidence_records`, `blocker_resolution_records`, `validation_results`, `artifact_records`, `outcome_records`, `route_decision_records`, `dashboard_attention_items`, `authority_projection_records` (20 tables) | Applied | Largest DDL block. All empty except `execution_events` (929 rows), `hook_invocations` (917), `tool_invocations` (917), `skill_invocations` (1), `validation_results` (empty but present), `route_decision_records` (empty), `outcome_records` (2). The telemetry core is live. Intent 4 alignment: YES — canonical execution_events links here. |
| 038 | Shared Intelligence SQLite Authority Foundation | Creates: `artifact_authority_records`, `learning_event_records`, `hardening_candidate_records`, `adapter_authority_profiles`, `model_provider_profiles`, `shared_context_packets`, `adapter_result_records`, `capability_route_records` (8 tables) | Applied | All 8 empty. `file_is_export INTEGER DEFAULT 1` on `artifact_authority_records` explicitly marks records as having optional file exports — SQLite is authority, file is projection. Intent 1 alignment: YES explicitly stated in header. |
| 039 | Dashboard Authority Reconciliation | Repair migration: re-creates `raw_sessions`, `alert_rules`, `alert_history`; ALTERs `raw_sessions` (11 ADD COLUMN); Creates: `dashboard_authority_reconciliation_records`; Drops and re-creates `vw_security_summary` | Applied | `dashboard_authority_reconciliation_records` empty. This migration is a compatibility patch for databases created before the full column set was defined. |
| 040 | Production Readiness Authority | Creates: `production_readiness_assessment_runs`, `production_readiness_control_results`, `production_readiness_findings`, `production_readiness_remediation_work_orders`, `production_readiness_skill_control_mappings`, `project_readiness_scorecards`, `project_health_scorecards`, `release_readiness_records`, `compliance_review_flags` (9 tables) | Applied | All 9 empty. Intent 2 (security audit): partial — `production_readiness_findings` would receive intake security scan results, but is empty. Wiring not complete. |
| 041 | Legacy Canonical Event Import Map | Creates: `legacy_canonical_event_import_map` | Applied | Empty. Intended as an import ledger for old backup canonical_events reconciliation. |
| 042 | Token Usage Source References | Creates `token_usage_records` (IF NOT EXISTS — idempotent on top of 037); ALTERs to add `source_refs_json`, `evidence_refs_json` | Applied | Redundant CREATE wrapped in IF NOT EXISTS. The ALTER columns duplicate what 037 already defined. Safe but sloppy — indicates 042 was written without checking 037's schema. |
| 043 | AI Usage Accounting | Creates `token_usage_records` (IF NOT EXISTS again); Creates `ai_adapter_accounting_profiles`, `ai_usage_operational_records`; ALTERs `token_usage_records` (7 ADD COLUMN) | Applied | Third CREATE IF NOT EXISTS for `token_usage_records`. `ai_adapter_accounting_profiles` and `ai_usage_operational_records` empty. Multiple ALTERs may be adding already-present columns (silent duplicates). |
| 044 | Career Ops, Capability Center, Scoped Agents, GitHub Repo Intake Authority | Creates 28 tables: all career_* tables (15), `capability_center_records`, `agent_registry_records`, `agent_context_scope_policies`, `workflow_agent_skill_mappings`, `agent_result_records`, all github_repo_* tables (8) | Applied | All 28 empty. Largest single-migration table count. Header notes "optional/private authority, additive only, not enabled by default." |
| 045 | Task Attribution Authority | Creates: `task_attribution_records` | Applied | Empty. |
| 046 | Platform Hardening Authority | Creates: `skill_evaluation_runs`, `policy_decision_records`, `connector_ingestion_runs`, `privacy_redaction_export_records`, `local_watch_schedule_records`, `team_rollup_records`, `installer_distribution_checks`, `demo_case_study_packets` (8 tables) | Applied | All 8 empty. |
| 047 | PRD Lifecycle and Route Authority | Creates: `project_intake_records`, `project_intake_questions`, `project_assumption_records`, `prd_version_records`, `project_milestone_records`, `project_work_order_authority_records`, `project_change_order_records`, `prd_amendment_records`, `prd_route_reconciliation_records` (9 tables) | Applied | All 9 empty. Explicit header: "Files remain optional exports; SQLite is the durable current authority." Intent 1 alignment: YES explicitly. Intent 2 alignment: `project_intake_records` is the correct home for brownfield onboarding security audit kickoff — but empty. |
| 048 | Project Spine — ds_projects, ds_milestones, ds_work_orders, ds_tasks | Creates: `ds_projects`, `ds_milestones`, `ds_work_orders`, `ds_tasks` | Applied | Core operational tables. `ds_projects` (25 rows), `ds_milestones` (4), `ds_work_orders` (14), `ds_tasks` (9). This is the LIVE operational spine. |
| 049 | Work Order Type Routing Key | Creates: `ds_work_order_types`; Alters: `ds_work_orders` ADD COLUMN `work_order_type`; INSERT OR IGNORE for type rows | Applied | `ds_work_order_types` has 10 rows (live). |
| 050 | Documents Source Path | Alters: `ds_documents` ADD COLUMN `source_path` | Applied | `ds_documents` (12 rows, active). |

**Intent 4 (Events):** Migration 037 is the turning point. `execution_events` becomes the new event spine, explicitly linked to `canonical_events` starting in Era 4. However, in Era 3 itself, `execution_events` is written directly (not projected from `canonical_events`). The TA0b reconciliation in Era 4 retroactively adds the projection link.

**The activity_log deprecation path spans eras:** Created in 017 (Era 2), used as hub hub by 018–025, abandoned in 037 (Era 3), formally retired in 062–063 (Era 4). The hub-and-spoke architecture lasted for 8 migrations and then was completely replaced.

---

### Era 4: TA Series (051–064)

The TA series represents the Token Attribution remediation workstream — a retroactive push to bring all state changes under `canonical_events` authority.

| Migration | Purpose | Tables Created / Modified | Status | Notes |
|-----------|---------|--------------------------|--------|-------|
| 051 | Add `block_reason` column; extend `ds_work_orders.status` to include 'blocked' | Alters: `ds_work_orders`; PRAGMA writable_schema to patch CHECK constraint in-place | Applied | Applied 2026-05-16 (same day as 001–050 batch). `writable_schema` approach is non-standard for SQLite — used to avoid table recreation. |
| 052 | Add `invocation_mode` to `canonical_events` | Alters: `canonical_events` | Applied | `canonical_events` was not created by any migration (created lazily by the ingestor). This is the first migration to ALTER the canonical events table. |
| 053 | Design Brief Persistence | Creates: `ds_design_briefs` | Applied 2026-05-17 | `ds_design_briefs` has 1 row (live). |
| 054 | UI Gate Update | Updates: `ds_work_order_types` SET `post_build_gate = 'design_critique|anti_slop_passed'` for ui_component, ui_page | Applied 2026-05-17 | Pure data update, no DDL. |
| 055 | Technology Signals | Creates: `ds_technology_signals` | Applied 2026-05-17 | `ds_technology_signals` has 54 rows (live). |
| 056 | Milestone Order Index | Alters: `ds_milestones` ADD `order_index`; UPDATE backfill for Dream Command project | Applied 2026-05-19 | Backfill uses `rowid` as ordering proxy. |
| 057 | Work Order Type Extensions | Alters: `ds_work_order_types` (ADD 4 columns); UPDATEs for workflow/task routing | Applied 2026-05-19 | Extends routing table with `workflow_template`, `precondition_skill`, `task_generator`, `resolution_instructions`. |
| 058 | TA0b — Domain Field Validation | No DDL. Documents requirement that `canonical_events.trace` must include `domain` field. No schema change. | Applied 2026-05-21 | Pure documentation migration — records a requirement, makes no schema changes. Unusual pattern. |
| 059 | TA0b — Execution Events Projection Link | Alters: `execution_events` ADD `_built_from_event_id` | Applied 2026-05-21 | Links each `execution_events` row back to its source `canonical_events` record. Key Intent 4 migration — establishes the canonical_events → execution_events projection chain. |
| 060 | TA0b — Backfill Domain Field and Execution Events Projection | UPDATE backfill: sets `domain = 'telemetry'` in `canonical_events.trace` JSON for known event types | Applied 2026-05-21 | Pure data migration. No DDL. Backfills 'domain' field into existing `canonical_events` rows. |
| 061 | TA0 — Backfill SDLC Creation Events | INSERT OR IGNORE: synthetic `project.created`, `milestone.created`, `work_order.created` events into `canonical_events` | Applied 2026-05-21 | Attribution: `backfill` status. First canonical event backfill migration. Covers entities that existed before event emission was implemented. |
| 062 | Nullify activity_id FKs, Backfill activity_log → canonical_events, Replace Views | Recreates 7 tables with nullable `activity_id`; Drops 15 views and recreates 13; INSERT OR IGNORE backfill: 159 `activity_log` rows → `canonical_events` | Applied 2026-05-22 | Most complex single migration (20,625 bytes). Finalizes the `activity_log` → `canonical_events` migration. 159 historical activity records moved to canonical spine. |
| 063 | Drop activity_log | DROPs indexes and table: `activity_log` | Applied 2026-05-22 | One line of real DDL after 062 does all the preparation. `activity_log` is gone. |
| 064 | TA1 — Backfill task.created Events | INSERT OR IGNORE: synthetic `task.created` events for 9 tasks that predate event emission | Applied 2026-05-22 | Covers `ds_tasks` rows. Attribution: `backfill`. |

**TA series summary:** The TA series is a coherent retroactive attribution remediation. It was applied across 6 days (051–052 on 2026-05-16, 053–055 on 2026-05-17, 056 on 2026-05-19, 057 on 2026-05-19, 058–064 on 2026-05-21 to 2026-05-22). It completed three objectives:

1. Added the projection link from `execution_events` to `canonical_events` (059).
2. Backfilled the `domain` field into existing canonical events (060).
3. Generated synthetic backfill events for SDLC entities and tasks that predate event emission (061, 064).
4. Migrated and then dropped `activity_log`, consolidating all event history into `canonical_events` (062, 063).

**What the TA series did NOT complete:** No backfill migrations exist for PRD-era entities (`prd_documents`, `prd_tasks`, `prd_sessions`, `prd_handoffs`), Era 2 research/workflow/learning table writes, or any of the Era 3 authority tables (040–047). The token attribution series touched SDLC spine entities only.

---

## Dead Tables

Tables created by migrations but currently holding 0 rows:

| Table | Created By | Era | Notes |
|-------|-----------|-----|-------|
| `raw_skill_telemetry` | 001 | 1 | Empty. Superseded by `execution_events` + `tool_invocations`. |
| `cor_skill_corrections` | 001 | 1 | Empty. Learning/correction capture never wired. |
| `sum_skill_summary` | 001 | 1 | Empty. Analytics summary table, no writer. |
| `log_batch_imports` | 001 | 1 | Empty. Batch import tracking never used. |
| `raw_pulse_snapshots` | 001 | 1 | Empty. |
| `raw_planning_specs` | 001 | 1 | Empty. |
| `sum_analytics_run` | 001 | 1 | Empty. |
| `raw_approaches` | 002 | 1 | Empty. Was intended to track what approach worked per skill session. |
| `reg_skills` | 003 | 1 | Empty. Skills defined in YAML/files, not written to SQLite. Intent 1 gap. |
| `reg_workflows` | 003 | 1 | Empty. Same pattern as `reg_skills`. |
| `reg_skill_deps` | 003 | 1 | Empty. |
| `raw_specs` | 004 | 1 | Empty. |
| `raw_tasks` | 004 | 1 | Empty. Superseded by `ds_tasks` (048). |
| `raw_lessons` | 004 | 1 | Empty. |
| `automation_log` | 005 | 1 | Empty. Automation tracking never used. |
| `alert_rules` | 006 | 1 | Empty (re-created in 039). No alert rules defined. |
| `alert_history` | 006 | 1 | Empty. No alerts triggered. |
| `reg_analyzed_repos` | 007 | 1 | Empty. |
| `reg_repo_extractions` | 007 | 1 | Empty. |
| `reg_repo_research_links` | 007 | 1 | Empty. |
| `raw_research` | 008 | 1 | Empty. |
| `reg_research_sources` | 008 | 1 | Empty. |
| `pi_waves` | 008 | 1 | Empty. |
| `pi_wave_tasks` | 008 | 1 | Empty. |
| `pi_components` | 009 | 1 | Empty. PI analysis never run on this project. |
| `pi_dependencies` | 009 | 1 | Empty. |
| `pi_violations` | 009 | 1 | Empty. |
| `pi_bugs` | 009 | 1 | Empty. |
| `pi_improvements` | 009 | 1 | Empty. |
| `pi_analysis_runs` | 009 | 1 | Empty. |
| `tool_registry` | 013 | 2 | Empty. Discovery system not wired. |
| `research_cache` | 013 | 2 | Empty. |
| `tool_embeddings_cache` | 016 | 2 | Empty. Sentence-transformers never connected. |
| `hook_findings` | 018 | 2 | Empty. Hook executions (45 rows) run but produce no structured findings. |
| `sec_sarif_findings` | 020 | 2 | Empty. Security scan tables exist but no scans have written here. Intent 2 gap. |
| `sec_manual_reviews` | 020 | 2 | Empty. |
| `sec_cve_matches` | 020 | 2 | Empty. |
| `sec_hook_checks` | 020 | 2 | Empty. |
| `risk_register` | 021 | 2 | Empty. Intent 2 gap — risks not being captured. |
| `risk_mitigations` | 021 | 2 | Empty. |
| `audit_runs` | 025 | 2 | Empty. |
| `automation_checkpoints` | 028 | 2 | Empty. |
| `guardrail_decisions` | 027 | 2 | Empty. |
| `guardrail_rules_audit` | 027 | 2 | Empty. |
| `decision_log` | 031 | 2 | Empty. Superseded by `decision_records` in 037. |
| `decision_event_link` | 031 | 2 | Empty. |
| `prd_documents` | 012 | 2 | Empty. PRD system exists but nothing written. |
| `prd_plans` | 012 | 2 | Empty. |
| `prd_tasks` | 012 | 2 | Empty. Superseded by `ds_tasks` (048). |
| `prd_sessions` | 012 | 2 | Empty. |
| `session_tasks` | 012 | 2 | Empty. |
| `prd_handoffs` | 012 | 2 | Empty. `raw_handoffs` (26 rows) is still the live handoff store. |
| `execution_nodes` | 034 | 2 | Empty. Execution graph layer never populated. |
| `execution_dependencies` | 034 | 2 | Empty. |
| `execution_outputs` | 034 | 2 | Empty. |
| `execution_event_links` | 034 | 2 | Empty. |
| `artifact_authority_records` | 038 | 3 | Empty. |
| `learning_event_records` | 038 | 3 | Empty. |
| `hardening_candidate_records` | 038 | 3 | Empty. |
| `adapter_authority_profiles` | 038 | 3 | Empty. |
| `model_provider_profiles` | 038 | 3 | Empty. |
| `shared_context_packets` | 038 | 3 | Empty. |
| `adapter_result_records` | 038 | 3 | Empty. |
| `capability_route_records` | 038 | 3 | Empty. |
| `dashboard_authority_reconciliation_records` | 039 | 3 | Empty. |
| All 9 production_readiness_* tables | 040 | 3 | Empty. Intent 2 (security gate) gap — readiness assessment infrastructure exists but unused. |
| `legacy_canonical_event_import_map` | 041 | 3 | Empty. Import ledger never written to. |
| `ai_adapter_accounting_profiles` | 043 | 3 | Empty. |
| `ai_usage_operational_records` | 043 | 3 | Empty. |
| All 28 career_* / capability_* / github_repo_* tables | 044 | 3 | Empty. Career pack explicitly disabled by default. |
| `task_attribution_records` | 045 | 3 | Empty. |
| All 8 platform_hardening_* tables (046) | 046 | 3 | Empty. |
| All 9 prd_lifecycle_authority tables (047) | 047 | 3 | Empty. |
| `token_usage_records` | 037, 042, 043 | 3 | Empty. Token tracking infrastructure built but nothing written. |
| `telemetry_module_registry` | 037 | 3 | Empty. |
| `telemetry_entity_registry` | 037 | 3 | Empty. |

**Dead table count:** Approximately 100 of the ~150 non-system tables are empty.

**Notable exception — tables created by migrations that ARE live:**
`reg_gotchas` (1,488 rows), `raw_sessions` (51), `raw_handoffs` (26), `raw_sentinels` (113), `ds_projects` (25), `ds_milestones` (4), `ds_work_orders` (14), `ds_tasks` (9), `ds_work_order_types` (10), `ds_documents` (12), `ds_technology_signals` (54), `ds_design_briefs` (1), `hook_executions` (45), `execution_events` (929), `hook_invocations` (917), `tool_invocations` (917), `canonical_events` (1,853).

---

## Special Focus: SQLite vs File-Based in Migration History

### Did any migration attempt to migrate from file to SQLite?

**Yes — two patterns identified:**

**1. Migration 026 (`consolidate_databases`) — DB-to-DB migration, not file-to-SQLite**
This migration prepared schema for merging `dream-studio.db` → `studio.db`. It documented a process (the actual data copy was supposed to be done by a separate `TA-004` script) but performed no file-based migration itself. The separate `.db` files are different SQLite files, not flat-file stores.

**2. Migration 062 — activity_log → canonical_events backfill**
159 rows from `activity_log` were migrated to `canonical_events` as part of the `activity_log` retirement. This is table-to-table within SQLite. Completed.

**3. Migrations 061, 064 — SDLC entity synthetic event backfills**
Synthetic creation events generated from existing SQLite rows (ds_projects, ds_milestones, ds_work_orders, ds_tasks). The "file" being migrated is effectively the pre-event-emission SQLite state. Completed for SDLC spine only.

### What file-based stores remain unwired to SQLite?

**These file-based stores exist but have NO completed SQLite migration path:**

- `.dream-studio/projects/<name>/planning/` — plans, specs, work orders as markdown files. Migration 019 added `planning_path` as a column but this makes SQLite reference the file, not replace it.
- `.dream-studio/projects/<name>/sessions/` — session handoffs stored as markdown files. `raw_handoffs` table (26 rows) was the SQLite counterpart but is fed by a direct writer, not a migration. PRD handoffs table (migration 012) is empty.
- `canonical/skills/*.md`, `canonical/workflows/*.yaml` — skills and workflows defined in files. `reg_skills` and `reg_workflows` are empty (migration 003 created the tables; no writer ever populated them). Intent 1 gap: skill definitions are file-based only.
- `.dream-studio-project` marker files — Intent 5. No migration has ever touched the concept of marker files. There is no `project_markers` table, no migration for marker → SQLite, no evidence the marker files feed any SQLite table. The marker file remains the sole identity source with zero SQLite backing.

### Incomplete migration path for file-based stores

| File-Based Store | Intended SQLite Table | Migration That Created Table | Current SQLite Rows | Gap |
|-----------------|----------------------|------------------------------|---------------------|-----|
| planning/ files | `prd_documents`, `prd_plans` | 012 | 0 | Writer never connected |
| session handoff files | `prd_handoffs` | 012 | 0 | `raw_handoffs` still active (26 rows) |
| skills YAML/MD | `reg_skills` | 003 | 0 | No scanner/loader built |
| workflows YAML | `reg_workflows` | 003 | 0 | No scanner/loader built |
| `.dream-studio-project` markers | (none) | (none) | — | No migration created a table for this |

---

## Special Focus: Schema Version Applied Count

**Files on disk:** 61 `.sql` files  
**Rows in `_schema_version`:** 61 rows  
**Match:** Exact. Every file on disk has a corresponding applied row.

**Gap analysis:**
- Numbers 1–64 in sequence: 3 numbers are absent from both disk and DB (011, 035, 036).
- The runner applies migrations by file name (extracting the numeric prefix), so it can never apply a migration number that has no file. The gaps are permanent and do not represent "unapplied" migrations.
- The claim "61 applied out of 64 files" from Phase 0c was accurate: 64 is the highest migration number; 61 files exist; 61 applied.

**Applied timing clusters:**
- Migrations 001–050: All applied in a single batch on 2026-05-16 at 21:01:02–21:01:03 UTC (< 1 second window). This is an initial install against a fresh database.
- Migrations 051–052: Applied 2026-05-16 at 22:42:30 UTC (same day, ~1.5 hours later).
- Migration 053: 2026-05-17 at 00:40 UTC.
- Migration 054: 2026-05-17 at 00:46 UTC.
- Migration 055: 2026-05-17 at 12:16 UTC.
- Migration 056: 2026-05-19 at 00:42 UTC.
- Migration 057: 2026-05-19 at 22:27 UTC.
- Migrations 058–060: 2026-05-21 at 20:55–20:58 UTC.
- Migration 061: 2026-05-21 at 23:35 UTC.
- Migrations 062–063: 2026-05-22 at 01:49 UTC.
- Migration 064: 2026-05-22 at 02:29 UTC.

The timing shows migrations 001–050 were a single clean-install event. Migrations 051–064 represent incremental development over 6 days (2026-05-16 to 2026-05-22). This is consistent with the TA series being an ongoing remediation workstream.

---

## Findings

### F-G01: Migration numbering is authoritative-by-file, not by header
**Severity:** Low  
Files 020–029 have internal header numbers that do not match their file names (off by 1, caused by a renumbering pass that updated filenames but not headers). The migration runner uses the file name numeric prefix as the version number. The headers are documentation only. All 61 files applied correctly despite mismatches.

### F-G02: Three permanent gaps (011, 035, 036) are benign
**Severity:** Low  
No file, no application. Gap 011 was likely a discarded draft replaced by the comprehensive 012 PRD refactor. Gaps 035–036 were likely draft versions of the 037 telemetry spine. No functional regression.

### F-G03: ~100 of ~150 non-system tables are empty
**Severity:** High  
This is the most significant finding. Roughly two-thirds of the schema has been defined but never populated. This creates three risks:
1. **Maintenance debt** — schema grows without corresponding writers, making it harder to understand what is actually used.
2. **False architectural confidence** — the existence of tables like `sec_sarif_findings`, `production_readiness_assessment_runs`, `project_intake_records` creates the impression that security audit and production readiness workflows are implemented. They are schema-only.
3. **Compounding duplication** — `raw_tasks` (004) and `prd_tasks` (012) are both superseded by `ds_tasks` (048). Multiple generations of "task" tables exist simultaneously; only the last-generation table is live.

### F-G04: token_usage_records created by three separate migrations (037, 042, 043)
**Severity:** Medium  
Migration 037 creates `token_usage_records` with a full column set. Migration 042 creates it again (IF NOT EXISTS) and then tries to ADD columns that already exist — the migration runner silently swallows the duplicate-column errors. Migration 043 repeats the pattern a third time. The table has 0 rows despite having been the subject of 3 migrations. This indicates iterative schema confusion — the writers for this table were never implemented regardless of schema iteration.

### F-G05: The hub-and-spoke (activity_log) architecture was completely built and then completely reversed
**Severity:** Medium (observation)  
Migrations 017–025 built `activity_log` as a hub with multiple spoke tables (hook_executions, security findings, risk, audit, guardrails) all linked via `activity_id` FK. Migrations 062–063 demolished this architecture by making `activity_id` nullable everywhere and dropping `activity_log`. The 159 rows that were in `activity_log` at retirement time have been migrated to `canonical_events`. This is a completed architectural reversal with no loose ends except the now-nullable `activity_id` columns that remain on 7 tables as dead columns.

### F-G06: `reg_skills` and `reg_workflows` are empty despite being foundational
**Severity:** High (Intent 1 gap)  
Migration 003 created these tables in Era 1 as the authoritative skill and workflow registry. They have never been populated. All skill definitions live in `canonical/skills/*.md` and `canonical/workflows/*.yaml`. This is the clearest example of Intent 1 (SQLite-first authority) not being achieved — the skill system's source of truth is files, not SQLite.

### F-G07: .dream-studio-project marker files have no SQLite counterpart
**Severity:** High (Intent 5 gap)  
Intent 5 states marker files are the identity source of truth. No migration has ever created a table to store or reconcile marker file data. There is no `project_markers` table, no migration that reads markers to populate any table, and no `reg_projects` column that links to marker file presence. The marker file is an island — it exists in the filesystem only. Migration 048 created `ds_projects` as the operational project store (25 rows) but there is no evidence these rows were populated from marker file data.

### F-G08: Intents 2 and 3 (security audit workflow) exist only as schema
**Severity:** High  
The infrastructure for security-during-intake (Intent 2) and security-as-gate (Intent 3) is entirely schema-defined with zero operational use:
- `project_intake_records` (047): 0 rows — security classification field exists, never populated.
- `sec_sarif_findings`, `sec_manual_reviews`, `sec_cve_matches`, `sec_hook_checks` (020): all 0 rows.
- `production_readiness_assessment_runs` and related (040): all 0 rows.
- `compliance_review_flags` (040): 0 rows.
The security audit as an SDLC gate is architectural intent without runtime implementation.

### F-G09: TA series is incomplete — only SDLC spine backfilled
**Severity:** Medium  
The TA series backfilled `project.created`, `milestone.created`, `work_order.created` (061) and `task.created` (064) events. It did NOT backfill:
- PRD-era events (`prd_documents`, `prd_tasks`, `prd_sessions`)
- Raw handoff events
- Learning events from `raw_lessons`
- Research cache events
- Any of the ~100 empty authority tables' creation events

The canonical_events spine (1,853 rows) covers SDLC spine + telemetry invocations only. The vast majority of historical system activity (pre-canonical) has no event record.

---

## Intent Divergence

| Intent | Statement | Migration Evidence | Status |
|--------|-----------|-------------------|--------|
| 1: SQLite-first | All runtime state must be SQLite-backed | Era 1: Foundation correct. Era 2: `reg_skills`, `reg_workflows` created (003) but never populated — skills remain file-only. `prd_*` tables (012) exist but `raw_handoffs` still active. Migration 019 adds path columns to SQLite (reference, not authority). Era 3: Most authority tables correct but all empty. | **Partial — critical gap: skill/workflow definitions still file-only** |
| 2: Security during brownfield onboarding | Security skills run during intake, findings stored in SQLite | `project_intake_records` (047), `sec_sarif_findings` (020), `audit_runs` (025) all exist with 0 rows. No migration wires a security skill to the intake flow. | **Schema-only. Not implemented.** |
| 3: Security as SDLC gate | Greenfield projects must pass security before going live | `production_readiness_assessment_runs`, `production_readiness_findings`, `project_readiness_scorecards` (040) all 0 rows. `ds_work_order_types.post_build_gate` exists (049/054) but security audit is not a required gate. | **Schema-only. Not implemented.** |
| 4: Canonical events as spine | All state changes flow through canonical_events | Era 1–2: Zero event pathway. Era 3: `execution_events` + invocation tables created (037) but not linked to canonical_events. Era 4: TA series adds projection link (059), backfills SDLC entities (061, 064), migrates activity_log (062), drops activity_log (063). | **Partially achieved. SDLC spine and invocations covered. PRD/research/learning/authority tables have no event pathway.** |
| 5: Marker file authority | `.dream-studio-project` markers are identity source | No migration has ever created a table for marker data. `ds_projects` (048) exists but no linkage to markers. | **Not implemented at migration level.** |

---

## Open Questions

1. **Were gaps 035–036 ever written to disk before deletion?** The `promoted from legacy 003` note on 034 suggests significant refactoring occurred around this number range. Were there intermediate files that were intentionally deleted, or did the author deliberately skip these numbers to signal a design reset?

2. **Is the `dream-studio.db` consolidation (026, TA-004) complete?** Migration 026 prepared schema for the merge but explicitly deferred the actual data copy to a separate `TA-004` script. Was that script ever run? If not, there may be data in an orphaned `dream-studio.db` file that was never merged.

3. **Why does `raw_handoffs` remain active while `prd_handoffs` is empty?** Migration 012's comment says it "Replaces: Text-based plan_path in raw_handoffs with relational PRD tracking" but the code path writing to `raw_handoffs` was never redirected. Is `raw_handoffs` intentionally maintained as a simpler handoff store, or is this a wiring oversight?

4. **Who owns `reg_skills` population?** Skills are defined in `canonical/skills/*.md`. Was a scanner/loader ever planned to populate `reg_skills` from those files? If yes, it was never built. If no, what is the purpose of `reg_skills`?

5. **Is `token_usage_records` (0 rows) a monitoring blind spot?** Token usage is tracked in `canonical_events` via `token.consumption.recorded` events but the dedicated `token_usage_records` table is empty. Are these two stores intended to be synchronized, or has `canonical_events` fully replaced `token_usage_records` as the token authority?

6. **What triggers `project_intake_records` creation?** The table exists for security-during-onboarding (Intent 2) but has 0 rows and 25 active projects. When is intake supposed to run? Is it gated to a CLI command that was never invoked, or is the `ds project register` command expected to write here and does not?
