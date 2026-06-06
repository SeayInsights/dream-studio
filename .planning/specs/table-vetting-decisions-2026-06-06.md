# Table Vetting Decisions — 2026-06-06

Investigation output for WO-E (`b4df12bd-9e19-4330-b71f-3793f8db9e85`).
Rubric: AD-4 (live writer AND consumer required; non-adherent → retire).
Feeds: WO-F (DROP execution), WO-M (canonical cutover), WO-R (AI spine consolidation),
and a future migration-class WO for `security_events` + `readiness_events` spine authoring.

Source evidence: `spool/ingestor.py`, `core/event_store/event_store.py`,
`core/telemetry/execution_spine.py`, `core/shared_intelligence/scoped_agents.py`,
`core/execution/workflow_integration.py:284`, AD-1 through AD-10
(`.planning/specs/architecture-decisions-2026-06-06.md`), table census
(`.planning/audits/table-census-2026-06-06.md`), live studio.db row counts 2026-06-06.

---

## Part 1 — Event-Substrate Layer Map (Task 0)

The four event tables and their AD-1/AD-2/AD-5 classification:

| Table | Rows | Layer | Live Writer | Live Readers | Verdict |
|---|---|---|---|---|---|
| `canonical_events` | 8186 | **Legacy substrate** | `core/event_store/event_store.py:180,248` | projection runners (historical) | RETIRE after WO-M cutover; migration-class |
| `business_canonical_events` | 536 | **Substrate authority (AD-1)** | `spool/ingestor.py` (dual-canonical path) | projection runners, dashboard | **KEEP** — go-forward authority |
| `ai_canonical_events` | 2914 | **Substrate authority (AD-1)** | `spool/ingestor.py` (dual-canonical path) | projection runners, dashboard | **KEEP** — go-forward authority |
| `execution_events` | 3680 | **AI fact spine (AD-5) / future DuckDB projection (AD-2)** | `core/telemetry/execution_spine.py` | `core/projections/` runners, intelligence routes | **KEEP in studio.db** until three-store DuckDB build; flagged for future DuckDB migration |

**AD-2 vs AD-5 boundary resolution:** AD-1 classifies `execution_events` as a derived projection
(materialized from canonical events by `execution_events_projection.py`). AD-5 confirms it as the
AI fact spine — the single self-nesting table that replaces 5 per-type tables. AD-2 targets it for
future DuckDB migration. These are consistent: it is a projection by lineage (derived from canonical
substrate) and a fact spine by schema (it carries all AI invocation dimensions). For the clean-state
pass, `execution_events` **stays in studio.db**; the DuckDB move is explicitly "forward feature
work, not clean-state" per AD-2. No action this pass.

**Current state:** the ingestor dual-writes — `canonical_events` (primary/legacy) +
`business_canonical_events`/`ai_canonical_events` (best-effort). WO-M promotes the dual-canonical
write to primary and retires `canonical_events`.

---

## Part 2 — Per-Table Decision Table (Tasks 1–6)

Verdicts: **KEEP** (studio.db permanent or until DuckDB migration) · **CONSOLIDATE** (folded into a
named table, migration-class WO executes) · **RETIRE** (DROP in WO-F) · **DuckDB** (move to
analytics store, forward work) · **AT-RISK** (surface for operator decision — writer/reader
ambiguous or feature scope unclear).

### Substrate tables

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `business_canonical_events` | 536 | **KEEP** | Go-forward substrate authority (AD-1) |
| `ai_canonical_events` | 2914 | **KEEP** | Go-forward substrate authority (AD-1) |
| `canonical_events` | 8186 | **RETIRE after WO-M** | Legacy; writer exists but is being demoted; retire after cutover parity check |

### Business cascade

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `business_projects` | 6 | **KEEP** | Cascade L1; sole project authority (PRD retired per AD-10) |
| `business_milestones` | 5 | **KEEP** | Cascade L2 |
| `business_work_orders` | 58 | **KEEP** | Cascade L3 |
| `business_tasks` | 131 | **KEEP** | Cascade L4 |
| `business_work_order_types` | 10 | **KEEP** | WO type lookup |
| `business_design_briefs` | 1 | **KEEP** | Design brief entity |

