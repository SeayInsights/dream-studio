# Pass 1l — Storage Architecture Audit
*Phase 1 analysis | 2026-05-22*
*Focus: Intent #1 (SQLite-first authority)*

---

## Stated Architectural Intents

1. **SQLite-first authority** — all runtime STATE must be SQLite-backed. File-based state is v1 rot. **THIS PASS'S SOLE EVALUATION LENS.**
2. **Security audit during brownfield onboarding** — security skills run during project intake; findings stored in SQLite.
3. **Security audit as SDLC lifecycle gate** — greenfield projects must pass security audit before going live.
4. **Canonical events as the spine** — all state changes flow through `canonical_events`. Direct table writes without event emission are anomalies.
5. **Marker file authority for attribution** — `.dream-studio-project` markers are identity source; `ds_projects` is metadata storage.

Intent #1 is the exclusive lens for this pass. Intents #2–#5 are in scope only where they interact with storage architecture decisions (e.g., a file-backed store that would need to be SQLite-backed to support Intent #4 compliance).

---

## Storage Architecture Map

### Category A: SQLite-Backed (Intent-Aligned)

The single canonical database is `~/.dream-studio/state/studio.db` (6.3 MB as of 2026-05-22). All tables below live in this file. Connection management is via `core/config/database.py`, which declared itself the "SINGLE SOURCE OF TRUTH" for all SQLite connections.

#### A.1 — Active Tables (data present)

| Table | Rows | Domain | Notes |
|-------|------|--------|-------|
| canonical_events | 1,853 | telemetry | Primary event spine — the authoritative record of all system activity |
| execution_events | 929 | telemetry | Projection of canonical_events; backfilled via migration 060 |
| hook_invocations | 917 | telemetry | Written by `core/telemetry/emitters.py` via on-tool-activity hook only |
| tool_invocations | 917 | telemetry | Parallel record per tool use; same source as hook_invocations |
| fts_gotchas | 1,488 | learning | FTS5 virtual table over reg_gotchas (shadow table) |
| fts_gotchas_docsize | 1,488 | learning | FTS5 shadow |
| reg_gotchas | 1,488 | learning | Operator gotchas ingested via ds memory commands |
| raw_sentinels | 113 | telemetry | Dedup keys preventing double-write of session/handoff records |
| fts_gotchas_data | 74 | learning | FTS5 shadow data |
| fts_gotchas_idx | 72 | learning | FTS5 shadow index |
| _schema_version | 61 | infra | Migration version tracker (61 migrations applied) |
| validation_failures | 57 | telemetry | Schema validation errors during spool ingest (all from on_pulse, event_type='execution.completed') |
| ds_technology_signals | 54 | sdlc | Populated via session harvester ingest |
| raw_sessions | 51 | telemetry | Session open/close records written by on-session-start / on-session-end |
| hook_executions | 45 | telemetry | ONLY records on_pulse executions; all other hooks absent |
| ds_documents_fts_data | 27 | sdlc | FTS5 shadow for ds_documents |
| raw_handoffs | 26 | telemetry | Handoff records from on-stop-handoff.py |
| ds_documents_fts_idx | 25 | sdlc | FTS5 shadow index |
| ds_projects | 25 | sdlc | 1 real active (Dream Studio), 1 paused (Dream Command), 23 test fixture pollution |
| raw_workflow_nodes | 25 | workflow | Node execution records from 2 studio-onboard runs |
| ds_work_orders | 14 | sdlc | All for Dream Command — 2 complete, 1 in_progress, 11 open |
| sqlite_sequence | 14 | infra | SQLite autoincrement tracker |
| ds_documents | 12 | sdlc | Session handoffs and architecture decisions |
| ds_documents_fts | 12 | sdlc | FTS5 virtual table over ds_documents |
| ds_documents_fts_docsize | 12 | sdlc | FTS5 shadow |
| ds_work_order_types | 10 | sdlc | Type registry — 10 fully defined work order types |
| ds_tasks | 9 | sdlc | Tasks for Dream Command work orders |
| research_evidence_records | 9 | research | Research evidence |
| raw_operational_snapshots | 5 | telemetry | Health snapshots (all show "no github_repo configured") |
| ds_milestones | 4 | sdlc | Dream Command milestones, all status=pending |
| raw_token_usage | 3 | telemetry | All rows have input_tokens=0, output_tokens=0, skill_name=unknown — effectively empty |
| memory_fts_data | 2 | memory | FTS5 shadow for memory search index |
| outcome_records | 2 | workflow | Workflow outcome records for 2 studio-onboard runs |
| raw_workflow_runs | 2 | workflow | 2 studio-onboard runs archived from workflows.json |
| reg_projects | 2 | telemetry | Directory-name-based project registry (loose attribution; not UUID-keyed) |
| workflow_invocations | 2 | workflow | Parallel to raw_workflow_runs; same 2 studio-onboard runs |
| ds_design_briefs | 1 | sdlc | Dream Command brief, status=locked |
| ds_documents_fts_config | 1 | sdlc | FTS5 shadow config |
| fts_gotchas_config | 1 | learning | FTS5 shadow config |
| memory_fts_config | 1 | memory | FTS5 shadow config |
| skill_invocations | 1 | telemetry | Single row: skill=unknown, session telemetry type |

**Total: 41 tables with data** (including FTS shadow tables)

#### A.2 — Empty Tables (schema present, no data)

These tables have schema but zero rows. They represent either aspirational infrastructure, inactive domains, or write-path failures.

