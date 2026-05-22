# Dream Studio — Full Stock Audit
## Phase 0b: Mechanical Inventory — Depth Pass
**Date:** 2026-05-22
**Scope:** `C:\Users\Dannis Seay\builds\dream-studio-clean` (source)
**Runtime:** `C:\Users\Dannis Seay\.dream-studio\` (operator-local)
**Installed config:** `C:\Users\Dannis Seay\.claude\`
**Companion file:** `00-mechanical-inventory.md` (breadth pass — do not repeat here)

---

## CATEGORY 1: Skills — Depth

### Installed vs Canonical Byte Counts

| Pack | Canonical bytes | Installed bytes | Delta |
|------|----------------|-----------------|-------|
| ds-analyze | 1,227 | 1,251 | +24 |
| ds-bootstrap | 1,842 | 1,896 | +54 |
| ds-core | 3,819 | 3,893 | +74 |
| ds-domains | 1,914 | 1,945 | +31 |
| ds-project | 19,063 | 19,287 | +224 |
| ds-quality | 1,227 | 1,249 | +22 |
| ds-security | 1,423 | 1,446 | +23 |
| ds-setup | 8,028 | 8,203 | +175 |
| ds-workflow | 3,488 | 3,572 | +84 |

All 9 installed skills differ from their canonical source. All installed versions are larger than canonical. ds-project has the largest absolute delta (+224 chars). No installed skill is smaller than its canonical counterpart.

ds-milestone and ds-workorder are canonical skills that are NOT installed as standalone `.md` files in `~/.claude/skills/`. They are function-backed skills.

### Mode Inventory Per Skill

**ds-analyze (canonical):** multi, domain-re, repo, intelligence

**ds-core (canonical):** think, plan, build, review, verify, ship, handoff, recap, explain

**ds-domains (canonical):** game-dev, saas-build, mcp-build, dashboard-dev, client-work, design, website, fullstack

**ds-bootstrap (canonical):** No user-invocable modes. Passive context injection only. Not routed by pack keyword table.

**ds-project (canonical):** scope, resume, brief, manage
- resume mode: full 5-phase navigator. Phase 1 = state query. Phase 2 = project briefing. Phase 3 = work order identification. Phase 4 = execution context. Phase 5 = handoff check.
- scope mode: full 5-phase scoping protocol. Phase 1 = intake. Phase 2 = decomposition. Phase 3 = milestone planning. Phase 4 = work order generation. Phase 5 = PRD creation.

**ds-quality (canonical):** debug, polish, harden, secure, structure-audit, learn, coach
- NOTE: canonical SKILL.md references `modes/secure/SKILL.md` but installed pack uses mode name `pr-security-scan`. Discrepancy between canonical and installed naming.

**ds-security (canonical):** scan, review, dast, binary-scan, mitigate, comply, netcompat, dashboard

**ds-setup (canonical):** wizard, status, jit
- wizard mode: 6-step setup flow. Step 1 = detect. Step 2 = configure. Step 3 = install hooks. Step 4 = install skills. Step 5 = initialize DB. Step 6 = verify.
- status mode: health check against 7 capability areas.
- jit mode: just-in-time installer triggered on first invocation.

**ds-workflow (canonical):** No discrete modes listed. Invocation by workflow name from canonical/workflows/. Validator/runner contract defined in SKILL.md.

**ds-milestone (canonical):** status, close. Function-backed: wraps `core.milestones.*`.

**ds-workorder (canonical):** start, execute, close, block, status. Function-backed: wraps `core.work_orders.*`.

### Canonical Skill File Sizes

| Skill | SKILL.md bytes |
|-------|----------------|
| analyze | 1,227 |
| core | 3,819 |
| domains | 1,914 |
| ds-bootstrap | 1,842 |
| ds-milestone | 1,881 |
| ds-project | 19,063 |
| ds-workorder | 2,264 |
| quality | 1,227 |
| security | 1,423 |
| setup | 8,028 |
| workflow | 3,488 |

### Mode File Locations

Canonical skills with discoverable modes/ subdirectories reside under `canonical/skills/<pack>/modes/<mode>/SKILL.md`. The ds-project skill has the most documented content (19,063 chars).

---

## CATEGORY 2: Agents — Depth

### All Canonical Agents

Location: `canonical/agents/`

| File | Bytes | Domain |
|------|-------|--------|
| accessibility-expert.md | 4,900 | WCAG 2.2 audit |
| data-engineer.md | 9,189 | dbt, BigQuery, Snowflake, Airflow/Dagster |
| devops-engineer.md | 5,660 | GitHub Actions, OIDC, Docker |
| idea-validator.md | 7,253 | Stress-testing / fatal flaw hunting |
| kubernetes-expert.md | 5,644 | Production k8s ops |
| mobile-developer.md | 9,792 | iOS, Android, RN, Flutter |
| README.md | 2,318 | Agent system documentation |
| research-analyst.md | 5,457 | Source hierarchy, triangulation methodology |
| technical-writer.md | 5,725 | Diataxis framework |
| terraform-architect.md | 6,744 | Terraform module design |

Total canonical agents: 9 (excluding README.md).

### Agent Dispatch Modes

**Mode A (knowledge injection):** Agent content injected into skill context. No separate invocation. Used when a skill detects it needs domain-specific framing.

**Mode B (specialist dispatch):** Agent invoked as a separate subagent with its own context window. Used by ds-domains and ds-analyze for long-running specialist work.

### Agent Synthesis Origin

README.md states agents were synthesized by the domain-ingest workflow (`canonical/workflows/domain-ingest.yaml`). Agents are not hand-authored persona files — they are workflow outputs.

### Agents Registered in Packs Directory

`packs/core/agents/`: chief-of-staff.md (29 bytes), director.md (58 bytes), engineering.md (13 bytes), README.md (79 bytes)
`packs/domains/agents/`: client.md (96 bytes), game.md (32 bytes)

These are stub agent context files used for pack-level agent injection. Not the same as canonical specialists.

---

## CATEGORY 3: Hooks — Depth

### Hook File Inventory

All hook Python files are in `runtime/hooks/`. All installed hook dispatch lives in `C:\Users\Dannis Seay\.claude\hooks\`.

**Meta hooks (runtime/hooks/meta/):**

| File | Trigger | Size | Key dependency |
|------|---------|------|----------------|
| on-context-threshold.py | PostToolUse (dispatched) | — | Spawns fresh session at 75% context |
| on-edit-dispatch.py | PostToolUse Edit/Write | — | Calls 4 sub-handlers sequentially |
| on-first-run.py | UserPromptSubmit (dispatched) | — | hydrate_registry_once() |
| on-memory-retrieve.py | UserPromptSubmit (dispatched) | — | control.research.memory.MemorySearch, top_k=5 |
| on-meta-review.py | PostToolUse (dispatched) | — | Weekly retrospective |
| on-post-compact.py | PostCompact | — | Resets context tracking |
| on-prompt-dispatch.py | UserPromptSubmit | — | Calls 7 handlers in order |
| on-prompt-validate.py | UserPromptSubmit (dispatched) | — | rebuff_validator, pending-handoff.json check |
| on-pulse.py | UserPromptSubmit (dispatched) | — | pulse_collector.run_pulse_check(), insert_hook_execution |
| on-session-end.py | Stop (dispatched) | — | Closes session row |
| on-session-start.py | UserPromptSubmit (dispatched) | — | Records new session row |
| on-skill-complete.py | PostToolUse Skill (dispatched) | — | control.skills.calibration.record_outcome |
| on-skill-load.py | PostToolUse Read (dispatched) | — | Logs skill reads, resolves director_name |
| on-skill-metrics.py | PostToolUse Skill (dispatched) | — | insert_token_usage |
| on-skill-telemetry.py | Stop (dispatched) | — | Captures skill telemetry at session end |
| on-stop-dispatch.py | Stop | — | Calls 6 handlers in order |
| on-token-log.py | Stop (dispatched) | — | Appends token usage to token log |
| on-tool-activity.py | PostToolUse | — | Maintains activity.json feed |

**Core hooks (runtime/hooks/core/):**

| File | Trigger | Key behavior |
|------|---------|------|
| on-changelog-nudge.py | Stop | Nudges if source files changed but CHANGELOG.md not updated |
| on-milestone-end.py | Stop | Emits checkpoint if milestone marker exists |
| on-milestone-start.py | UserPromptSubmit | Writes marker when DCL command detected |
| on-post-tool-use.py | PostToolUse | Token attribution capture via core.telemetry.token_capture |
| on-stop-handoff.py | Stop | Writes handoff+recap if git activity detected. Time budget: <2 seconds |
| on-workflow-progress.py | Stop | Read-only workflow status reporter |

**Quality hooks (runtime/hooks/quality/):**

| File | Trigger | Key behavior |
|------|---------|------|
| on-agent-correction.py | PostToolUse Edit/Write | Parses director-corrections.md updates |
| on-quality-score.py | Stop | Advisory quality scoring after milestone |
| on-security-scan.py | PostToolUse Edit/Write | Lightweight security pattern check. Advisory only |
| on-structure-check.py | PostToolUse Write | Nudges on FSC convention violations |

**Domain hooks (runtime/hooks/domains/):**

| File | Trigger | Key behavior |
|------|---------|------|
| on-game-validate.py | PostToolUse Edit/Write | Active only when domains pack is active |

### Hook Dispatch Chain Detail

**UserPromptSubmit path:** run.py → on-prompt-dispatch.py → [on-prompt-validate, on-session-start, on-first-run, on-memory-retrieve, on-milestone-start, on-context-threshold, on-pulse]

**Stop path:** run.py (calls spool.ingestor.ingest_pending() + session cleanup) → on-stop-dispatch.py → [on-session-end, on-stop-handoff, on-quality-score, on-skill-telemetry, on-milestone-end, on-token-log]

**PostCompact path:** run.py → on-post-compact.py (direct, no sub-dispatch)

**PostToolUse path:** run.py → hooks.py → on-tool-activity [always] → then:
- If tool == Skill: on-skill-metrics, on-skill-complete
- If tool in (Edit, Write, MultiEdit): on-edit-dispatch → [on-agent-correction, on-game-validate, on-security-scan, on-structure-check]
- If tool == Read: on-skill-load

### Installed Hook Infrastructure

`C:\Users\Dannis Seay\.claude\hooks\dispatch\hooks.py` — routing logic (resolves which handlers to call per event+tool)
`C:\Users\Dannis Seay\.claude\hooks\run.py` — spool emitter entry point. PACKS constant = ("core", "quality", "career", "analyze", "domains", "meta", "security")

`hooks/` in repo root (source hooks, separate from runtime hooks):
- hooks/git/pre-push — git pre-push hook script (717 bytes)
- hooks/hooks.json (4,420 bytes) — hook definitions for source repo
- hooks/on-commit.py (2,977 bytes) — commit-time hook logic
- hooks/run.cmd (2,834 bytes) — Windows hook runner
- hooks/run.sh (2,100 bytes) — Unix hook runner

---

## CATEGORY 4: CLI — Depth

### Primary Entrypoint

**File:** `interfaces/cli/ds.py`
**Size:** 90,234 bytes
**Entrypoint:** `main()` function registered as `ds` in `pyproject.toml` under `[project.scripts]`
**Invocation:** `py -m interfaces.cli.ds <command>` or (if installed) `ds <command>`

### CLI Subcommand Modules

Located at `interfaces/cli/`:

| Module | Size | Purpose |
|--------|------|---------|
| ds.py | 90,234 | Primary CLI entrypoint, argparse-based |
| ds_work_order.py | 31,259 | Work order CRUD and lifecycle |
| ds_memory.py | 21,606 | Memory ingestion and retrieval |
| ds_analytics/harvester.py | 14,743 | Analytics data harvesting |
| resume_from_handoff.py | 14,727 | Handoff resume logic |
| runtime_recovery.py | 20,314 | Runtime recovery procedures |
| runtime_preflight.py | 19,498 | Pre-flight checks |
| hydrate_registry.py | 24,327 | Registry hydration |
| migrate_to_option_c.py | 16,296 | DB migration tooling |
| efficiency_analytics.py | 16,491 | Efficiency analytics |
| pulse_collector.py | 19,339 | Pulse health check collector |
| setup.py | 19,890 | Setup command implementation |
| session_analytics.py | 13,076 | Session analytics |
| memory_audit.py | 18,356 | Memory audit tooling |
| ds_workflow.py | 5,391 | Workflow execution CLI |
| ds_entry.py | 1,116 | Global entry helper |
| ds_dashboard.py | 9,408 | Dashboard server launcher |
| ds_spool.py | 1,030 | Spool management CLI |
| dream_exec.py | 11,614 | Dream execution runner |
| studio_backup.py | 15,397 | Backup tooling |

### Auxiliary CLI Scripts (interfaces/cli/, not subcommands)

| Script | Size | Purpose |
|--------|------|---------|
| check_migrations.py | 1,805 | Migration completeness check |
| check_repo_updates.py | 8,698 | Repo update checker |
| ci_gate.py | 3,728 | CI gate runner |
| contract_atlas_lifecycle_gate.py | 5,031 | Contract atlas lifecycle gate |
| contract_docs_drift_gate.py | 3,697 | Contract docs drift gate |
| generate_routing.py | 8,547 | Auto-generate routing table |
| hydrate_registry.py | 24,327 | Registry hydration |
| lint_skills.py | 10,909 | Skill linter |
| repo_publication_readiness.py | 2,049 | Repo publication readiness check |
| runtime_preflight.py | 19,498 | Runtime preflight |
| runtime_recovery.py | 20,314 | Recovery procedures |
| seed_tool_registry.py | 6,191 | Tool registry seeder |
| spec_risk_check.py | 11,159 | Spec risk checker |
| validate_client_profile.py | 11,353 | Client profile validator |

### pyproject.toml Registered Entry Points

- `ds` → `interfaces.cli.ds:main`

### Global Entry Shorthand

`C:\Users\Dannis Seay\.claude\bin\ds.cmd` — wrapper that calls `py -m interfaces.cli.ds` from `dream-studio-clean`. Required to be on PATH for global `ds` invocation.

---

## CATEGORY 5: Database Schema — Depth

### Database File

- **Path:** `C:\Users\Dannis Seay\.dream-studio\state\studio.db`
- **Size:** 6,500,352 bytes (6.5 MB)
- **Backup:** studio.db.bak (5,300,224 bytes), studio.db.pre-ta0c-backup (6,295,552 bytes)
- **Schema migrations applied:** 61 (versions 1 through 64 — gaps at 035, 036; numbers are not strictly sequential)
- **First migration applied:** 2026-05-16T21:01:02
- **Last migration applied:** 2026-05-22T02:29:03

### Tables with Row Counts (non-zero only)

| Table | Row Count |
|-------|-----------|
| _schema_version | 61 |
| canonical_events | 1,835 |
| ds_design_briefs | 1 |
| ds_documents | 12 |
| ds_documents_fts | 12 |
| ds_documents_fts_config | 1 |
| ds_documents_fts_data | 27 |
| ds_documents_fts_docsize | 12 |
| ds_documents_fts_idx | 25 |
| ds_milestones | 4 |
| ds_projects | 25 |
| ds_tasks | 9 |
| ds_technology_signals | 54 |
| ds_work_order_types | 10 |
| ds_work_orders | 14 |
| execution_events | 929 |
| fts_gotchas | 1,488 |
| fts_gotchas_config | 1 |
| fts_gotchas_data | 74 |
| fts_gotchas_docsize | 1,488 |
| fts_gotchas_idx | 72 |
| hook_executions | 45 |
| hook_invocations | 917 |
| memory_fts_config | 1 |
| memory_fts_data | 2 |
| outcome_records | 2 |
| raw_handoffs | 26 |
| raw_operational_snapshots | 5 |
| raw_sentinels | 113 |
| raw_sessions | 51 |
| raw_token_usage | 3 |
| raw_workflow_nodes | 25 |
| raw_workflow_runs | 2 |
| reg_gotchas | 1,488 |
| reg_projects | 2 |
| research_evidence_records | 9 |
| skill_invocations | 1 |
| sqlite_sequence | 14 |
| tool_invocations | 917 |
| validation_failures | 57 |
| workflow_invocations | 2 |

### Key Table Schemas

**ds_projects columns:** project_id, name, status, created_at, updated_at
- 25 rows total. 1 active project (29ff0914 "Dream Studio"), 1 paused real project (a4befdce "Dream Command"). Remaining 23 rows are test fixtures with names "My Project", "Programmatic Project", "API Project".

**ds_work_orders columns:** work_order_id, project_id, milestone_id, title, description, status, created_at, updated_at, work_order_type, block_reason
- 14 rows. All for Dream Command project. 2 complete, 1 in_progress, 11 open.

**ds_milestones columns:** milestone_id, project_id, title, description, due_date, status, created_at, updated_at, order_index
- 4 rows. All for Dream Command. All status=pending.
- Titles: "Shell + Intelligence Foundation", "Command Routing + Execution", "Multi-Step Workflow Orchestration", "Packaging and Distribution"

**ds_tasks columns:** task_id, work_order_id, project_id, title, description, status, created_at, updated_at
- 9 rows.

**ds_work_order_types columns:** type_id, label, pre_build_gate, build_executor, post_build_gate, workflow_template, precondition_skill, task_generator, resolution_instructions

**ds_design_briefs:** 1 row. For Dream Command (a4befdce). status=locked. design_system=tech-minimal.

**canonical_events columns:** event_id, event_type, timestamp, trace (JSON), severity, payload (JSON), actor (JSON), confidence_score, source_type, raw_prompt_retained, raw_tool_output_retained, schema_version, created_at, invocation_mode

**raw_workflow_runs columns:** id, run_key, workflow, yaml_path, status, started_at, finished_at, node_count, nodes_done, activity_id, prd_id, task_id
- 2 rows. Both are "studio-onboard" workflow runs. Run 1: status=aborted (11/12 nodes done). Run 2: status=completed (13/13 nodes done).

**raw_workflow_nodes columns:** id, run_key, node_id, status, started_at, finished_at, duration_s, output, activity_id
- 25 rows. From the two studio-onboard runs.

### Work Order Types (all 10)

| type_id | label | pre_build_gate | build_executor | post_build_gate | workflow_template |
|---------|-------|----------------|----------------|-----------------|-------------------|
| ui_component | UI Component | design_brief_locked | fullstack:frontend | design_critique\|anti_slop_passed | ui-feature |
| ui_page | UI Page | design_brief_locked | website:page | design_critique\|anti_slop_passed | ui-feature |
| api_endpoint | API Endpoint | api_contract_exists | fullstack:backend | security_scan | idea-to-pr |
| authentication | Authentication | api_contract_and_security_review | fullstack:backend | security_scan | idea-to-pr |
| saas_feature | SaaS Feature | api_contract_exists | saas-build | security_scan | idea-to-pr |
| data_pipeline | Data Pipeline | (none) | fullstack:backend | security_scan | idea-to-pr |
| game_mechanic | Game Mechanic | spec_approved | game-dev | game_validate | game-feature |
| deployment | Deployment | all_tests_pass | devops-engineer | security_scan | (none) |
| infrastructure | Infrastructure | (none) | devops-engineer | security_scan | idea-to-pr |
| documentation | Documentation | (none) | core:build | (none) | (none) |

---

## CATEGORY 6: Migration Depth

### Migration File Inventory

All migrations in `core/event_store/migrations/`. 64 numbered files (gaps at 011, 035, 036 — numbers 011, 035, 036 do not exist as files).

### Migration File Sizes (bytes) — Full List

| File | Bytes |
|------|-------|
| 001_initial.sql | 3,330 |
| 002_approaches.sql | 932 |
| 003_registry.sql | 1,144 |
| 004_operations.sql | 8,015 |
| 005_automation_tables.sql | 1,344 |
| 006_alerts.sql | 1,467 |
| 007_document_system.sql | 7,469 |
| 008_research_and_waves.sql | 5,906 |
| 009_project_intelligence.sql | 9,032 |
| 010_workflow_learning.sql | 733 |
| 012_prd_schema.sql | 6,969 |
| 013_discovery_tables.sql | 2,401 |
| 014_graph_views.sql | 1,627 |
| 015_performance_indexes.sql | 1,201 |
| 016_tool_embeddings.sql | 1,302 |
| 017_activity_log.sql | 2,949 |
| 018_hook_tracking.sql | 4,276 |
| 019_update_project_paths.sql | 961 |
| 020_security_findings.sql | 7,495 |
| 021_risk_register.sql | 5,232 |
| 022_workflow_connections.sql | 4,076 |
| 023_research_connections.sql | 5,143 |
| 024_learning_connections.sql | 3,271 |
| 025_audit_tracking.sql | 3,331 |
| 026_consolidate_databases.sql | 5,106 |
| 027_guardrail_metadata.sql | 1,468 |
| 028_create_automation_checkpoints.sql | 1,067 |
| 029_analytics_views.sql | 3,641 |
| 030_adapter_metadata.sql | 1,972 |
| 031_decision_log.sql | 1,442 |
| 032_semantic_memory.sql | 1,130 |
| 033_memory_fts.sql | 341 |
| 034_execution_graph.sql | 7,269 |
| 037_execution_telemetry_traceability_spine.sql | 14,531 |
| 038_shared_intelligence_authority.sql | 9,262 |
| 039_dashboard_authority_reconciliation.sql | 5,515 |
| 040_production_readiness_authority.sql | 6,973 |
| 041_legacy_canonical_event_import_map.sql | 1,719 |
| 042_token_usage_source_refs.sql | 1,000 |
| 043_ai_usage_accounting.sql | 6,476 |
| 044_career_capability_agent_github_authority.sql | 19,872 |
| 045_task_attribution_authority.sql | 3,638 |
| 046_platform_hardening_authority.sql | 6,120 |
| 047_prd_lifecycle_authority.sql | 12,981 |
| 048_project_spine.sql | 2,941 |
| 049_work_order_type.sql | 1,636 |
| 050_documents_source_path.sql | 405 |
| 051_work_order_block.sql | 611 |
| 052_invocation_mode.sql | 501 |
| 053_design_brief.sql | 870 |
| 054_ui_gate_update.sql | 314 |
| 055_technology_signals.sql | 445 |
| 056_milestone_order_index.sql | 530 |
| 057_work_order_type_extensions.sql | 1,231 |
| 058_ta0b_domain_field_validation.sql | 725 |
| 059_ta0b_execution_events_projection_link.sql | 559 |
| 060_ta0b_backfill_execution_events_from_canonical.sql | 4,140 |
| 061_backfill_sdlc_creation_events.sql | 2,627 |
| 062_nullify_activity_id_backfill_and_replace_views.sql | 20,625 |
| 063_drop_activity_log.sql | 661 |
| 064_backfill_task_creation_events.sql | 1,451 |

**Largest migration by bytes:** 044_career_capability_agent_github_authority.sql (19,872 bytes)
**Largest by scope:** 062_nullify_activity_id_backfill_and_replace_views.sql (20,625 bytes)
**Smallest:** 033_memory_fts.sql (341 bytes)
**Gap in numbering:** 011, 035, 036 do not exist as files.

### Migration Runner

`core/event_store/event_store.py` — contains migration runner logic. Reads files from `migrations/` directory, tracks applied versions in `_schema_version` table.

`interfaces/cli/check_migrations.py` (1,805 bytes) — CLI tool to verify migration completeness.
`interfaces/cli/manual_migrate.py` (1,422 bytes) — Manual migration executor.
`interfaces/cli/verify_migrations.py` (3,002 bytes) — Migration verification.

---

## CATEGORY 7: API Endpoint Depth

### API Server Entry Point

**File:** `projections/api/main.py` (6,139 bytes)
**Framework:** FastAPI
**Launcher:** `scripts/ds_dashboard.py` (831 bytes) → delegates to `interfaces/cli/ds_dashboard.py` (9,408 bytes)

### Registered Router Prefixes

| Router module | Prefix | Tags |
|---------------|--------|------|
| metrics | /api/v1/metrics | metrics |
| insights | /api/v1/insights | insights |
| reports | /api/v1/reports | reports |
| exports | /api/v1/export | export |
| schedules | /api/v1/schedules | schedules |
| realtime | /api/v1 | realtime |
| alerts | /api/v1/alerts | alerts |
| ml | /api/v1/ml | ml |
| analytics | /api/v1/analytics | analytics |
| project_intelligence | /api/v1/projects | projects |
| prd | (no prefix — inline) | prd |
| discovery_internal | /api/discovery/internal | discovery |
| discovery_external | (no prefix — inline) | discovery |
| discovery_research | (no prefix — inline) | discovery |
| hooks | /api/v1 | hooks |
| security | /api/v1 | security |
| audits | /api/v1 | audits |
| intelligence | /api/v1/intelligence | intelligence |
| telemetry | /api/telemetry | telemetry |
| shared_intelligence | /api/shared-intelligence | shared-intelligence |
| frontend | (not shown in include list) | — |
| sqlite_schema | (not shown in include list) | — |

### Route File Sizes

| File | Bytes |
|------|-------|
| project_intelligence.py | 109,882 |
| shared_intelligence.py | 31,435 |
| security.py | 24,690 |
| exports.py | 27,881 |
| intelligence.py | 36,438 |
| discovery_internal.py | 19,562 |
| alerts.py | 17,803 |
| metrics.py | 18,663 |
| audits.py | 20,691 |
| hooks.py | 19,236 |
| schedules.py | 16,086 |
| discovery_research.py | 13,214 |
| reports.py | 10,603 |
| insights.py | 11,351 |
| analytics.py | 11,908 |
| prd.py | 9,224 |
| discovery_external.py | 8,379 |
| realtime.py | 5,403 |
| telemetry.py | 4,590 |
| ml.py | 4,060 |
| sqlite_schema.py | 2,628 |
| frontend.py | 1,445 |

### WebSocket

`projections/api/websocket/connection_manager.py` (8,563 bytes) — WebSocket connection manager for real-time streaming.

### Token Attribution Query Module

`projections/api/queries/token_attribution.py` (12,808 bytes) — dedicated query module for token attribution, separate from route handlers.

### Safety Layer

`projections/api/safety.py` (2,933 bytes) — API safety middleware.

---

## CATEGORY 8: Adapter / Integration Depth

### Integrations Module Structure

`integrations/` contains the adapter target infrastructure:

| File | Bytes | Purpose |
|------|-------|---------|
| detector.py | 1,382 | Detects which AI tools are installed |
| health.py | 5,602 | Integration health checks |
| manifest.py | 2,734 | Integration manifest management |
| compiler/claude_code.py | 11,251 | Claude Code adapter compiler |
| installer/base.py | 1,808 | Base installer abstract class |
| installer/claude_code.py | 34,269 | Claude Code installer (largest file in module) |
| installer/file_ops.py | 1,591 | File operation helpers for installation |
| targets/claude_code/settings_merge.py | 9,055 | Claude Code settings.json merge logic |
| targets/claude_code/hooks_template.json | — | Hook registration template |

### Registered Adapter: claude_code

The only implemented adapter target is `claude_code`. No other adapter targets exist in `integrations/targets/`.

### Adapter Projection Files

`adapter-projections/` directory exists at repo root. Not crawled in detail — present for operator-local projections.

### Compiler Output

`integrations/compiler/claude_code.py` (11,251 bytes) — generates CLAUDE.md projection from SQLite authority. This is the source of the projection file at `C:\Users\Dannis Seay\.claude\projects\C--Users-Dannis-Seay\<proj-id>\CLAUDE.md`.

### Installed State

Installed version token: `C:\Users\Dannis Seay\.dream-studio\state\installed-version` contains `2026-05-17` (string, not a semver).

### Platform Detection Output

`C:\Users\Dannis Seay\.dream-studio\state\platform.json`:
```json
{"os_name": "Windows", "os_version": "10.0.26200", "shell": "powershell",
 "python_version": "3.12.8", "terminal": "Windows Terminal",
 "is_windows": true, "is_macos": false, "is_linux": false}