### AI fact spine

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `execution_events` | 3680 | **KEEP** (DuckDB future) | AI fact spine (AD-5); stays in studio.db until three-store build |
| `skill_invocations` | 1 | **CONSOLIDATE → execution_events** | Redundant denorm slice; WO-R |
| `agent_invocations` | 0 | **CONSOLIDATE → execution_events** | Redundant denorm slice; WO-R |
| `workflow_invocations` | 2 | **CONSOLIDATE → execution_events** | Redundant denorm slice; WO-R |
| `hook_invocations` | 3668 | **CONSOLIDATE → execution_events** | Redundant denorm slice; WO-R; volume must be migrated |
| `tool_invocations` | 3571 | **CONSOLIDATE → execution_events** | Redundant denorm slice; WO-R; volume must be migrated |
| `hook_executions` | 618 | **AT-RISK** | Populated; role overlaps `hook_invocations`; reconcile before WO-R drop |

### Memory / gotchas / docs

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `memory_entries` | 1488 | **KEEP** | Operational memory; live writer (on-memory-ingest hook) |
| `memory_fts` + 5 shadow tables | — | **KEEP** | FTS5 index for memory_entries; ride-along |
| `reg_gotchas` | 1488 | **KEEP** | Gotchas store; live writer (on-memory-ingest hook) |
| `fts_gotchas` + 4 shadow tables | — | **KEEP** | FTS5 index for reg_gotchas; ride-along |
| `ds_documents` | 12 | **KEEP** | Docs store; live writer (ds CLI) |
| `ds_documents_fts` + 4 shadow tables | — | **KEEP** | FTS5 index for ds_documents; ride-along |

### Migration bookkeeping

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `_schema_version` | 98 | **KEEP** | Migration tracking; required |
| `projection_state` | 5 | **KEEP** | Projection-runner bookkeeping |
| `projection_checkpoints` | 0 | **KEEP** | Projection-runner bookkeeping; legitimately empty |
| `log_batch_imports` | 1 | **KEEP** | Migration import tracking |
| `legacy_canonical_event_import_map` | 0 | **KEEP pending WO-M** | Backfill map for canonical migration; needed by WO-M; retire after cutover |

### Adapter / projection authority

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `adapter_authority_profiles` | 8 | **KEEP** | Adapter registry; live reader (adapter resolution routes) |
| `authority_projection_records` | 0 | **KEEP** | Live writer: `execution_spine.py:623` (INSERT); live readers: `read_models.py:45`, `upgrade/installed_state_rehydration.py`; legitimately 0 rows (feature writes on specific conditions) |
| `shared_context_packets` | 0 | **KEEP** | Adapter projection contract (global CLAUDE.md); legitimately empty — context loaded from file, not written at runtime |

### Scan run grouping (pre-spine-migration)

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `scan_runs` | 8 | **KEEP** | Run-grouping; stays as spine anchor until DuckDB migration of projections |
| `scan_deltas` | 7 | **RETIRE authority → DuckDB projection** | Per AD-10, deltas cease to be authority; become a projection over spine history. Rows are reference data for migration, not authority |

### AT-RISK: legitimately empty (unused feature, not dead)

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `agent_context_scope_policies` | 0 | **KEEP (AT-RISK)** | Reader: `core/shared_intelligence/scoped_agents.py`; no writer yet; unused feature, not dead. Surface for WO-O (gate registry) to decide whether to wire a writer or retire. |
| `agent_registry_records` | 0 | **KEEP (AT-RISK)** | Reader: `core/shared_intelligence/scoped_agents.py` + API routes; no writer yet; same disposition as above. |
| `validation_results` | 0 | **KEEP** | WO-E task 2: confirmed live (validator infrastructure); 0 rows because no validation runs have been issued in current session context |

### AT-RISK: Phase 19.4 skill-personalization scope

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `ds_friction_signals` | 0 | **AT-RISK** | Phase 19.4; scope and writer not confirmed. Surface for operator decision before WO-F. |
| `ds_user_extensions` | 0 | **AT-RISK** | Phase 19.4; scope and writer not confirmed. |
| `ds_workflow_pattern_signals` | 0 | **AT-RISK** | Phase 19.4; scope and writer not confirmed. |

### Spool raw ingest layer (populated)