| Table | Domain | Why empty |
|-------|--------|-----------|
| adapter_authority_profiles | adapters | Adapter authority system not activated |
| adapter_executions | adapters | No adapter executions recorded |
| adapter_result_records | adapters | No adapter results |
| agent_context_scope_policies | agents | Agent scoping not in use |
| agent_invocations | agents | Agent tracking not wired to write path |
| agent_registry_records | agents | No agents registered |
| agent_result_records | agents | No agent results |
| ai_adapter_accounting_profiles | billing | Not activated |
| ai_usage_operational_records | billing | Not activated |
| alert_history | monitoring | Alert system not activated |
| alert_rules | monitoring | Alert rules not configured |
| artifact_authority_records | artifacts | Not activated |
| artifact_records | artifacts | Not activated |
| audit_runs | audit | No audit runs have been executed via CLI |
| authority_projection_records | authority | Not activated |
| automation_checkpoints | workflow | Checkpoint system not wired |
| automation_log | workflow | Automation logging not active |
| blocker_resolution_records | sdlc | No blockers resolved |
| capability_center_records | routing | Not activated |
| capability_route_records | routing | Not activated |
| career_application_events | career | Career pack not activated (external dependency) |
| career_application_field_mappings | career | Career pack not activated |
| career_applications | career | Career pack not activated |
| career_browser_automation_runs | career | Career pack not activated |
| career_case_studies | career | Career pack not activated |
| career_cover_letter_versions | career | Career pack not activated |
| career_evidence_refs | career | Career pack not activated |
| career_interview_story_bank | career | Career pack not activated |
| career_job_opportunities | career | Career pack not activated |
| career_portfolio_artifacts | career | Career pack not activated |
| career_profile_fields | career | Career pack not activated |
| career_profiles | career | Career pack not activated |
| career_resume_versions | career | Career pack not activated |
| career_role_targets | career | Career pack not activated |
| career_scorecards | career | Career pack not activated |
| compliance_review_flags | security | Security gates not executing |
| connector_ingestion_runs | connectors | Connector system not activated |
| cor_skill_corrections | learning | Skill corrections not flowing from on-agent-correction hook to DB |
| dashboard_attention_items | dashboard | Dashboard not writing attention items |
| dashboard_authority_reconciliation_records | dashboard | Not activated |
| decision_event_link | authority | Not activated |
| decision_log | authority | Not activated |
| decision_records | authority | Not activated |
| demo_case_study_packets | career | Not activated |
| execution_dependencies | workflow | Execution graph tables empty despite workflow runs |
| execution_event_links | workflow | Not populated |
| execution_nodes | workflow | Empty — workflow execution writes to raw_workflow_nodes instead |
| execution_outputs | workflow | Empty — outputs not tracked in canonical graph |
| github_repo_adoption_decisions | github | Repo analysis never run |
| github_repo_attribution_records | github | Repo analysis never run |
| github_repo_dependency_findings | github | Repo analysis never run |
| github_repo_evaluations | github | Repo analysis never run |
| github_repo_integration_candidates | github | Repo analysis never run |
| github_repo_license_findings | github | Repo analysis never run |
| github_repo_pattern_references | github | Repo analysis never run |
| github_repo_security_findings | github | Repo analysis never run |
| guardrail_decisions | security | Guardrail system not activated |
| guardrail_rules_audit | security | Guardrail system not activated |
| hardening_candidate_records | security | Hardening not run |
| hook_findings | security | Hook security scan findings not stored |
| installer_distribution_checks | install | Installer check system not activated |
| learning_event_records | learning | Learning events not being written |
| legacy_canonical_event_import_map | telemetry | Migration/import tool not run |
| local_watch_schedule_records | scheduling | Not activated |
| log_batch_imports | telemetry | Batch import log not active |
| memory_fts | memory | FTS5 virtual table (empty when no memory docs loaded) |
| memory_fts_content | memory | FTS5 shadow |
| memory_fts_docsize | memory | FTS5 shadow |
| memory_fts_idx | memory | FTS5 shadow |
| model_provider_profiles | billing | Not activated |
| pi_analysis_runs | project_intelligence | No analysis ever executed |
| pi_bugs | project_intelligence | No analysis ever executed |
| pi_components | project_intelligence | No analysis ever executed |
| pi_dependencies | project_intelligence | No analysis ever executed |
| pi_improvements | project_intelligence | No analysis ever executed |
| pi_violations | project_intelligence | No analysis ever executed |
| pi_wave_tasks | project_intelligence | No analysis ever executed |
| pi_waves | project_intelligence | No analysis ever executed |
| policy_decision_records | authority | Not activated |
| prd_amendment_records | prd | PRD system not used |
| prd_documents | prd | PRD system not used |
| prd_handoffs | prd | PRD system not used |
| prd_plans | prd | PRD system not used |
| prd_route_reconciliation_records | prd | PRD system not used |
| prd_sessions | prd | PRD system not used |
| prd_tasks | prd | PRD system not used |
| prd_version_records | prd | PRD system not used |
| privacy_redaction_export_records | compliance | Not activated |
| process_runs | workflow | Not activated |
| production_readiness_assessment_runs | readiness | Not activated |
| production_readiness_control_results | readiness | Not activated |
| production_readiness_findings | readiness | Not activated |
| production_readiness_remediation_work_orders | readiness | Not activated |
| production_readiness_skill_control_mappings | readiness | Not activated |
| project_assumption_records | sdlc | Not activated |
| project_change_order_records | sdlc | Not activated |
| project_health_scorecards | sdlc | Not activated |
| project_intake_questions | sdlc | Intake system not wired |
| project_intake_records | sdlc | Intake system not wired |
| project_milestone_records | sdlc | Not activated |
| project_readiness_scorecards | sdlc | Not activated |
| project_work_order_authority_records | sdlc | Not activated |
| raw_approaches | learning | `cmd_memory_ingest_sessions` not called; `SessionHarvester` path not activated |
| raw_lessons | learning | Lesson pipeline not activated |
| raw_planning_specs | learning | Planning spec ingestion not activated |
| raw_pulse_snapshots | telemetry | Pulse snapshot writer not writing to table |
| raw_research | learning | Research not ingested |
| raw_skill_telemetry | telemetry | Skill telemetry pipeline writes to file (telemetry-buffer.jsonl), not this table |
| raw_specs | learning | Not activated |
| raw_tasks | learning | Not activated |
| reg_analyzed_repos | github | Repo analysis never run |
| reg_repo_extractions | github | Not activated |
| reg_repo_research_links | github | Not activated |
| reg_research_sources | research | Not activated |
| reg_skill_deps | registry | Not activated |
| reg_skills | registry | Skill registry exists in schema, but `hydrate_registry_once` does not persist to this table in practice |
| reg_workflows | registry | Workflow registry exists in schema, not populated |
| release_readiness_records | readiness | Not activated |
| research_cache | research | Not activated |
| risk_mitigations | sdlc | Risk register not activated |
| risk_register | sdlc | Risk register not activated |
| route_decision_records | routing | Not activated |
| sec_cve_matches | security | Security scanning not activated |
| sec_hook_checks | security | Hook security checks not stored |
| sec_manual_reviews | security | Manual reviews not stored |
| sec_sarif_findings | security | SARIF scanning not activated |
| security_findings | security | Security pipeline not activated |
| session_tasks | sdlc | Not activated |
| shared_context_packets | context | Context packet system not activated |
| skill_evaluation_runs | learning | Skill evaluation not run |
| sum_analytics_run | analytics | Analytics rollup not run |
| sum_skill_summary | analytics | Analytics rollup not run |
| task_attribution_records | telemetry | Task attribution not wired |
| team_rollup_records | sdlc | Team rollup not activated |
| telemetry_entity_registry | telemetry | Entity registry not populated |
| telemetry_module_registry | telemetry | Module registry not populated |
| token_usage_records | telemetry | Token tracking writes to files, not to this table |
| tool_embeddings_cache | tools | Embedding cache not activated |
| tool_registry | tools | Tool registry not populated |
| validation_results | testing | Validation results not stored |
| workflow_agent_skill_mappings | workflow | Workflow-agent mapping not populated |