```

---

## CATEGORY 9: Workflows — Depth

### All Canonical Workflow Files

Location: `canonical/workflows/`

| File | Bytes | Node Count (approx) |
|------|-------|---------------------|
| audit-to-fix.yaml | 2,329 | 7 nodes, 1 gate |
| client-deliverable.yaml | 3,835 | 7 nodes, 1 gate |
| comprehensive-review.yaml | 2,689 | 7 nodes, 5 parallel review nodes |
| daily-close.yaml | 3,605 | 4 nodes |
| daily-standup.yaml | 3,445 | 5 nodes, 1 gate |
| domain-ingest.yaml | 8,352 | 4 phases/nodes, 1 gate |
| domain-refresh.yaml | 6,295 | 4 nodes |
| feature-research.yaml | 26,274 | 14 nodes, 2 gates |
| fix-issue.yaml | 3,077 | 8 nodes, 3 gates |
| game-feature.yaml | 5,378 | 9 nodes, 2 gates |
| hotfix.yaml | 1,501 | 5 nodes, 1 gate |
| idea-to-pr.yaml | 4,390 | partial: 3 gates visible |
| optimize.yaml | 18,881 | — |
| pre-push.yaml | 2,307 | — |
| production-readiness.yaml | 2,807 | — |
| project-audit.yaml | 3,184 | — |
| prototype.yaml | 1,710 | — |
| README.md | 2,058 | (documentation) |
| safe-refactor.yaml | 2,099 | — |
| security-audit.yaml | 14,077 | — |
| self-audit.yaml | 10,646 | — |
| studio-analytics.yaml | 6,953 | — |
| studio-onboard.yaml | 50,816 | 12-13 nodes (executed in DB: 13 completed) |
| ui-feature.yaml | 1,763 | — |

Total workflows: 23 YAML files + 1 README.
Largest workflow: `studio-onboard.yaml` (50,816 bytes).
Second largest: `feature-research.yaml` (26,274 bytes).

### Workflow Runtime Data (from DB)

Two workflow runs exist in `raw_workflow_runs`:
1. `studio-onboard-1779058590`: status=aborted, 11/12 nodes done, started 2026-05-17T22:56:30
2. `studio-onboard-1779063188`: status=completed, 13/13 nodes done, started 2026-05-18T00:13:08

25 node execution records in `raw_workflow_nodes`. First node (config-setup) was skipped with output "no skill defined". Second node (discovery) failed with "Unknown skill: ds-core:build".

### Workflow Engine Location

`control/execution/workflow/engine.py` (13,373 bytes)
`control/execution/workflow/runner.py` (20,797 bytes)
`control/execution/workflow/state.py` (19,860 bytes)
`control/execution/workflow/validate.py` (9,816 bytes)
`control/execution/workflow/registry.py` (3,760 bytes)
`control/execution/workflow/wave_executor.py` (13,568 bytes)
`control/execution/workflow/wave_executor_enhanced.py` (14,914 bytes)
`control/execution/workflow/cost.py` (6,482 bytes)
`control/execution/workflow/learning.py` (9,201 bytes)
`control/execution/workflow/tracking.py` (2,435 bytes)

### Workflow State Files

`C:\Users\Dannis Seay\.dream-studio\state\workflow-checkpoint.json`:
```json
{"workflow_key": "wf-fail-1", "last_node": "n1", "status": "failed", "timestamp": "2026-05-20T21:59:02..."}
```

`C:\Users\Dannis Seay\.dream-studio\state\workflows.json`:
```json
{"schema_version": 1, "active_workflows": {}}
```

`C:\Users\Dannis Seay\.dream-studio\state\workflow-sessions\`: Two run-key subdirs (studio-onboard-1779058590 with repo-context.json, studio-onboard-1779063188).

---

## CATEGORY 10: Configuration Depth

### Python Dependencies

**requirements.txt** (777 bytes) — production dependencies:
- pydantic>=2.0
- jsonschema>=4.0
- sentry-sdk
- pandas>=2.0
- Jinja2>=3.1
- PyYAML>=6.0
- psutil>=5.9
- networkx>=3.0
- cachetools>=5.0
- fastapi>=0.100
- uvicorn>=0.23
- httpx>=0.24
- python-multipart>=0.0.6
- Comments note: giskard, rebuff, llm-guard require Python <3.12 and are excluded (stubbed). tiktoken and apscheduler are optional and commented out.

**requirements-dev.txt** (204 bytes):
- -r requirements.txt (inherits)
- pytest==9.0.3
- pytest-cov==7.1.0
- freezegun>=1.5
- factory-boy>=3.3
- black>=24.0
- flake8>=7.0
- pip-audit>=2.7
- pre-commit>=3.0

**requirements-semantic.txt** (357 bytes) — optional:
- sentence-transformers>=2.2
- Note: default Dream Studio operation uses TF-IDF and FTS5 and does NOT require this.

### pyproject.toml Configuration

**[tool.black]:** line-length = 100

**[project.scripts]:** ds = "interfaces.cli.ds:main"

**[tool.flake8]:** max-line-length = 100; per-file-ignores for tests (E501, F401)

**[tool.pytest.ini_options]:**
- testpaths = ["tests", "analytics/tests"]
- asyncio_mode = "auto"
- addopts = "-v --color=no"
- markers: runtime_reliability (Phase 5 runtime reliability gate)

**[tool.coverage.run]:**
- source = ["hooks/lib", "packs/domains/domain_lib"]
- fail_under = 70
- Omitted from coverage: workflow_state.py, traceability.py, deprecation.py, document_store.py, migrate_files_to_sqlite.py, research_engine.py, research_methods.py, wave_executor.py, pattern_learning.py, workflow_learning.py, token_optimization.py, repo_analyzer.py, skill_router.py, skill_calibration.py, component_extractor.py, findings_summarizer.py, team_context.py

### Runtime Config Files

`C:\Users\Dannis Seay\.dream-studio\config.json` (385 bytes) — operator-local configuration.

`C:\Users\Dannis Seay\.claude\settings.json` — Claude Code settings. Key fields:
- model: claude-sonnet-4-6
- Hook registrations for UserPromptSubmit, Stop, PostCompact, PostToolUse
- 11 MCP servers configured
- allowedTools includes mcp__github__*, mcp__filesystem__*, and others

`C:\Users\Dannis Seay\.dream-studio\state\platform.json` — platform detection result (see Category 8).

### No .env Files Found

No `.env` or `.env.*` files found in `dream-studio-clean/` root or subdirectories.

### Template Project Standards

`packs/domains/templates/project-standards/` contains a template set for new projects:
- pyproject.toml (262 bytes)
- requirements.txt (27 bytes)
- requirements-dev.txt (123 bytes)
- .coveragerc (52 bytes)
- .pre-commit-config.yaml (78 bytes)
- Makefile (96 bytes)
- CONTRIBUTING.md (71 bytes)
- SECURITY.md (43 bytes)
- README.md (87 bytes)

---

## CATEGORY 11: Documentation Depth

### docs/ Directory Structure

Top-level docs directories: architecture/, audits/, authoring/, canonical/, contracts/, demo/, operations/, pilot/, product/, publication/, schema/, setup/

### Document Category Counts

| Category | File Count |
|----------|-----------|
| contracts/ | 30 files |
| architecture/ | 10 files |
| operations/ | 20 files |
| publication/ | 11 files |
| product/ | 7 files |
| demo/ | 10+ files |
| pilot/ | 5 files |
| audits/ | 5+ files (this audit) |

### Notable Architecture Documents

- `docs/ARCHITECTURE.md` — top-level architecture overview
- `docs/architecture/dream-studio-ai-orchestration-architecture.md` — main architecture doc
- `docs/architecture/dream-studio-ai-orchestration-architecture.mmd` — Mermaid diagram source
- `docs/architecture/dream-studio-canonical-data-erd.mmd` — ERD diagram source
- `docs/architecture/event-store.md` — event store architecture
- `docs/architecture/shared-authority-and-adapter-projections.md`
- `docs/architecture/dream-studio-execution-telemetry-spine.md`
- `docs/architecture/dream-studio-dashboard-projection-mapping.md`
- `docs/architecture/dream-studio-dashboard-projection-mapping.yaml`
- `docs/architecture/SYSTEM.md`
- `docs/DATABASE.md` — database documentation
- `docs/HOOK_RUNTIME.md` — hook runtime documentation
- `docs/WORKFLOW_RUNTIME.md` — workflow runtime documentation
- `docs/TRANSACTION_SAFETY_GUIDE.md`
- `docs/MIGRATION_AUTHORITY.md`
- `docs/PUBLICATION_BOUNDARY.md`
- `docs/RUNTIME_RELIABILITY_GATE.md`

### Contract Documents

30 contract files in `docs/contracts/`. Key contracts:
- adapter-contract.md, agent-contract.md, approval-contract.md
- artifact-format-policy.md
- dashboard-projection-model-contract.md
- event-contract.md
- execution-packet-contract.md
- file-structure-authority-policy.md
- governance-contract.md
- handoff-packet-contract.md
- hook-contract.md
- human-in-the-loop-contract.md
- operator-decision-contract.md
- portable-execution-contract.md
- projection-contract.md
- research-source-contract.md
- security-review-* (8 security review contract files)
- skill-contract.md
- state-contract.md
- workflow-contract.md
- work-ledger-contract.md
- work-order-contract.md
- work-order-paused-work-contract.md
- work-result-contract.md

### Canonical Schema Files

`docs/canonical/canonical_event_v1_schema.json` — JSON Schema for CanonicalEventEnvelope
`docs/canonical/event_taxonomy_v1.json` — Allowed event type taxonomy (see Category 14)

### Operational Runbooks

`docs/operations/` — 20 operational documents covering: adapter workspace hygiene, career ops, code history guardrail, docker clean room, docker module profiles, expert workflow systems, external project validation, GitHub CI strategy, installed adapter runtime, lint/format baseline, local runtime, platform hardening, PRD authority lifecycle, product readiness, repo publication privacy, task attribution, troubleshooting, windows dev commands, work orders.

---

## CATEGORY 12: Tests Depth

### Test Directory Structure

`tests/` contains:
- `conftest.py` (73 bytes)
- `factories.py` (219 bytes)
- `core/` — 2 test files
- `evals/` — 9 test files
- `integration/` — 47 test files
- `integration/emitters/` — 1 test file
- `integration/integrations/` — 4 test files
- `integration/spool/` — 8 test files
- `runtime_verification/` — 1 test file
- `unit/` — 259+ test files
- `unit/canonical/` — 7 test files
- `unit/emitters/` — 3 test files
- `unit/gates/` — 4 test files
- `unit/health/` — 1 test file
- `unit/hooks/` — 2 test files
- `unit/integrations/` — 11 test files
- `unit/spool/` — 5 test files
- `validation/` — 4 test files

**Total test files (non-__init__.py):** approximately 350 files

### Test Subdirectory Counts

| Directory | Test Files |
|-----------|-----------|
| tests/unit/ (root-level) | ~230 |
| tests/unit/canonical/ | 7 |
| tests/unit/emitters/ | 3 |
| tests/unit/gates/ | 4 |
| tests/unit/health/ | 1 |
| tests/unit/hooks/ | 2 |
| tests/unit/integrations/ | 11 |
| tests/unit/spool/ | 5 |
| tests/integration/ (root-level) | ~36 |
| tests/integration/emitters/ | 1 |
| tests/integration/integrations/ | 4 |
| tests/integration/spool/ | 8 |
| tests/evals/ | 9 |
| tests/core/ | 2 |
| tests/runtime_verification/ | 1 |
| tests/validation/ | 4 |

### Notable Test Files

`tests/integration/spool/test_ta6_e2e_attribution.py` (14,087 bytes) — largest spool integration test
`tests/unit/test_shared_intelligence_*.py` — 11 files covering shared intelligence module
`tests/unit/test_work_order_*.py` — 23 files covering work order module
`tests/unit/test_ta*.py` — 9 files covering task attribution workstream (TA0-TA5)
`tests/validation/T134_end_to_end_validation.py`, `T145_end_to_end_validation.py` — numbered validation tests

### Test Infrastructure

`tests/conftest.py` (73 bytes) — minimal conftest with SIGINT handler (pytest-level)
`tests/factories.py` (219 bytes) — factory-boy factory definitions
`projections/tests/` — separate test suite for projections module (100+ test files in projections/)
`projections/core/scheduler/test_scheduler.py` (15,135 bytes) — scheduler tests co-located with source

### Pytest Configuration (from pyproject.toml)

- testpaths: ["tests", "analytics/tests"]
- asyncio_mode: auto
- filterwarnings: ignore DeprecationWarning, PendingDeprecationWarning
- markers: runtime_reliability

### Coverage Target

fail_under = 70 (in `[tool.coverage.report]`)

---

## CATEGORY 13: Discovered Additional Categories

### GitHub CI/CD

`.github/workflows/`:
- `ci.yml` (1,414 bytes) — primary CI
- `full-ci.yml` (776 bytes) — full CI (broader test scope)
- `release-validation.yml` (1,124 bytes) — release validation gate
- `validate-skills.yml` (2,406 bytes) — skill validation gate

`.github/scripts/validate-skills.py` (7,733 bytes) — Python script invoked by validate-skills.yml
`.github/SKILL_STANDARDS.md` (9,715 bytes) — canonical skill authoring standards
`.github/PULL_REQUEST_TEMPLATE.md` (1,314 bytes) — PR template

### Guardrails Module

`guardrails/` — security scanner infrastructure:
- `enforcement.py` (3,279 bytes) — guardrail enforcement logic
- `evaluator.py` (12,166 bytes) — guardrail evaluation engine
- `loader.py` (3,668 bytes) — rule loader
- `models.py` (3,320 bytes) — guardrail data models
- `rules/quality.yaml` (2,393 bytes) — quality rules
- `rules/security.yaml` (2,148 bytes) — security rules
- `scanners/giskard_scanner.py` (17,790 bytes) — Giskard ML security scanner (stub — requires Python <3.12)
- `scanners/llm_guard_scorer.py` (15,324 bytes) — LLM Guard scorer (stub)
- `scanners/rebuff_validator.py` (16,020 bytes) — Rebuff prompt injection validator (stub)

### Packs Module

`packs/` — pack-specific rules, context, agents:
- `packs/core/agents/` — director, chief-of-staff, engineering stubs
- `packs/core/context/` — director-corrections.md, director-preferences.md, fullstack-standards.md, session-context.md, session-primer.md
- `packs/domains/agents/` — client.md, game.md stubs
- `packs/domains/rules/game/` — game-specific coding rules (7 rule files)
- `packs/domains/templates/project-standards/` — project boilerplate template
- `packs/quality/rules/structure/architecture.md`, `fsc.md` — FSC structure rules

### Emitters Module

`emitters/claude_code/`:
- `emitter.py` (4,770 bytes) — event emitter for Claude Code
- `project.py` (2,229 bytes) — project context emitter
- `run.py` (5,377 bytes) — run-level emitter
- `session.py` (876 bytes) — session emitter

`emitters/shared/spool_writer.py` (616 bytes) — shared spool write helper

### Projections Exporters

`projections/exporters/` — report/export format generators:
- `excel_exporter.py` (26,966 bytes)
- `excel_templates.py` (39,160 bytes) — largest exporter file
- `pdf_exporter.py` (16,723 bytes)
- `powerbi_exporter.py` (27,295 bytes)
- `pptx_exporter.py` (20,539 bytes)
- `csv_exporter.py` (14,947 bytes)
- `chart_renderer.py` (12,179 bytes)

### Frontend Asset

`projections/frontend/dashboard.html` (501,683 bytes) — full HTML dashboard (largest single file in repo).

### Projections Dashboard Generator

`projections/generators/production_dashboard.py` (53,859 bytes) — production dashboard generator.

### Control Module Submodules

`control/` contains:
- `analysis/` — audit, bugs, discovery, engine, findings_summarizer, quality_scoring, repo_analyzer, research, security_patterns, synthesis, stacks/ (astro, nextjs, python_generic detectors)
- `context/` — compiler, context7_manager, handoff, monitor, pack, repo, team
- `execution/` — dispatch_helpers, dispatch_tracking, models/selector, workflow/ (engine, runner, state, validate, registry, wave_executor, wave_executor_enhanced, cost, learning, tracking)
- `research/` — engine, memory, methods, tools (40,552 bytes — largest in research), web
- `review/` — engine
- `session/` — cache, manager, parser
- `skills/` — calibration, completion, loader, metrics, router

### Spool Module

`spool/`:
- `ingestor.py` (10,088 bytes) — event ingestion pipeline, Windows SIGINT handler
- `session_harvester.py` (17,928 bytes) — session state harvester
- `states.py` (792 bytes) — spool state definitions
- `writer.py` (1,076 bytes) — spool write operations
- `config.py` (243 bytes) — spool configuration

### Shared Module

`shared/`:
- `paths.py` (67 bytes) — path constants
- `config.py` (21 bytes) — shared config
- `mcp-integrations/` — MCP integration test docs and scripts
- `repo_analysis/` — repo analysis utilities (analyzer, cli, formatters, pattern_extractors)
- `version-detection.sh` (40 bytes)

### Scripts Directory

`scripts/`:
- `dev.ps1` (10,661 bytes) — development PowerShell script
- `dashboard_smoke_harness.py` (3,654 bytes) — dashboard smoke test
- `ds_dashboard.py` (831 bytes) — dashboard launcher shorthand
- `requeue_failed.py` (5,377 bytes) — failed event requeue
- `runtime_state_hash_guard.py` (4,959 bytes) — runtime state hash guard
- `docker_runtime_check.py` (1,967 bytes) — Docker runtime checker
- `lesson_queue.py` (457 bytes) — lesson queue launcher

### Core Module Submodules (partial — 37 subdirectories)

`core/` subdirectories: adapters, config, decisions, design_briefs, dispatch, event_store, events, execution, gates, graph, health, learning, memory, milestones, monitoring, observability, ontology, pricing, production_readiness, projections, projects, recovery, release, repo_actions, research, sdlc, security, shared_intelligence, skills, storage, telemetry, upgrade, utils, validation, work_orders

---

## CATEGORY 14: Event Types Registry — Depth

### Taxonomy Source

File: `docs/canonical/event_taxonomy_v1.json`
Schema version: 1.0.0

### All Registered Namespaces and Counts

| Namespace | Event Type Count |
|-----------|-----------------|
| research | 3 |
| prd | 7 |
| decision | 5 |
| task | 4 |
| skill | 3 |
| workflow | 3 |
| agent | 3 |
| ingestion | 3 |
| reconstruction | 2 |
| business | 2 |
| contract | 3 |
| security | 7 |
| usage | 3 |
| validation | 1 |
| execution | 4 |
| analysis | 4 |
| repo | 4 |
| model | 3 |
| session | 4 |
| tool | 3 |
| hook | 3 |
| backfill | 2 |
| migration | 1 |
| database | 1 |
| alert | (in taxonomy) |
| scan | (in taxonomy) |
| vulnerability | (in taxonomy) |
| memory | (in taxonomy) |
| plan | (in taxonomy) |
| phase | (in taxonomy) |
| wave | (in taxonomy) |
| system | (in taxonomy) |
| test | (in taxonomy) |

**Total registered event types in taxonomy:** 112

### Live Event Types in canonical_events Table (actual observed data)

| Event Type | Count | First Observed | Last Observed |
|-----------|-------|----------------|---------------|
| tool.execution.completed | 822 | 2026-05-17T01:18:33 | 2026-05-22T15:05:17 |
| prompt.lifecycle.submitted | 248 | 2026-05-16T22:33:59 | 2026-05-22T16:37:19 |
| hook.tool_activity | 246 | 2026-05-21T20:58:14 | 2026-05-22T16:44:22 |
| token.consumption.recorded | 179 | 2026-05-16T22:33:59 | 2026-05-22T16:45:11 |
| event.validation.failed | 57 | 2026-05-17T20:40:02 | 2026-05-19T23:02:17 |
| system.session.recorded | 51 | 2026-05-17T20:30:43 | 2026-05-22T16:37:19 |
| system.hook.execution.logged | 45 | 2026-05-17T20:40:02 | 2026-05-19T00:21:08 |
| system.session.closed | 32 | 2026-05-17T20:30:43 | 2026-05-22T16:02:47 |
| system.handoff.created | 26 | 2026-05-17T20:30:43 | 2026-05-22T16:02:48 |
| workflow.node.completed | 25 | 2026-05-18T00:13:03 | 2026-05-18T01:15:08 |
| skill.invoked | 21 | 2026-05-17T01:19:44 | 2026-05-20T21:55:50 |
| context.threshold.crossed | 18 | 2026-05-17T02:51:45 | 2026-05-22T14:21:38 |
| work_order.started | 15 | 2026-05-17T01:45:19 | 2026-05-19T23:07:17 |
| work_order.created | 14 | 2026-05-17T01:43:28 | 2026-05-17T01:43:28 |
| task.created | 9 | 2026-05-17T01:43:28 | 2026-05-19T22:05:37 |
| token.consumed | 7 | 2026-05-22T12:36:07 | 2026-05-22T14:23:59 |
| milestone.created | 4 | 2026-05-17T01:43:28 | 2026-05-17T01:43:28 |
| task.completed | 4 | 2026-05-19T22:07:17 | 2026-05-19T22:07:47 |
| work_order.closed | 4 | 2026-05-17T02:30:23 | 2026-05-19T23:00:59 |
| gate.bypassed | 3 | 2026-05-17T02:30:23 | 2026-05-17T02:32:40 |
| project.created | 3 | 2026-05-17T01:22:43 | 2026-05-22T13:22:45 |
| workflow.completed | 2 | 2026-05-18T00:13:03 | 2026-05-18T01:15:08 |

**Total live events:** 1,835

**Discrepancy note:** Observed event types (hook.tool_activity, prompt.lifecycle.submitted, token.consumption.recorded, system.*) do not all appear in the taxonomy JSON. The taxonomy defines the allowed types; the DB contains types emitted by the actual hook runtime.

---

## CATEGORY 15: Schemas / Data Contracts — Depth

### JSON Schema Files

`docs/canonical/canonical_event_v1_schema.json` — CanonicalEventEnvelope JSON Schema (pydantic-compatible)
`docs/canonical/event_taxonomy_v1.json` — Allowed event type taxonomy (112 types, 34 namespaces)

### YAML Contract Files

`docs/contracts/dashboard-projection.sample.yaml` — sample dashboard projection contract
`docs/contracts/security-review-report.sample.yaml` — sample security review report
`docs/contracts/security-review-scan-catalog.sample.yaml` — sample scan catalog
`docs/contracts/security-review-scan-catalog.yaml` — active scan catalog
`docs/contracts/security-review-tier0-work-order.sample.yaml` — sample tier-0 work order

`docs/architecture/dream-studio-dashboard-projection-mapping.yaml` — dashboard projection mapping

`docs/product/dream-studio-stage-gates.yaml` — stage gate definitions

`docs/publication/`:
- `clean_clone_validation_evidence.yaml`
- `contract-atlas.freshness-manifest.json`
- `contract-atlas.public_sanitized.json`
- `final_history_rewrite_branch_classification.yaml`
- `final_history_rewrite_branch_classification_repo*.yaml`
- `git_history_privacy_audit.yaml`
- `history_rewrite_rehearsal_evidence.yaml`
- `ignored_file_audit.yaml`
- `repo_publication_cleanliness_certificate.yaml`
- `tracked_file_audit.yaml`

### Pydantic Model Locations

`core/events/models.py` — CanonicalEventEnvelope and related models
`projections/api/models/insights.py` (1,991 bytes)
`projections/api/models/metrics.py` (2,663 bytes)
`projections/api/models/reports.py` (6,006 bytes)
`projections/models/events.py` (3,149 bytes)
`guardrails/models.py` (3,320 bytes)

### Contract Atlas

`docs/publication/contract-atlas.public_sanitized.json` — sanitized public contract atlas
`docs/publication/contract-atlas.freshness-manifest.json` — contract freshness tracking

`interfaces/cli/contract_atlas_lifecycle_gate.py` (5,031 bytes) — enforces contract atlas lifecycle
`interfaces/cli/contract_docs_drift_gate.py` (3,697 bytes) — enforces contract doc freshness

---

## CATEGORY 16: Runtime State Directory — Depth

### Directory Structure

`C:\Users\Dannis Seay\.dream-studio\`:
- `.sessions/` — session files by date
- `backups/` — timestamped backup files
- `bin/` — installed executables
- `events/` — raw event spool files
- `integrations/` — integration state
- `meta/` — meta state files
- `planning/` — planning state
- `state/` — primary state directory

### `.sessions/` Contents

Dated subdirectories from 2026-05-17 through 2026-05-22. Each date dir contains pairs of files:
- `handoff-<hash>.md` (507–2,356 bytes)
- `recap-<hash>.md` (1,352–3,188 bytes)

Recent session files (descending by date):
- 2026-05-22/recap-567a31dd.md (1,432 bytes), handoff-567a31dd.md (551 bytes)
- 2026-05-22/recap-38a930c3.md (1,352 bytes), handoff-38a930c3.md (507 bytes)
- 2026-05-22/recap-dcc010ef.md (3,188 bytes), handoff-dcc010ef.md (2,356 bytes)
- 2026-05-22/recap-e900bd9e.md (2,735 bytes), handoff-e900bd9e.md (1,942 bytes)
- 2026-05-21/recap-1c908fd6.md (2,674 bytes), handoff-1c908fd6.md (1,883 bytes)

### `state/` File Inventory

| File | Size | Purpose |
|------|------|---------|
| studio.db | 6,500,352 bytes | Primary SQLite authority database |
| studio.db.bak | 5,300,224 bytes | Automatic backup of studio.db |
| studio.db.pre-ta0c-backup | 6,295,552 bytes | Pre-TA0c workstream backup |
| hook-timing.jsonl | 387,423 bytes | Hook execution timing log (3,596 lines) |
| activity.json | 269 bytes | Current agent activity feed |
| skill-usage.jsonl | 366 bytes | Skill usage log (3 lines) |
| telemetry-buffer.jsonl | 91 bytes | Telemetry buffer (1 line) |
| pending-handoff.json | 164 bytes | In-progress handoff state |
| platform.json | 218 bytes | Platform detection cache |
| installed-version | 12 bytes | Contains string: "2026-05-17" |
| machine_id | 36 bytes | UUID: c6676983-2495-456b-86b9-2bf9e851c7f9 |
| workflow-checkpoint.json | 132 bytes | Last workflow checkpoint |
| workflows.json | 54 bytes | Active workflow registry |

`state/diagnostics/`:
- token-capture.jsonl (3,690 bytes, last modified 2026-05-22)

`state/workflow-sessions/`:
- studio-onboard-1779058590/ (contains repo-context.json, 5,449 bytes)
- studio-onboard-1779063188/ (empty dir or minimal contents)

### `backups/` Contents

`backups/claude_code/` — contains timestamped `.bak` files from 2026-05-19T230941Z onwards.

### `pending-handoff.json` Content

```json
{"session_id": "dd1a4f73-4bf2-40c5-8e4f-769e957851d8",
 "triggered_at": 1779410621,
 "cwd": "C:\\Users\\Dannis Seay",
 "invocation_flags": [],
 "status": "in_progress"}