These tables are the spool's raw write layer — the ingestor reads them. All KEEP.

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `raw_claude_code_events` | 7510 | **KEEP** | Spool raw; ingestor source; high volume confirms live write path |
| `raw_sentinels` | 299 | **KEEP** | Spool raw; sentinel events |
| `raw_handoffs` | 105 | **KEEP** | Spool raw; handoff hook output |
| `raw_sessions` | 115 | **KEEP** | Spool raw; session events |
| `raw_workflow_nodes` | 25 | **KEEP** | Spool raw; workflow node events |
| `raw_workflow_runs` | 2 | **KEEP** | Spool raw; workflow run events |
| `raw_skill_telemetry` | 1 | **KEEP** | Spool raw; skill telemetry events |

### Behavioral eval / discovery infrastructure

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `ds_eval_baselines` | 8 | **KEEP** | Behavioral eval harness (18.8.3 / WO-N); live data confirms active use |
| `ds_technology_signals` | 54 | **KEEP** | Project-acquisition discovery substrate (AD-9); live data |
| `ai_adapter_accounting_profiles` | 10 | **KEEP** | Adapter accounting; live data; review during WO-P capability catalog |
| `research_evidence_records` | 9 | **KEEP** | Live research records |

### Token usage (WO-A resolution)

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `raw_token_usage` | 3 | **RETIRE** | WO-A stopped writes at source (on-skill-metrics.py stripped the insert). 3 legacy rows remain. Drops in WO-F. |
| `token_usage_records` | 0 | **RETIRE** | WO-A removed the backfill mapping (legacy_backfill.py). No live writer. Drops in WO-F. |

### Analytics / projections → DuckDB (AD-2 forward work)

These tables are projection read-models. They stay until the DuckDB store is built; no action this pass.

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `validation_failures` | 530 | **DuckDB** | Read-model; populated; migrate when DuckDB store lands |
| `raw_operational_snapshots` | 28 | **DuckDB** | Read-model / analytics |
| `outcome_records` | 2 | **DuckDB** | Read-model |
| `dashboard_attention_items` | 0 | **DuckDB** | Dashboard read-model |
| `team_rollup_records` | 0 | **DuckDB** | Analytics rollup |
| `sum_analytics_run` | 0 | **DuckDB** | Analytics summary |
| `sum_skill_summary` | 0 | **DuckDB** | Analytics summary |
| `sum_*` (any remaining) | 0 | **DuckDB** | Analytics summaries |

### Findings cluster → CONSOLIDATE (AD-10; NOT retire)

These tables are **empty because the security/readiness workflows have not run yet** — empty ≠ dead
here per AD-4 discipline. They consolidate into 2 self-nesting event spines in a future
migration-class WO. (See Part 4 for spine target columns.)

**Security findings → `security_events` spine:**

| Table | Rows | Verdict |
|---|---|---|
| `sec_cve_matches` | 0 | CONSOLIDATE → security_events |
| `sec_manual_reviews` | 0 | CONSOLIDATE → security_events |
| `sec_sarif_findings` | 0 | CONSOLIDATE → security_events |
| `security_findings` | 0 | CONSOLIDATE → security_events |
| `findings` | 15 | CONSOLIDATE → security_events (migrate rows) |
| `resolved_finding_links` | 2 | CONSOLIDATE → security_events (migrate rows) |
| `compliance_review_flags` | 0 | CONSOLIDATE → security_events |
| `guard_events` | 0 | CONSOLIDATE → security_events |
| `guardrail_decisions` | 0 | CONSOLIDATE → security_events |
| `hook_findings` | 0 | CONSOLIDATE → security_events |

**Readiness findings → `readiness_events` spine:**

| Table | Rows | Verdict |
|---|---|---|
| `production_readiness_assessment_runs` | 0 | CONSOLIDATE → readiness_events |
| `production_readiness_control_results` | 0 | CONSOLIDATE → readiness_events |
| `production_readiness_findings` | 0 | CONSOLIDATE → readiness_events |
| `production_readiness_remediation_work_orders` | 0 | CONSOLIDATE → readiness_events |
| `production_readiness_skill_control_mappings` | 0 | CONSOLIDATE → readiness_events |

### PRD cluster → RETIRE (AD-10 confirmed)