**Total: 141 empty tables**

The ratio of empty to active tables (141:41, roughly 3.4:1) indicates that the SQLite schema has grown substantially ahead of the write-path implementations. A large fraction of the schema is aspirational infrastructure.

---

### Category B: File-Backed (Intent Divergence)

These are runtime state stores that persist entirely or primarily in files rather than SQLite. Each represents a direct gap against Intent #1.

---

#### B.1 — `~/.dream-studio/state/workflows.json`
- **Contains:** JSON object with `schema_version` (int) and `active_workflows` (dict keyed by workflow run key; each value holds workflow name, YAML path, node list, current status, start time, node results). Currently `{"schema_version": 1, "active_workflows": {}}` — no active workflows.
- **Writer:** `control/execution/workflow/state.py` — `cmd_start` writes the initial entry; `WorkflowRunner.advance` and `WorkflowRunner.run` update node state; `_try_archive_and_prune` removes the entry on completion and writes the archived record to `raw_workflow_runs` + `raw_workflow_nodes`.
- **Readers:** `cmd_status` and `cmd_list` in `control/execution/workflow/state.py`; `on-workflow-progress` hook (Stop chain) reads to check for in-flight workflows.
- **Why file-based:** Legacy v1 design. The module was built before `workflow_invocations` was added (migration 034). The file provides the live execution state buffer during a workflow run; SQLite receives only the completed archive.
- **SQLite equivalent:** `workflow_invocations` (2 rows) and `raw_workflow_runs` (2 rows) hold the same runs but only after completion. No live/in-flight workflow state exists in SQLite.
- **Migration documented:** Not in any migration plan file found. The dual-store pattern (file while running, SQLite after completion) is the current de facto architecture.
- **Size:** 54 bytes (empty — no active workflows at audit time)

---

#### B.2 — `~/.dream-studio/state/workflow-checkpoint.json`
- **Contains:** JSON object with `workflow_key`, `last_node`, `status`, and `timestamp`. Current value shows `wf-fail-1 / n1 / failed / 2026-05-20T21:59:02Z` — a stale failed test checkpoint.
- **Writer:** `control/execution/workflow/state.py` — written when a workflow node fails as a crash recovery marker.
- **Readers:** `WorkflowRunner.run` on startup — checks if a matching checkpoint exists to resume after failure.
- **Why file-based:** Crash recovery coordination artifact. Needs to survive process death, making a write-ahead file pattern understandable. However, SQLite WAL mode is already crash-safe and could serve the same purpose.
- **SQLite equivalent:** None exists. `automation_checkpoints` table is empty and not wired to this path.
- **Migration documented:** No.
- **Size:** 132 bytes

---

#### B.3 — `~/.dream-studio/state/active_task.json`
- **Contains:** JSON object with `task_id`, `work_order_id`, `milestone_id`, `project_id` — the current operator task pointer. Does NOT currently exist (not found at either candidate path).
- **Writer:** `core/sdlc/active_task.py:set_active_task()` — called by `ds task set-active` CLI command; also called by `work-order task-done` via `clear_active_task()`.
- **Readers:** `core/sdlc/active_task.py:get_active_task()` — called by `ds task active`; zero DB involvement on read path.
- **Why file-based:** Explicit design decision. `DS_ACTIVE_TASK_PATH` env var points to this file. The CLI audit (1c) identified this as a flagged violation — SQLite is read to resolve the task chain but the result is persisted to a file.
- **SQLite equivalent:** `ds_tasks` and `ds_work_orders` tables contain the full task graph. An `active_task` flag column in `ds_tasks` or a `ds_active_pointer` single-row table would replace this.
- **Migration documented:** No.
- **Size:** 0 bytes (file does not exist at audit time)

---

#### B.4 — `~/.dream-studio/state/activity.json`
- **Contains:** JSON object with `agents` array; each entry has `id`, `name`, `status`, `task`, `elapsed`, `ts`. Tracks recent tool call activity for the dashboard agent feed. Current: 1,275 bytes, last-written timestamp is from this audit session.
- **Writer:** `core/telemetry/tool_tracking.py` — `_activity_path()` returns the path; written by `on-tool-activity` hook on every PostToolUse event.
- **Readers:** Dashboard API (`/api/v1/agents/activity`); `ds analytics` CLI command reads it via `control/skills/completion.py`.
- **Why file-based:** Originally built as a lightweight real-time feed. The dashboard needs low-latency access to the last N tool calls without a DB query.
- **SQLite equivalent:** `hook_invocations` and `tool_invocations` tables hold per-tool-use records (917 rows each). `activity.json` is a denormalized window view over recent tool calls.
- **Migration documented:** No.
- **Size:** 1,275 bytes

---

#### B.5 — `~/.dream-studio/state/pending-handoff.json`
- **Contains:** JSON object with `session_id`, `triggered_at` (Unix timestamp), `cwd`, `invocation_flags`, `status` (`pending` or `in_progress`). Current: `{"session_id": "dd1a4f73...", "triggered_at": 1779410621, ..., "status": "in_progress"}` — a stale in-progress handoff from 2026-05-21.
- **Writer:** `runtime/hooks/meta/on-context-threshold.py:_write_pending_handoff()` — written when context usage crosses 75%.
- **Readers:** `runtime/hooks/meta/on-prompt-validate.py:_check_pending_handoff()` — reads and mutates status from `pending` to `in_progress`; `runtime/hooks/meta/on-stop-dispatch.py` checks for the file's existence at Stop time.
- **Why file-based:** Cross-process coordination between the context threshold hook (writes) and the prompt validate hook (reads). The two hooks run in separate processes; file is the only shared state channel available.
- **SQLite equivalent:** None. `shared_context_packets` table exists but is empty and not wired to this path. A `ds_handoff_requests` table with session_id as primary key would directly replace this.
- **Migration documented:** No.
- **Size:** 164 bytes. Note: the current file is stale — the `triggered_at` timestamp is ~16 hours old as of audit time. There is no TTL enforcement that clears stale `in_progress` records.