```

### `activity.json` Content (at audit time)

Records current agent activity feed. At time of audit, showed File Writer agent writing 00-mechanical-inventory.md.

---

## CATEGORY 17: Background Processes — Depth

### Hook Process Model

Hooks run as subprocess calls from `~/.claude/hooks/run.py`. Each hook handler is a Python subprocess launched by the Claude Code hook mechanism. No persistent background processes are started by the hook system.

### Dashboard Server

`projections/api/main.py` — FastAPI + uvicorn server. Not running persistently by default. Launched on demand via `py scripts/ds_dashboard.py` or `py interfaces/cli/ds_dashboard.py`. Port: Cannot determine from available files (not found in main.py header without deep read).

### Spool Ingestor

`spool/ingestor.py` — called synchronously during Stop hook via `run.py → spool.ingestor.ingest_pending()`. Not a persistent background process.

### Session Harvester

`spool/session_harvester.py` (17,928 bytes) — called during handoff generation. Not a persistent background process.

### Scheduler

`projections/core/scheduler/job_scheduler.py` (24,392 bytes) — APScheduler-based. Can run as background service. `projections/core/scheduler/__main__.py` — runnable as `py -m projections.core.scheduler`. This is optional and not auto-started.

### Pulse Collector

`interfaces/cli/pulse_collector.py` (19,339 bytes) — invoked from on-pulse.py hook handler. Runs as a subprocess during UserPromptSubmit hook chain. Not a persistent background process.

---

## CATEGORY 18: Diagnostic Outputs — Depth

### hook-timing.jsonl

**Path:** `C:\Users\Dannis Seay\.dream-studio\state\hook-timing.jsonl`
**Size:** 387,423 bytes (3,596 lines)
**Written by:** `on-tool-activity.py` hook
**Schema (per line):**
```json
{"event": "PostToolUse", "handler": "on-tool-activity", "duration_ms": 25.96, "ts": "2026-05-17T20:28:58Z"}
```
Fields: event (event name), handler (handler name), duration_ms (float), ts (ISO 8601 UTC)
Date range of entries: 2026-05-17 through 2026-05-22

### skill-usage.jsonl

**Path:** `C:\Users\Dannis Seay\.dream-studio\state\skill-usage.jsonl`
**Size:** 366 bytes (3 lines)
**Schema (two observed formats):**
```json
{"ts": "...", "skill": "unknown", "mode": "", "session": "", "recommended_model": "sonnet"}
{"skill_name": "unknown", "invoked_at": "...", "success": 1}
```
Note: Two different schema formats exist in this file. The third line uses skill_name/invoked_at/success. The first two lines use ts/skill/mode/session/recommended_model.

### telemetry-buffer.jsonl

**Path:** `C:\Users\Dannis Seay\.dream-studio\state\telemetry-buffer.jsonl`
**Size:** 91 bytes (1 line)
**Content:**
```json
{"skill_name": "unknown", "invoked_at": "2026-05-19T00:15:03.392141+00:00", "success": 1}
```

### state/diagnostics/token-capture.jsonl

**Path:** `C:\Users\Dannis Seay\.dream-studio\state\diagnostics\token-capture.jsonl`
**Size:** 3,690 bytes
**Last modified:** 2026-05-22 10:23:59
**Written by:** `on-post-tool-use.py` core hook via `core.telemetry.token_capture`

### Session Files (.sessions/)

**Handoff files** (handoff-*.md): 507–2,356 bytes. Written by on-stop-handoff.py hook.
**Recap files** (recap-*.md): 1,352–3,188 bytes. Written by on-stop-handoff.py hook alongside handoff.

### Workflow Session Files

**Path:** `state/workflow-sessions/<run_key>/`
**Content:** `repo-context.json` (5,449 bytes for studio-onboard-1779058590 run).

---

## CATEGORY 19: Spool Architecture — Depth

### Spool Module Files

| File | Bytes | Purpose |
|------|-------|---------|
| spool/__init__.py | 0 | Package marker |
| spool/config.py | 243 | Spool configuration constants |
| spool/ingestor.py | 10,088 | Main ingestion pipeline, SIGINT handler |
| spool/session_harvester.py | 17,928 | Session state harvest logic |
| spool/states.py | 792 | Spool state enum/constants |
| spool/writer.py | 1,076 | Spool write operations |

### Spool Flow

1. Claude Code emits hook events via `~/.claude/hooks/run.py`
2. `run.py` writes events to spool directory (`~/.dream-studio/events/`)
3. On Stop event: `run.py` calls `spool.ingestor.ingest_pending()`
4. `ingestor.py` reads pending spool files and inserts into `studio.db`
5. Events land in `canonical_events` table as `CanonicalEventEnvelope` records

### Windows SIGINT Handling

`spool/ingestor.py` contains module-level Windows CTRL_C handler registered at import time.
`tests/conftest.py` contains pytest-level SIGINT handler.

### CanonicalEventEnvelope Requirement

Every new spool event MUST use `CanonicalEventEnvelope`. Hand-built dicts cause the A0 ingest failure (per operator feedback in MEMORY.md).

### Spool State Values

`spool/states.py` (792 bytes) — defines spool state enum. Cannot determine specific values without reading file.

### Emitter Side

`emitters/claude_code/emitter.py` (4,770 bytes) — Claude Code event emitter that formats events into CanonicalEventEnvelope before writing to spool.
`emitters/claude_code/run.py` (5,377 bytes) — run-level emitter.
`emitters/claude_code/session.py` (876 bytes) — session-level emitter.
`emitters/claude_code/project.py` (2,229 bytes) — project-level emitter.
`emitters/shared/spool_writer.py` (616 bytes) — shared spool write primitive.

### Spool Integration Tests

Located at `tests/integration/spool/`:
- test_cli_event_chain.py (4,512 bytes)
- test_decoupled_pipeline.py (2,097 bytes)
- test_ingestor_sqlite.py (2,241 bytes)
- test_minimal_pair.py (624 bytes)
- test_spool_end_to_end.py (2,232 bytes)
- test_sqlite_isolation.py (275 bytes)
- test_ta6_e2e_attribution.py (14,087 bytes)
- sigint_idle_test.py (688 bytes)

---

## SUPPLEMENTAL: Active Project State

### Dream Studio Project (active in DB)

Project ID: 29ff0914 (partial)
Name: Dream Studio
Status: active
Updated: 2026-05-22T15:06:01

### Dream Command Project (primary build target)

Project ID: a4befdce-bfb6-40ed-9e83-ace93edac44b
Name: Dream Command
Status: paused
Updated: 2026-05-22T15:06:01
Design brief: locked (status=locked, design_system=tech-minimal)
Milestones: 4 (all pending)
Work orders: 14 (2 complete, 1 in_progress, 11 open)

### Work Order Status Summary (Dream Command)

| WO Title | Status | Type |
|----------|--------|------|
| Wire Tauri shell into Vite project | complete | infrastructure |
| Build Dream Studio SQLite data bridge | complete | api_endpoint |
| Build adapter capability card | complete | ui_component |
| Build intelligence foundation dashboard | in_progress | ui_page |
| Build command input interface | open | ui_component |
| Build routing decision engine | open | api_endpoint |
| Wire command dispatch to adapter CLIs | open | api_endpoint |
| Write routing outcome to Dream Studio SQLite | open | data_pipeline |
| Build workflow step coordinator | open | api_endpoint |
| Build workflow progress page | open | ui_page |
| Build inter-step output handoff | open | data_pipeline |
| Build first-run adapter detection | open | saas_feature |
| Build onboarding UI | open | ui_page |
| Configure Tauri signing and build pipeline | open | deployment |

---

*End of Phase 0b Depth Pass*