`business_projects` IS what PRD was. PRD-equivalent content (intended vision) lands on the
project entity, not `prd_documents`. Entire cluster drops in WO-F.

| Table | Rows | Verdict |
|---|---|---|
| `prd_amendment_records` | 0 | RETIRE (WO-F) |
| `prd_documents` | 0 | RETIRE (WO-F) |
| `prd_handoffs` | 0 | RETIRE (WO-F) |
| `prd_plans` | 0 | RETIRE (WO-F) |
| `prd_route_reconciliation_records` | 0 | RETIRE (WO-F) |
| `prd_sessions` | 0 | RETIRE (WO-F) |
| `prd_tasks` | 0 | RETIRE (WO-F) |
| `prd_version_records` | 0 | RETIRE (WO-F) |

### pi_* cluster → RETIRE (Task 5)

Both tables have 0 rows. `core/execution/workflow_integration.py:284,295` is the sole reader
(inside `create_wave_node`). **No live writer exists** — the pi_analysis function that would have
written `pi_waves` was part of the deleted PI analysis system (Wave cleanup). The reader function
exists but the feature is dead: no rows, no writer, no call path. RETIRE per AD-4.

| Table | Rows | Verdict | Reason |
|---|---|---|---|
| `pi_waves` | 0 | RETIRE (WO-F) | No live writer; sole reader in dead code path |
| `pi_wave_tasks` | 0 | RETIRE (WO-F) | No live writer; sole reader in dead code path |

Note: `workflow_integration.py` should have the `create_wave_node` reader removed in WO-F or a
companion cleanup WO (it references a dead table).

### GitHub intake orphans → RETIRE

| Table | Rows | Verdict |
|---|---|---|
| `github_repo_adoption_decisions` | 0 | RETIRE (WO-F) |
| `github_repo_adoption_decisions_attribution_records` | 0 | RETIRE (WO-F) |
| `github_repo_adoption_decisions_dependency_findings` | 0 | RETIRE (WO-F) |
| `github_repo_adoption_decisions_evaluations` | 0 | RETIRE (WO-F) |
| `github_repo_adoption_decisions_integration_candidates` | 0 | RETIRE (WO-F) |
| `github_repo_adoption_decisions_license_findings` | 0 | RETIRE (WO-F) |
| `github_repo_adoption_decisions_pattern_references` | 0 | RETIRE (WO-F) |
| `github_repo_adoption_decisions_security_findings` | 0 | RETIRE (WO-F) |

### Decision / route / policy → RETIRE

No live writer confirmed. 0 rows. Routing is now handled deterministically via skill routing
table (AD-8) and gate registry (WO-O), not these tables.

| Table | Rows | Verdict |
|---|---|---|
| `decision_event_link` | 0 | RETIRE (WO-F) |
| `decision_log` | 0 | RETIRE (WO-F) |
| `decision_records` | 0 | RETIRE (WO-F) |
| `route_decision_records` | 0 | RETIRE (WO-F) |
| `policy_decision_records` | 0 | RETIRE (WO-F) |
| `capability_route_records` | 0 | RETIRE (WO-F) |

### Adapter / accounting dead → RETIRE

| Table | Rows | Verdict |
|---|---|---|
| `adapter_executions` | 0 | RETIRE (WO-F) |
| `adapter_result_records` | 0 | RETIRE (WO-F) |
| `ai_usage_operational_records` | 0 | RETIRE (WO-F) |
| `model_provider_profiles` | 0 | RETIRE (WO-F) |

### Execution graph unused → RETIRE

Execution graph tables (nodes, edges, outputs) have 0 rows and no live writer. The execution
model is the self-nesting `execution_events` spine (AD-5).

| Table | Rows | Verdict |
|---|---|---|
| `execution_dependencies` | 0 | RETIRE (WO-F) |
| `execution_event_links` | 0 | RETIRE (WO-F) |
| `execution_nodes` | 0 | RETIRE (WO-F) |
| `execution_outputs` | 0 | RETIRE (WO-F) |

### Projection plumbing unused → RETIRE

| Table | Rows | Verdict |
|---|---|---|
| `projection_dead_letter` | 0 | RETIRE (WO-F) |
| `projection_retry_queue` | 0 | RETIRE (WO-F) |