---

#### B.6 — `~/.dream-studio/state/platform.json`
- **Contains:** JSON object with platform detection results: `os_name`, `os_version`, `shell`, `python_version`, `terminal`, `is_windows`, `is_macos`, `is_linux`.
- **Writer:** `core/config/platform.py:get_platform_profile()` — writes cache on first call when the file does not exist.
- **Readers:** `core/config/platform.py:get_platform_profile()` — reads cached profile on subsequent calls; `core/telemetry/token_capture.py` imports `get_platform_profile`.
- **Why file-based:** Performance cache to avoid repeated OS detection on every hook invocation. The detected values do not change between sessions on the same machine.
- **SQLite equivalent:** None. The data could live in a `ds_machine_profile` table alongside `machine_id`.
- **Migration documented:** No.
- **Size:** 218 bytes

---

#### B.7 — `~/.dream-studio/state/installed-version`
- **Contains:** Plain text string — the installation date stamp used as the version identifier (e.g., `2026-05-17`).
- **Writer:** `integrations/installer/claude_code.py` — written as the final step of a successful install; `interfaces/cli/ds.py` also reads and compares it against `VERSION` file.
- **Readers:** `emitters/claude_code/run.py:_check_version_drift()` — reads on every hook invocation to detect version mismatch; `interfaces/cli/ds.py:_check_version_drift()`.
- **Why file-based:** Install-time artifact. Version markers are conventionally file-based in most tooling.
- **SQLite equivalent:** None. Could be a row in a `ds_installation_records` table, but the file-based pattern here is lower-severity than stateful runtime stores because it only changes on reinstall.
- **Migration documented:** No.
- **Size:** 12 bytes

---

#### B.8 — `~/.dream-studio/state/machine_id`
- **Contains:** UUID string (e.g., `c6676983-2495-456b-86b9-2bf9e851c7f9`). Stable identity token for telemetry attribution.
- **Writer:** `core/telemetry/machine_id.py` — generates and writes UUID on first call if the file does not exist.
- **Readers:** `core/telemetry/token_capture.py:handle_post_tool_use()` uses `get_machine_id()`; diagnostics entries embed `machine_id`; `core/telemetry/diagnostics.py`.
- **Why file-based:** Standard pattern for stable machine identity — UUID is written once and never changes. The `DS_MACHINE_ID_PATH` env var makes it overridable for tests.
- **SQLite equivalent:** None. Could be stored in a `ds_machine_profile` singleton table alongside `platform.json` data.
- **Migration documented:** No.
- **Size:** 36 bytes

---

#### B.9 — `~/.dream-studio/state/hook-timing.jsonl`
- **Contains:** JSONL — one JSON object per hook invocation, with `handler`, `duration_ms`, `ts`, and sometimes `status`. Written by every hook dispatcher.
- **Writer:** `control/execution/dispatch_helpers.py:write_timing()` and `control/execution/dispatch_tracking.py` — both append to this file. Called by `execute_handlers` in the dispatcher chain.
- **Readers:** `interfaces/cli/ds_analytics/harvester.py:harvest_hook_timing()` — reads the full file on every `ds analytics` invocation to compute per-handler averages; `interfaces/cli/ds_analytics/main.py` displays the aggregated result.
- **Why file-based:** Hot path — written on every tool use (1,202 on-tool-activity invocations per the 1d audit), before SQLite write overhead would be acceptable. The file is append-only, which is faster than a SQLite INSERT under concurrent hook processes.
- **SQLite equivalent:** `hook_executions` table exists (45 rows) but only records `on_pulse` — it is NOT the hook_timing store for the dispatch chain. A `hook_timing_records` table would be required. The analytics harvester would need to be rewritten against it.
- **Migration documented:** No.
- **Size:** 392,668 bytes / 3,645 lines. The largest file-based state store by volume.

---

#### B.10 — `~/.dream-studio/state/skill-usage.jsonl`
- **Contains:** JSONL — 3 lines. Fields: `ts`, `skill`, `mode`, `session`, `recommended_model`. All 3 records have `skill=unknown`, `mode=""`, `session=""` — a schema inconsistency where skill identification is not resolving.
- **Writer:** `control/skills/metrics.py:write_skill_usage()` — called by `on-skill-metrics` hook; `control/skills/completion.py` also writes a parallel record to the same file.
- **Readers:** `runtime/hooks/meta/on-skill-telemetry.py:get_session_skills()` — reads file to extract skills active in current session; `interfaces/cli/ds_analytics/harvester.py` (skill usage timeline).
- **Why file-based:** Same hot-path rationale as hook-timing.jsonl. Written on skill invocation before the stop-time ingest.
- **SQLite equivalent:** `raw_skill_telemetry` table exists but is empty. The `telemetry-buffer.jsonl` file is a parallel write target for the same data. Three-way divergence: `skill-usage.jsonl`, `telemetry-buffer.jsonl`, and `raw_skill_telemetry` all represent skill usage — none is authoritative.
- **Migration documented:** No.
- **Size:** 366 bytes / 3 lines

---

#### B.11 — `~/.dream-studio/state/telemetry-buffer.jsonl`
- **Contains:** JSONL — 1 line. Fields: `skill_name`, `invoked_at`, `success`. Current record has `skill_name=unknown`.
- **Writer:** `runtime/hooks/meta/on-skill-telemetry.py:write_telemetry()` — writes at Stop time.
- **Readers:** `interfaces/cli/pulse_collector.py` — batch-imports the buffer into DB, rotates the file, rebuilds summaries.
- **Why file-based:** Designed as a transient buffer to be consumed by `pulse_collector`. The buffer pattern is intentional — writes accumulate between pulse collections.
- **SQLite equivalent:** `raw_skill_telemetry` is the intended target after pulse_collector batch-imports. The pipeline is: `on-skill-telemetry.py` → `telemetry-buffer.jsonl` → `pulse_collector.py` → `raw_skill_telemetry`. In practice `raw_skill_telemetry` is empty, meaning the buffer has never been flushed.
- **Migration documented:** No migration needed — the architecture intends this as transient. The gap is the flush pipeline being broken.
- **Size:** 91 bytes / 1 line

---