### reg_* mostly dead → RETIRE

| Table | Rows | Verdict | Notes |
|---|---|---|---|
| `reg_analyzed_repos` | 0 | RETIRE (WO-F) | |
| `reg_repo_extractions` | 0 | RETIRE (WO-F) | |
| `reg_research_sources` | 0 | RETIRE (WO-F) | |
| `reg_skill_deps` | 0 | RETIRE (WO-F) | |
| `reg_skills` | 0 | RETIRE (WO-F) | `ds_documents` is the live skills registry |
| `reg_workflows` | 0 | RETIRE (WO-F) | |

### raw_* dead (0-row vestigial) → RETIRE

Distinct from the spool raw tables above (which have data and live writers).

| Table | Rows | Verdict | Notes |
|---|---|---|---|
| `raw_lessons` | 0 | **AT-RISK → RETIRE** | `on-memory-ingest` hook batch-syncs into memory_entries; confirm hook no longer writes here before dropping |
| `raw_approaches` | 0 | RETIRE (WO-F) | |
| `raw_specs` | 0 | RETIRE (WO-F) | |
| `raw_tasks` | 0 | RETIRE (WO-F) | |
| `raw_planning_specs` | 0 | RETIRE (WO-F) | |
| `raw_pulse_snapshots` | 0 | RETIRE (WO-F) | |
| `raw_research` | 0 | RETIRE (WO-F) | |

### Miscellaneous 0-row dead → RETIRE

| Table | Rows | Verdict | Notes |
|---|---|---|---|
| `alert_rules` | 0 | RETIRE (WO-F) | Alert subsystem; no live writer |
| `alert_history` | 0 | RETIRE (WO-F) | |
| `artifact_records` | 0 | RETIRE (WO-F) | |
| `artifact_authority_records` | 0 | RETIRE (WO-F) | |
| `audit_runs` | 0 | RETIRE (WO-F) | |
| `blocker_resolution_records` | 0 | RETIRE (WO-F) | |
| `connector_ingestion_runs` | 0 | RETIRE (WO-F) | |
| `cor_skill_corrections` | 0 | RETIRE (WO-F) | |
| `demo_case_study_packets` | 0 | RETIRE (WO-F) | |
| `hardening_candidate_records` | 0 | RETIRE (WO-F) | |
| `installer_distribution_checks` | 0 | RETIRE (WO-F) | |
| `learning_event_records` | 0 | RETIRE (WO-F) | `learning.py` deleted in WO-C; no writer |
| `local_watch_schedule_records` | 0 | RETIRE (WO-F) | |
| `privacy_redaction_export_records` | 0 | RETIRE (WO-F) | |
| `process_runs` | 0 | RETIRE (WO-F) | |
| `release_readiness_records` | 0 | RETIRE (WO-F) | |
| `research_cache` | 0 | RETIRE (WO-F) | |
| `session_tasks` | 0 | RETIRE (WO-F) | |
| `skill_evaluation_runs` | 0 | RETIRE (WO-F) | |
| `task_attribution_records` | 0 | RETIRE (WO-F) | |
| `tool_embeddings_cache` | 0 | RETIRE (WO-F) | |
| `tool_registry` | 0 | RETIRE (WO-F) | `ds_documents` serves this role |

---

## Part 3 — DROP List (WO-F input)

These tables are confirmed RETIRE. WO-F executes the drops as a single migration class.
`canonical_events` is excluded (drops in WO-M after cutover parity check).

**Total: ~67 tables to drop in WO-F.**

### Group 1 — PRD cluster (AD-10 confirmed) [8 tables]
`prd_amendment_records`, `prd_documents`, `prd_handoffs`, `prd_plans`,
`prd_route_reconciliation_records`, `prd_sessions`, `prd_tasks`, `prd_version_records`

### Group 2 — pi_* cluster [2 tables]
`pi_waves`, `pi_wave_tasks`

### Group 3 — Token usage (WO-A resolved) [2 tables]
`raw_token_usage`, `token_usage_records`

### Group 4 — GitHub intake orphans [8 tables]
`github_repo_adoption_decisions`, `github_repo_adoption_decisions_attribution_records`,
`github_repo_adoption_decisions_dependency_findings`, `github_repo_adoption_decisions_evaluations`,
`github_repo_adoption_decisions_integration_candidates`, `github_repo_adoption_decisions_license_findings`,
`github_repo_adoption_decisions_pattern_references`, `github_repo_adoption_decisions_security_findings`

### Group 5 — Decision / route / policy [6 tables]
`decision_event_link`, `decision_log`, `decision_records`,
`route_decision_records`, `policy_decision_records`, `capability_route_records`

### Group 6 — Adapter / accounting dead [4 tables]
`adapter_executions`, `adapter_result_records`,
`ai_usage_operational_records`, `model_provider_profiles`

### Group 7 — Execution graph unused [4 tables]
`execution_dependencies`, `execution_event_links`, `execution_nodes`, `execution_outputs`

### Group 8 — Projection plumbing unused [2 tables]
`projection_dead_letter`, `projection_retry_queue`

### Group 9 — reg_* dead [6 tables]
`reg_analyzed_repos`, `reg_repo_extractions`, `reg_research_sources`,
`reg_skill_deps`, `reg_skills`, `reg_workflows`

### Group 10 — raw_* dead [6 tables]
`raw_approaches`, `raw_specs`, `raw_tasks`, `raw_planning_specs`,
`raw_pulse_snapshots`, `raw_research`
(+ `raw_lessons` pending on-memory-ingest hook writer check — AT-RISK)

### Group 11 — Miscellaneous dead [19 tables]
`alert_rules`, `alert_history`, `artifact_records`, `artifact_authority_records`, `audit_runs`,
`blocker_resolution_records`, `connector_ingestion_runs`, `cor_skill_corrections`,
`demo_case_study_packets`, `hardening_candidate_records`, `installer_distribution_checks`,
`learning_event_records`, `local_watch_schedule_records`, `privacy_redaction_export_records`,
`process_runs`, `release_readiness_records`, `research_cache`, `session_tasks`,
`skill_evaluation_runs`, `task_attribution_records`, `tool_embeddings_cache`, `tool_registry`

### Deferred to WO-M
`canonical_events` — retire after dual-canonical cutover parity check (not WO-F).

### Deferred to WO-R (consolidate, not drop)
`skill_invocations`, `agent_invocations`, `workflow_invocations`,
`hook_invocations`, `tool_invocations`
(`hook_executions` pending reconciliation with `hook_invocations`)

### Deferred to future finding-spine WO (consolidate, not drop)
All tables in the security_events and readiness_events consolidate lists above.
`scan_deltas` — ceases to be authority; drops after spine migration and projection build.

---

## Part 4 — Consolidate List (AD-10)

### 4a — `security_events` spine

Self-nesting append-only event spine. Peer to `execution_events` (AD-5).
Models: `scan_run` (root) → `finding` (child) → `occurrence/location` (grandchild).

**Sources consolidated in:** `sec_cve_matches`, `sec_manual_reviews`, `sec_sarif_findings`,
`security_findings`, `findings` (15 rows — migrate), `resolved_finding_links` (2 rows — migrate),
`compliance_review_flags`, `guard_events`, `guardrail_decisions`, `hook_findings`.

**Target columns:**

| Column | Type | Description |
|---|---|---|
| `event_id` | UUID PK | Unique event identifier |
| `parent_event_id` | UUID FK → self | Self-nesting: scan_run → finding → occurrence |
| `event_type` | text | `scan_run.started` · `finding.recorded` · `finding.status_changed` · `finding.resolved` |
| `correlation_id` | UUID | → `ai_canonical_events` skill run that produced it |
| `project_id` | UUID FK | Project scope |
| `work_order_id` | UUID FK | WO scope (PR-level scans) |
| `scanner_type` | text | `SAST` · `DAST` · `SCA` · `secrets` |
| `cwe_id` | text | CWE identifier (nullable) |
| `owasp_category` | text | OWASP category (nullable) |
| `cve_id` | text | CVE identifier (nullable) |
| `file_path` | text | Source file (nullable) |
| `line_number` | integer | Line in source file (nullable) |
| `vuln_class` | text | Vulnerability class (injection, auth, crypto, etc.) |
| `exploitability` | text | `critical` · `high` · `medium` · `low` · `info` |
| `severity` | text | `critical` · `high` · `medium` · `low` · `info` |
| `title` | text | Short finding description |
| `body` | text | Full finding detail |
| `created_at` | datetime | Event timestamp (append-only; never updated) |