#### B.12 — `~/.dream-studio/state/diagnostics/token-capture.jsonl`
- **Contains:** JSONL — performance timing records with `ts`, `category` (`performance`), `source` (`token_capture.handle_post_tool_use`), `machine_id`, `session_id`, `context.step`, `duration_ms`. Contains NO token counts — only timing data.
- **Writer:** `core/telemetry/diagnostics.py` — appended by `core/telemetry/token_capture.py:handle_post_tool_use()`. The diagnostics module derives the filename from the `source` parameter.
- **Readers:** `interfaces/cli/ds.py:_diagnostics_dispatch` (branch `list`) — reads `*.jsonl` files from the diagnostics directory.
- **Why file-based:** Diagnostic output path — intentionally separate from the main telemetry pipeline to avoid circular dependency. Also supports the `ds diagnostics clear` command which truncates files.
- **SQLite equivalent:** None. The `DS_DIAGNOSTICS_DIR` env var configures this directory. No diagnostics table in the schema.
- **Migration documented:** No. The 1c CLI audit flagged `ds diagnostics list/clear` as a file-based violation.
- **Size:** 3,690 bytes (active as of audit date — still being written)

---

#### B.13 — `~/.dream-studio/.sessions/` (handoff and recap files)
- **Contains:** 58 markdown files across 6 date-partitioned directories (2026-05-17 through 2026-05-22). Two file types: `handoff-{session_id}.md` (~35 KB each for full handoffs; ~334 bytes for stub handoffs) and `recap-{session_id}.md` (similar sizes). The large files contain full session context; the small ones are stub records.
- **Writer:** `runtime/hooks/meta/on-stop-handoff.py` — writes both files at Stop time. `on-stop-dispatch.py` orchestrates the call.
- **Readers:** `ds memory ingest` (`ds_memory.py:cmd_memory_ingest`) reads these files to ingest handoffs into SQLite (`ds_documents`, `reg_gotchas`); `runtime/hooks/meta/on-prompt-validate.py` checks `pending-handoff.json` to inject handoff content into the next session's context.
- **Why file-based:** Session boundary artifact. The files serve two purposes: (1) human-readable session records, and (2) input to the memory ingest pipeline. The markdown format is intentional for (1). For (2), they are a staging area for eventual SQLite ingestion.
- **SQLite equivalent:** `raw_handoffs` (26 rows) and `ds_documents` (12 rows) hold ingested handoff data. The `.sessions/` files are the pre-ingest staging layer. The 58 files represent sessions that have not yet been fully ingested.
- **Migration documented:** The `ds memory ingest` command is the documented path. The ingest is manual, not automatic.
- **Size:** 58 files, ranging from 334 bytes to ~36 KB per file

---

#### B.14 — `~/.dream-studio/integrations/claude_code/manifest.json`
- **Contains:** JSON with `schema_version`, `tool`, `scope`, `ds_version`, `installed_at`, and `files` (array of 515 items — the complete list of installed files at last install time).
- **Writer:** `integrations/installer/claude_code.py` — written at install completion as the installation record.
- **Readers:** `integrations/manifest.py` — reads to validate installed file list.
- **Why file-based:** Install-time artifact. Same rationale as `installed-version` — records the state of a discrete install event.
- **SQLite equivalent:** None. Could be a single row in a `ds_installation_records` table with `files` as a JSON blob. The `DS_DREAM_STUDIO_HOME` env var points to this store indirectly.
- **Migration documented:** No.
- **Size:** Contains 515 file paths. File not directly size-measured but estimated ~50 KB based on item count.

---

#### B.15 — `~/.dream-studio/events/.sessions/{pid}.json` (spool session coordination)
- **Contains:** Per-process session coordination files. Each file: `{"session_id": "...", "pid": ...}`. 1,102 files — one per process invocation.
- **Writer:** `emitters/claude_code/run.py` — writes a session coordination file when a hook process starts.
- **Readers:** The spool ingestor uses these to correlate event files with sessions.
- **Why file-based:** Process-boundary coordination artifact. Each hook invocation is a separate process; the session ID must be communicated via filesystem since there is no shared memory.
- **SQLite equivalent:** These are transient coordination files. Their content (session_id → pid mapping) is not directly representable in the current SQLite schema, though `raw_sessions` could carry a pid field.
- **Migration documented:** No. These are not runtime state in the traditional sense — they are process bootstrap artifacts.
- **Size:** 1,102 files × 68 bytes = ~74 KB

---

#### B.16 — `.dream-studio-project` marker files (repository root)
- **Contains:** JSON or plain UUID string identifying the `ds_projects.project_id` for the repository.
- **Writer:** `core/projects/mutations.py:write_project_marker()` — called by `ds project register`.
- **Readers:** `emitters/claude_code/project.py` — reads the marker to get project_id for event attribution; `core/sdlc/cwd_resolver.py:resolve_project_context()` — walks up the directory tree to find the marker.
- **Why file-based:** **Intent #5 explicitly designates this as authoritative.** Marker files are the identity source by architectural decision, not by technical limitation. `ds_projects` is explicitly metadata storage, not the identity authority.
- **SQLite equivalent:** N/A — marker files are the designated authority. This is an **intentional** architectural choice.
- **Migration documented:** N/A — this is the current Intent #5.
- **Notes:** This is the only Category B store that is a *designed* exception to Intent #1. All other Category B stores are unintentional gaps.

---

#### B.17 — `packs/core/context/director-corrections.md`
- **Contains:** 18 lines / 750 bytes. A freeform markdown log of routing and priority overrides by the Director. Entries record session, DCL command, and correction rationale.
- **Writer:** `runtime/hooks/quality/on-agent-correction.py` — updates the file when a correction is detected; also written manually by the operator.
- **Readers:** `on-agent-correction.py` parses the file on each PostToolUse Edit/Write event; the Chief of Staff is instructed to load this every session.
- **Why file-based:** Designed as an operator-editable plaintext log. The `DREAM_STUDIO_CORRECTIONS_PATH` env var points here. The `cor_skill_corrections` SQLite table exists (schema: `id`, `telemetry_id`, `corrected_success`, `reason`, `corrected_at`) but is empty — no write path from corrections file to DB table is active.
- **SQLite equivalent:** `cor_skill_corrections` exists and is the obvious target. The dual-store gap is that corrections are written to file but never migrated to DB.
- **Migration documented:** No.
- **Size:** 750 bytes / 18 lines

---

#### B.18 — `packs/core/context/director-preferences.md`
- **Contains:** 49 lines / 2,963 bytes. Standing instructions for all agents — execution preferences, communication style, trust rules, project preferences.
- **Writer:** Operator-edited manually. No hook writes to this file automatically.
- **Readers:** Chief of Staff prompt instruction loads this file every session alongside `director-corrections.md`.
- **Why file-based:** Operator configuration document. Not event-driven — human-edited.
- **SQLite equivalent:** None. Would require a `ds_director_preferences` table with key-value or structured columns. Given the freeform nature, a `ds_documents` record (type=`director_preferences`) could hold it.
- **Migration documented:** No.
- **Size:** 2,963 bytes / 49 lines