**Status:** status is NOT a column — it is an event. Current status of a finding = the latest
`finding.status_changed` event's `vuln_class` payload. Projections over the spine produce
"what's open right now" (→ DuckDB per AD-2). Spine is append-only/immutable.

**`scan_runs` relationship:** `scan_runs` (8 rows, KEEP) provides run grouping. A
`scan_run.started` event in `security_events` references the `scan_runs` row via `parent_event_id`
= scan_run's event_id. `scan_deltas` becomes a projection over spine history (ceases to be
authority).

### 4b — `readiness_events` spine

Self-nesting append-only event spine. Peer to `security_events`.
Models: `assessment` (root) → `control_result` (child) → `sub-control` (grandchild).

**Sources consolidated in:** `production_readiness_assessment_runs`,
`production_readiness_control_results`, `production_readiness_findings`,
`production_readiness_remediation_work_orders`, `production_readiness_skill_control_mappings`.

**Target columns:**

| Column | Type | Description |
|---|---|---|
| `event_id` | UUID PK | Unique event identifier |
| `parent_event_id` | UUID FK → self | Self-nesting: assessment → control_result → sub-control |
| `event_type` | text | `assessment.started` · `control_result.recorded` · `control_result.status_changed` · `assessment.closed` |
| `correlation_id` | UUID | → `ai_canonical_events` skill run that produced it |
| `project_id` | UUID FK | Project scope |
| `work_order_id` | UUID FK | WO scope (optional) |
| `framework` | text | `SOC2` · `NIST` · `ISO27001` · `custom` |
| `control_id` | text | Control identifier (e.g., CC6.1, AC-2) |
| `result` | text | `pass` · `fail` · `na` · `incomplete` (current via status-as-event) |
| `evidence` | text | Evidence reference or attestation text |
| `remediation_wo` | UUID FK | → `business_work_orders` (remediation tracking) |
| `title` | text | Control name / short description |
| `body` | text | Full assessment detail |
| `created_at` | datetime | Event timestamp (append-only) |

**Status:** same append-only invariant as `security_events`. Current result = latest
`control_result.status_changed` event payload. DuckDB projection produces current posture view.

---

## Summary — Decision Counts

| Verdict | Table count (approx) |
|---|---|
| KEEP (studio.db permanent) | ~35 (incl. 16 FTS shadow tables) |
| KEEP pending DuckDB migration | ~10 (analytics/projection read-models) |
| CONSOLIDATE → execution_events (WO-R) | 5 (+1 AT-RISK: hook_executions) |
| CONSOLIDATE → security_events (future WO) | 10 |
| CONSOLIDATE → readiness_events (future WO) | 5 |
| RETIRE in WO-F | ~67 |
| RETIRE in WO-M | 1 (canonical_events) |
| AT-RISK / surface for decision | 5 |
| **Total** | **~138** (remainder in AT-RISK or scan_deltas transition) |

**Net: 154 tables → ~35 in studio.db clean state** (before DuckDB build moves analytics out,
leaving ~12-15 authority tables + FTS shadows + bookkeeping). This is the ~90% reduction the
census projected.

---

## Open Items for WO-F Author

1. **`raw_lessons` AT-RISK:** verify `runtime/hooks/meta/on-memory-ingest.py` no longer writes
   to `raw_lessons` before adding to drop migration. If it still does, patch the hook first.

2. **`hook_executions` vs `hook_invocations` reconciliation:** both have live data (618 vs 3668
   rows). Determine which is authoritative before WO-R drops either. One must be the source,
   one the redundant slice.

3. **`ds_friction_signals` / `ds_user_extensions` / `ds_workflow_pattern_signals`:** Phase 19.4
   scope unclear. Get operator confirmation before including in WO-F drops.

4. **`workflow_integration.py` reader cleanup:** `create_wave_node` reads `pi_waves` /
   `pi_wave_tasks` (lines 284, 295). Remove or guard this reader when WO-F drops the tables.

5. **`scan_deltas` transition timing:** keep until `security_events` spine is authored and a
   DuckDB projection for deltas is built. Coordinate with the finding-spine WO.