---

#### B.19 — `~/.dream-studio/meta/` file outputs
This directory contains several persistent file stores that are not state-per-se but represent operational records that would ideally live in SQLite:

- **`pulse-YYYY-MM-DD.md` and `pulse-latest.json`** (3 pulse reports, last 2026-05-19 — 3 days silent): Written by `on-pulse.py` via `pulse_collector.py`. JSON snapshot of health state per day. SQLite equivalent: `raw_pulse_snapshots` table exists but is empty — the pulse writer is not using it.
- **`token-log.md`** (written by `on-token-log.py` on every Stop): Markdown token accounting log. No SQLite equivalent; `raw_token_usage` table has only 3 rows with all-zero values. Dual-track token logging with file as the only populated path.
- **`first-run.log`** (27,258 bytes, active as of 2026-05-22): Written by `on-first-run.py` via `hydrate_registry_once`. Logs registry hydration state. No SQLite equivalent; `reg_skills` and `reg_workflows` tables are empty despite hydration being recorded here.
- **`draft-lessons/`** (2 files): Draft lesson markdown files from `daily-close.yaml` workflow. No SQLite equivalent — `raw_lessons` table is empty.

---

### Category C: Hybrid Stores

These stores have both file and SQLite components, with the relationship ranging from intentional pipeline staging to unintentional dual-write.

---

#### C.1 — Spool Pipeline: `events/spool/` → `canonical_events`

**Architecture:** The spool pipeline is the primary write path for canonical events. Events are written as individual JSON files to `~/.dream-studio/events/spool/` by `emitters/claude_code/run.py`, then consumed by `spool/ingestor.py:ingest_pending()` which is called on every Stop hook. Processed events move to `events/processed/`.

**Current state:**
- `events/spool/`: 12 pending files (awaiting next Stop hook)
- `events/processing/`: 3 files currently being processed (from the current session)
- `events/processed/`: 1,593 files (successfully ingested)
- `events/failed/`: 0 files

**Transient or persistent?** The file storage is **intentionally transient** — a write-ahead buffer. The design is:
1. Hook processes write individual event JSON files synchronously (no SQLite contention risk)
2. The Stop hook runs the ingestor which reads all pending files, inserts to `canonical_events`, and moves files to `processed/`
3. `events/.sessions/{pid}.json` coordination files are permanent artifacts (1,102 files), not transient — they accumulate indefinitely

**Assessment:** The spool pattern is architecturally sound for its stated purpose. The file stage is transient by design. The gap is that `events/processed/` becomes an ever-growing archive (1,593 files) with no pruning mechanism, and `events/.sessions/` also accumulates indefinitely.

**Intent #1 alignment:** ALIGNED for the pipeline design. The file stage is the write buffer, SQLite is the authority. However, the indefinite growth of `processed/` creates an implicit second copy of the canonical record alongside the DB.

---

#### C.2 — Token Attribution: `diagnostics/token-capture.jsonl` ↔ `canonical_events`

**Architecture:** `core/telemetry/token_capture.py:handle_post_tool_use()` writes performance timing data to `diagnostics/token-capture.jsonl`. Separately, `emitters/claude_code/run.py` emits `hook.tool_activity` events to the spool which eventually reach `canonical_events`. The two paths carry different data: the diagnostics file has per-call timing; canonical_events has event metadata.

**Authoritative store for token data:** Neither is authoritative. The diagnostics file holds timing-only data (no token counts), while `canonical_events` holds event metadata (no timing). The `raw_token_usage` table has 3 rows with all-zero counts, and `token_usage_records` is empty. Token counts are not reliably stored anywhere.

**Assessment:** HYBRID but not overlapping. The `token-capture.jsonl` and `canonical_events` hold complementary, not redundant, data. The real gap is that the intended token count data lands in neither store reliably.

---

#### C.3 — Dual SQLite: `reg_projects` ↔ `ds_projects`

**Architecture:** Two separate SQLite tables serve similar purposes:
- `reg_projects` (2 rows): `project_id` is a directory name (e.g., `dream-studio-clean`), `project_path` is the filesystem path. Written by `on-session-start.py` — uses `Path.cwd().name` as the project identifier. 20 columns, most null.
- `ds_projects` (25 rows): `project_id` is a UUID (e.g., `29ff0914-b15a-4a84-8bc7-5619cc5240f6`), `name` is human-readable. Written by `ds project register` / CLI commands. 6 columns.

**Authoritative store:** `ds_projects` is the SDLC authority (Intent #5 context: marker files resolve to `ds_projects` UUIDs). `reg_projects` is the analytics registry (session-to-path mapping). They use incompatible identity schemes (directory name vs UUID) and do not cross-reference each other.

**Assessment:** Not a true dual-store — they are distinct registries for different consumers. The confusion is that both are called "projects." The identity mismatch (directory name vs UUID) means they cannot be easily merged without a join table.

---

#### C.4 — Dual Workflow Tables: `raw_workflow_runs` ↔ `workflow_invocations`

**Architecture:** Both tables have 2 rows representing the same 2 `studio-onboard` workflow runs.
- `raw_workflow_runs` (12 columns): includes `run_key`, `workflow`, `yaml_path`, `status`, `started_at`, `finished_at`, `node_count`, `nodes_done`, `activity_id`, `prd_id`, `task_id`. Written by `_try_archive_and_prune` in `workflow/state.py`.
- `workflow_invocations` (11 columns): includes `invocation_id`, `project_id`, `milestone_id`, `task_id`, `process_run_id`, `event_id`, `workflow_id`, `status`, `purpose`, `metadata_json`. Written separately.

**Authoritative store:** Neither is clearly designated. `raw_workflow_runs` is more operationally complete (has node counts, start/end times). `workflow_invocations` has better SDLC linkage (project_id, milestone_id, event_id). The execution graph tables (`execution_nodes`, `execution_outputs`) are empty and disconnected from both.

**Assessment:** Unintentional dual-store. The `raw_*` tables appear to be v1 persistence that was not replaced when `workflow_invocations` was introduced.

---

#### C.5 — Skill Telemetry Triple-Store: `skill-usage.jsonl` + `telemetry-buffer.jsonl` + `raw_skill_telemetry`

**Architecture:**
- `skill-usage.jsonl`: Written by `on-skill-metrics` hook at skill invocation time; read by `on-skill-telemetry` and analytics harvester.
- `telemetry-buffer.jsonl`: Written by `on-skill-telemetry` hook at Stop time; designed to be consumed by `pulse_collector.py`.
- `raw_skill_telemetry`: Empty SQLite table — the intended destination after `pulse_collector` batch-import.

**Pipeline intent:** `skill-usage.jsonl` → (session boundary) → `on-skill-telemetry reads skill-usage` → `telemetry-buffer.jsonl` → (pulse collection) → `raw_skill_telemetry`. The pipeline is broken at the `pulse_collector` stage: `raw_skill_telemetry` has never received data.

**Authoritative store:** None is currently authoritative. `skill-usage.jsonl` is the only populated source with recent data, but carries `unknown` values for all 3 records.

**Assessment:** Three-layer pipeline with the last layer never populated. A triple-store with no single authority.

---

#### C.6 — `.sessions/` File Store ↔ `raw_handoffs` / `ds_documents`

**Architecture:**
- `.sessions/` markdown files: Written at Stop time by `on-stop-handoff.py`. 58 files (29 handoff + 29 recap pairs). Some large (~35 KB), some stub (~334 bytes).
- `raw_handoffs` (26 rows): Handoff records from `on-stop-handoff.py`.
- `ds_documents` (12 rows, type=session_handoff): Ingested via `ds memory ingest`.

**Pipeline intent:** `.sessions/` files are written first; `ds memory ingest` reads them and ingests into `raw_handoffs` / `ds_documents`. The file is the source; SQLite is the processed store.

**Authoritative store:** The `.sessions/` files are more complete (58 files > 26 raw_handoffs rows). Not all sessions have been ingested. The files are the current authority by data coverage.

**Assessment:** Intentional staging pipeline, but the ingest step is manual and has fallen behind. 58 files in `.sessions/` vs 26 rows in `raw_handoffs` means roughly 32 sessions' data has not been ingested.

---

## Storage Architecture Summary Table

| Store | Type | Intent #1 | Domain | Migration Effort | Replaceable By |
|-------|------|-----------|--------|-----------------|----------------|
| `studio.db` | SQLite | ALIGNED | all | N/A | N/A |
| `workflows.json` | File | VIOLATES | workflow | MEDIUM | `workflow_invocations` + in-flight state extension |
| `workflow-checkpoint.json` | File | VIOLATES | workflow | SMALL | `automation_checkpoints` table |
| `active_task.json` | File | VIOLATES | sdlc | SMALL | `ds_tasks` flag column or pointer table |
| `activity.json` | File | VIOLATES | telemetry | MEDIUM | Materialized view over `hook_invocations` |
| `pending-handoff.json` | File | VIOLATES | handoff | SMALL | `ds_handoff_requests` table (new) |
| `platform.json` | File | VIOLATES | config | SMALL | `ds_machine_profile` table (new) |
| `installed-version` | File | PARTIAL | install | SMALL | `ds_installation_records` table (low priority) |
| `machine_id` | File | VIOLATES | telemetry | SMALL | `ds_machine_profile` table (alongside platform.json) |
| `hook-timing.jsonl` | File | VIOLATES | telemetry | LARGE | `hook_timing_records` table (new; high write volume) |
| `skill-usage.jsonl` | File | VIOLATES | telemetry | MEDIUM | `raw_skill_telemetry` (schema exists; flush broken) |
| `telemetry-buffer.jsonl` | File | TRANSITIONAL | telemetry | SMALL (fix flush) | `raw_skill_telemetry` via pulse_collector |
| `token-capture.jsonl` | File | VIOLATES | telemetry | MEDIUM | `diagnostic_records` table (new) |
| `.sessions/` files | File | PARTIAL | handoff | LARGE | `raw_handoffs` + `ds_documents` (ingest is manual) |
| `integrations/manifest.json` | File | PARTIAL | install | SMALL | `ds_installation_records` table |
| `events/spool/` files | File | TRANSITIONAL | telemetry | N/A (intentional buffer) | `canonical_events` (already the target) |
| `events/.sessions/{pid}.json` | File | PARTIAL | telemetry | SMALL | Process coordination — `raw_sessions` pid field |
| `.dream-studio-project` markers | File | INTENTIONAL | identity | N/A | N/A (Intent #5 designates as authority) |
| `director-corrections.md` | File | VIOLATES | learning | SMALL | `cor_skill_corrections` (schema exists; wire flush) |
| `director-preferences.md` | File | VIOLATES | config | SMALL | `ds_documents` (type=director_preferences) |
| `milestone-active.txt` | File | NOT FOUND | sdlc | N/A | (Does not exist at audit time) |
| `pulse-*.md` / `pulse-latest.json` | File | VIOLATES | telemetry | SMALL | `raw_pulse_snapshots` (schema exists; write broken) |
| `token-log.md` | File | VIOLATES | telemetry | MEDIUM | `raw_token_usage` (schema exists; write broken) |
| `first-run.log` | File | VIOLATES | registry | SMALL | `reg_skills` / `reg_workflows` (schema exists; hydration not persisting) |
| `draft-lessons/` files | File | VIOLATES | learning | SMALL | `raw_lessons` (schema exists; pipeline not activated) |
| `reg_projects` | SQLite | ALIGNED | analytics | N/A (exists in DB but identity mismatch vs ds_projects) | — |
| `raw_workflow_runs` + `workflow_invocations` | SQLite dual | ALIGNED | workflow | MEDIUM | Consolidate into single canonical table |

---

## Migration Effort Estimates

### SMALL (single table, clear writer, low call volume — estimated 1–2 days each)
- `workflow-checkpoint.json` → `automation_checkpoints`
- `active_task.json` → `ds_tasks` pointer column
- `pending-handoff.json` → new `ds_handoff_requests` table
- `platform.json` + `machine_id` → new `ds_machine_profile` table (combine both)
- `director-corrections.md` → wire `on-agent-correction.py` to write `cor_skill_corrections` directly (schema exists)
- `director-preferences.md` → `ds_documents` record (low urgency; human-edited)
- `telemetry-buffer.jsonl` → fix `pulse_collector.py` flush to write `raw_skill_telemetry`
- `raw_pulse_snapshots` write path → fix `on-pulse.py` to insert to table (schema exists)
- `first-run.log` → wire `hydrate_registry_once` to persist to `reg_skills` + `reg_workflows`
- `integrations/manifest.json` → add `ds_installation_records` table; write at install time
- `installed-version` → add to `ds_installation_records` (low priority)

### MEDIUM (multiple writers/readers, schema change needed, moderate impact — estimated 3–5 days each)
- `workflows.json` → extend `workflow_invocations` to carry in-flight node state; `cmd_status` / `cmd_list` read from DB
- `activity.json` → materialized window view over `hook_invocations`; dashboard API reads DB instead of file
- `skill-usage.jsonl` → consolidate with `raw_skill_telemetry` write path; fix skill name resolution (currently `unknown`)
- `token-capture.jsonl` → new `diagnostic_records` table; `ds diagnostics list/clear` commands read/truncate DB rows
- `token-log.md` → fix `on-token-log.py` to write `raw_token_usage`; retire file-based log

### LARGE (high write volume, many consumers, architectural impact — estimated 1–2 weeks each)
- `hook-timing.jsonl` → new `hook_timing_records` table; 3,645 lines in 5 days = ~730 inserts/day. Requires WAL-mode write performance testing. Analytics harvester needs query rewrite.
- `.sessions/` files → automate `ds memory ingest` at Stop time (currently manual); full SQLite handoff storage requires schema changes to `raw_handoffs` to support full markdown content.

---

## Findings

### F1: 24 runtime state stores violate Intent #1
Of the non-marker-file, non-spool-buffer stores identified, 24 distinct file-based runtime state stores have no corresponding authoritative SQLite record. This is not marginal tech debt — it is structural divergence between the stated architecture and the implemented one.

### F2: The spool pipeline is the only correctly implemented hybrid pattern
The `events/spool/` → `canonical_events` pipeline is the only hybrid store where the file stage is provably transient and SQLite is demonstrably authoritative. All other hybrid stores have either broken flush pipelines or no flush at all.

### F3: 10 schemas exist but write paths are broken or inactive
The following SQLite tables have schemas but no active write path: `raw_skill_telemetry`, `raw_pulse_snapshots`, `raw_token_usage`, `cor_skill_corrections`, `token_usage_records`, `raw_lessons`, `reg_skills`, `reg_workflows`, `automation_checkpoints`, `hook_executions` (partial — on_pulse only). In every case, the corresponding file-based store is the only active record.

### F4: hook-timing.jsonl is the single largest compliance gap by data volume
At 392 KB and 3,645 lines (still actively growing as of audit date), `hook-timing.jsonl` represents the largest accumulation of runtime state outside SQLite. The analytics pipeline depends directly on this file. Migration is LARGE due to write frequency.

### F5: Three-way skill telemetry split has no authoritative store
`skill-usage.jsonl`, `telemetry-buffer.jsonl`, and `raw_skill_telemetry` form a broken triple-store pipeline. None is authoritative. The data quality is also degraded — all 3 records in `skill-usage.jsonl` have `skill=unknown`, meaning even if the pipeline were fixed, the data would be unreliable.

### F6: The .sessions/ ingest gap is growing
58 session files vs 26 `raw_handoffs` rows means 32 sessions' data (roughly 55%) has not been ingested into SQLite. The ingest is manual; it is falling behind session creation rate.

### F7: platform.json is re-created on every new machine_id write
`platform.json` is written by `get_platform_profile()` on first access if not present. The `machine_id` file is written by `get_machine_id()` on first access. Both could share a single `ds_machine_profile` table write at the same initialization point.

### F8: pending-handoff.json has no TTL enforcement
The current `pending-handoff.json` is stale (`triggered_at` = 2026-05-21 ~8:44 PM, audit time = 2026-05-22 ~1:53 PM — ~17 hours old). The `in_progress` status was written by `on-prompt-validate.py` and never cleared. There is no expiry check in either reader. A SQLite-backed `ds_handoff_requests` table would naturally support TTL queries (`WHERE triggered_at > now() - 300`).

---

## Intent Divergence

**Intent #1 (SQLite-first authority) is structurally non-compliant.** The evidence:

- **182 tables in schema; 141 are empty.** The schema describes an intent-aligned architecture that is not yet implemented.
- **24 file-based runtime state stores** exist alongside 41 populated SQLite tables. File-based stores represent approximately 37% of active state persistence points.
- **The most frequently accessed stores are the most file-dependent:** hook-timing.jsonl (3,645 lines, every tool invocation), activity.json (every tool invocation), pending-handoff.json (cross-session coordination).
- **9 of 13 file-path env vars configure file-based state stores with no SQLite equivalent** (from the 1i config audit).

The architecture has been moving toward SQLite-first since at least Slice 5 (the SDLC tables are well-populated and correctly used). The telemetry and operational layers have not followed.

---

## Open Questions

1. **workflows.json live state vs SQLite:** Is there a performance or correctness reason why in-flight workflow state must be file-based rather than in `workflow_invocations`? The spool pattern demonstrates that SQLite with WAL mode can handle concurrent hook writes.

2. **hook-timing.jsonl replacement feasibility:** The analytics harvester reads the entire file on each invocation to compute per-handler averages. A SQLite query (`SELECT handler, AVG(duration_ms) FROM hook_timing_records GROUP BY handler`) would be faster and more composable. Is there a specific reason the current harvester reads the whole file?

3. **events/processed/ pruning:** 1,593 processed spool files accumulate indefinitely. Is there a pruning policy? Should processed files be deleted after the ingestor confirms SQLite insertion?

4. **events/.sessions/{pid}.json accumulation:** 1,102 session coordination files exist with no pruning. These are process bootstrap artifacts. Can they be deleted after the session ends?

5. **reg_projects identity mismatch:** `reg_projects.project_id` uses directory names; `ds_projects.project_id` uses UUIDs. `on-session-start.py` uses `Path.cwd().name` which creates `reg_projects` rows that cannot be linked to `ds_projects` rows. Is this intentional separation or a design gap?

6. **Skill telemetry `unknown` values:** All 3 records in `skill-usage.jsonl` and the single `telemetry-buffer.jsonl` record have `skill=unknown`. Is the skill name resolution broken at the hook level, or does the write happen before the skill context is established?

7. **raw_pulse_snapshots vs pulse-*.md:** The pulse hook writes detailed markdown reports to `meta/` but `raw_pulse_snapshots` is empty. What would the SQLite schema need to hold the structured health data from the pulse reports?

8. **director-corrections.md vs cor_skill_corrections:** The `cor_skill_corrections` table was created in a migration. Was the intent always to have both (file for human editing, DB for programmatic access), or should the file be retired once the DB write path is active?
