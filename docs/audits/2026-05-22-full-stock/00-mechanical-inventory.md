# Phase 0 — Mechanical Inventory
*Audit date: 2026-05-22*
*Repo: C:\Users\Dannis Seay\builds\dream-studio-clean*
*Runtime DB: C:\Users\Dannis Seay\.dream-studio\state\studio.db*

---

## 1. Filesystem Layout

### Top-Level Directory File Counts

| Directory | File Count |
|-----------|-----------|
| .audit | 12 |
| .claude | 513 |
| .github | 8 |
| .planning | 49 |
| .pytest_cache | 5 |
| .vscode | 2 |
| adapter-projections | 9 |
| canonical | 515 |
| control | 109 |
| core | 495 |
| docker-test-results | 1 |
| docs | 149 |
| emitters | 16 |
| examples | 1 |
| guardrails | 20 |
| hooks | 5 |
| integrations | 27 |
| interfaces | 112 |
| packs | 37 |
| projections | 209 |
| runtime | 76 |
| scripts | 14 |
| shared | 24 |
| skills | 42 |
| spool | 12 |
| templates | 34 |
| tests | 726 |
| tools | 10 |
| __pycache__ | 1 |

### Root-Level Source Files

- .dockerignore
- .dream-studio-project
- .flake8
- .gitattributes
- .gitignore
- .pre-commit-config.yaml
- AGENTS.md
- ARCHITECTURE.md
- backlog.md
- CHANGELOG.md
- CLAUDE.md
- compat.py
- CONTRIBUTING.md
- DATABASE.md
- docker-compose.yml
- Dockerfile
- Dockerfile.runtime-check
- DREAM-STUDIO-ROADMAP.md
- ds.cmd
- ds.ps1
- install.ps1
- install.sh
- launch-dashboard
- launch-dashboard.cmd
- LICENSE
- Makefile
- packs.yaml
- pyproject.toml
- pyrightconfig.json
- README.md
- requirements-dev.txt
- requirements-semantic.txt
- requirements.txt
- SECURITY.md
- STRUCTURE.md
- VERSION
- WORKFLOWS.md

### Non-Source Directories

- `.audit/` — 12 .md audit files from prior sessions (2026-05-16 through 2026-05-22)
- `.claude/` — 513 files: agents/, hooks/, skills/, workflows/, CLAUDE.md
- `.github/` — CI/CD workflows (ci.yml, full-ci.yml, release-validation.yml, validate-skills.yml), PULL_REQUEST_TEMPLATE.md, SKILL_STANDARDS.md, scripts/validate-skills.py
- `.planning/` — 49 files: specs/, work-orders/, workflow/ subdirs; slice .md files (Slice-1 through slice-9e), Architecture Audit.md, handoffs
- `.vscode/` — extensions.json, tasks.json
- `docker-test-results/` — .gitkeep only
- `docs/` — 149 files across architecture/, authoring/, canonical/, contracts/, demo/, operations/, pilot/, product/, publication/, schema/, setup/ subdirectories
- `tools/` — 10 files (investigation/audit scripts, .md reports)

---

## 2. Skills

### canonical/skills/ Directories (11 total)

| Directory | Path |
|-----------|------|
| analyze | canonical/skills/analyze |
| core | canonical/skills/core |
| domains | canonical/skills/domains |
| ds-bootstrap | canonical/skills/ds-bootstrap |
| ds-milestone | canonical/skills/ds-milestone |
| ds-project | canonical/skills/ds-project |
| ds-workorder | canonical/skills/ds-workorder |
| quality | canonical/skills/quality |
| security | canonical/skills/security |
| setup | canonical/skills/setup |
| workflow | canonical/skills/workflow |

### canonical/skills/ — Modes Per Pack

**analyze** (maps to ds-analyze): modes/domain-re, modes/intelligence, modes/multi, modes/repo

**core** (maps to ds-core): modes/build, modes/explain, modes/handoff, modes/plan, modes/recap, modes/review, modes/ship, modes/think, modes/verify

**domains** (maps to ds-domains): modes/client-work, modes/dashboard-dev, modes/design, modes/fullstack (sub-modes: backend, frontend, integrate, secure), modes/game-dev, modes/mcp-build, modes/saas-build, modes/website (sub-modes: animate, brand, cip, critique, deck, direction, discover, page, prototype)

**ds-bootstrap**: no modes directory

**ds-milestone**: modes/close, modes/status

**ds-project**: modes/brief, modes/manage, modes/resume, modes/scope

**ds-workorder**: modes/block, modes/close, modes/execute, modes/start, modes/status

**quality** (maps to ds-quality): modes/audit, modes/coach, modes/debug, modes/harden, modes/learn, modes/polish, modes/pr-security-scan, modes/structure-audit

**security** (maps to ds-security): modes/binary-scan, modes/comply, modes/dashboard, modes/dast, modes/mitigate, modes/netcompat, modes/review, modes/scan

**setup** (maps to ds-setup): modes/jit, modes/status, modes/wizard

**workflow** (maps to ds-workflow): no modes subdirectory

### skills/ (repo-root, not canonical) — Additional Skill

- `skills/career/` — modes/apply, modes/evaluate, modes/ops, modes/pdf, modes/scan, modes/track
- `skills/templates/` — config.yml.template, gotchas.yml.template, metadata.yml.template, pack-router-template.md

### .claude/skills/ Installed Directories (9 total)

- ds-analyze
- ds-bootstrap
- ds-core
- ds-domains
- ds-project
- ds-quality
- ds-security
- ds-setup
- ds-workflow

### Discrepancy: canonical/skills vs .claude/skills/

canonical/skills contains: analyze, core, domains, ds-bootstrap, ds-milestone, ds-project, ds-workorder, quality, security, setup, workflow (11 dirs)

.claude/skills contains: ds-analyze, ds-bootstrap, ds-core, ds-domains, ds-project, ds-quality, ds-security, ds-setup, ds-workflow (9 dirs)

Not installed in .claude/skills: ds-milestone, ds-workorder (canonical dirs with ds- prefix); analyze, core, domains, quality, security, setup, workflow (canonical dirs without ds- prefix — mirrored by their ds- counterparts in .claude)

### SKILL.md Files Outside canonical/skills/ (repo root skills/)

- skills/career/SKILL.md
- skills/career/modes/apply/SKILL.md
- skills/career/modes/evaluate/SKILL.md
- skills/career/modes/ops/SKILL.md
- skills/career/modes/pdf/SKILL.md
- skills/career/modes/scan/SKILL.md
- skills/career/modes/track/SKILL.md

---

## 3. Agents

### canonical/agents/ Files

| Filename | Agent Name (from frontmatter) |
|----------|-------------------------------|
| accessibility-expert.md | accessibility-expert |
| data-engineer.md | data-engineer |
| devops-engineer.md | devops-engineer |
| idea-validator.md | idea-validator |
| kubernetes-expert.md | kubernetes-expert |
| mobile-developer.md | mobile-developer |
| research-analyst.md | research-analyst |
| technical-writer.md | technical-writer |
| terraform-architect.md | terraform-architect |

### packs/ Agent Files

- packs/core/agents/chief-of-staff.md — `# Chief of Staff Agent`
- packs/core/agents/director.md — `# Director Persona`
- packs/core/agents/engineering.md — `# Engineering Agent`
- packs/domains/agents/client.md — `# Client Agent`
- packs/domains/agents/game.md — `# Game Agent`

### .claude/agents/ (Installed Copies)

Mirrors canonical/agents/: accessibility-expert.md, data-engineer.md, devops-engineer.md, idea-validator.md, kubernetes-expert.md, mobile-developer.md, research-analyst.md, technical-writer.md, terraform-architect.md

### Agent-Shaped Python Files (agent in filename)

Cannot enumerate: no dedicated search performed for `*agent*.py` outside already-cataloged directories. Files containing "agent" exist in core/shared_intelligence/ and other modules but are not standalone agent definitions.

---

## 4. Hooks

### runtime/hooks/ Files (32 .py files, 4 subdirectories)

**meta/ (18 hooks)**

| File | First Line |
|------|-----------|
| on-context-threshold.py | (no leading comment) |
| on-edit-dispatch.py | #!/usr/bin/env python3 |
| on-first-run.py | #!/usr/bin/env python3 |
| on-memory-retrieve.py | #!/usr/bin/env python3 |
| on-meta-review.py | #!/usr/bin/env python3 |
| on-post-compact.py | #!/usr/bin/env python3 |
| on-prompt-dispatch.py | #!/usr/bin/env python3 |
| on-prompt-validate.py | #!/usr/bin/env python3 |
| on-pulse.py | #!/usr/bin/env python3 |
| on-session-end.py | #!/usr/bin/env python3 |
| on-session-start.py | #!/usr/bin/env python3 |
| on-skill-complete.py | #!/usr/bin/env python3 |
| on-skill-load.py | #!/usr/bin/env python3 |
| on-skill-metrics.py | #!/usr/bin/env python3 |
| on-skill-telemetry.py | #!/usr/bin/env python3 |
| on-stop-dispatch.py | #!/usr/bin/env python3 |
| on-token-log.py | #!/usr/bin/env python3 |
| on-tool-activity.py | #!/usr/bin/env python3 |

**core/ (6 hooks)**

| File | First Line |
|------|-----------|
| on-changelog-nudge.py | #!/usr/bin/env python3 |
| on-milestone-end.py | #!/usr/bin/env python3 |
| on-milestone-start.py | #!/usr/bin/env python3 |
| on-post-tool-use.py | #!/usr/bin/env python3 |
| on-stop-handoff.py | #!/usr/bin/env python3 |
| on-workflow-progress.py | #!/usr/bin/env python3 |

**quality/ (4 hooks)**

| File | First Line |
|------|-----------|
| on-agent-correction.py | #!/usr/bin/env python3 |
| on-quality-score.py | #!/usr/bin/env python3 |
| on-security-scan.py | #!/usr/bin/env python3 |
| on-structure-check.py | #!/usr/bin/env python3 |

**domains/ (1 hook)**

| File | First Line |
|------|-----------|
| on-game-validate.py | #!/usr/bin/env python3 |

### Hooks Registered in C:\Users\Dannis Seay\.claude\settings.json

| Event | Hook Command | Matcher |
|-------|-------------|---------|
| UserPromptSubmit | py "C:/Users/Dannis Seay/.claude/hooks/run.py" UserPromptSubmit | (none) |
| UserPromptSubmit | py "C:/Users/Dannis Seay/.claude/hooks/dispatch/hooks.py" UserPromptSubmit | (none) |
| Stop | py "C:/Users/Dannis Seay/.claude/hooks/run.py" Stop | (none) |
| Stop | py "C:/Users/Dannis Seay/.claude/hooks/dispatch/hooks.py" Stop | (none) |
| PostCompact | py "C:/Users/Dannis Seay/.claude/hooks/run.py" PostCompact | (none) |
| PostCompact | py "C:/Users/Dannis Seay/.claude/hooks/dispatch/hooks.py" PostCompact | (none) |
| PostToolUse | py "C:/Users/Dannis Seay/.claude/hooks/run.py" PostToolUse | Skill |
| PostToolUse | py "C:/Users/Dannis Seay/.claude/hooks/dispatch/hooks.py" PostToolUse | Skill |
| PostToolUse | py "C:/Users/Dannis Seay/.claude/hooks/dispatch/hooks.py" PostToolUse | Edit\|Write |

### Hook File vs Registration Discrepancy

Registered hook scripts: `.claude/hooks/run.py` and `.claude/hooks/dispatch/hooks.py`

The 32 hook files in `runtime/hooks/` are not directly registered in settings.json. They are dispatched through the two registered entry points (`run.py` and `dispatch/hooks.py`). The meta/ hooks in runtime/hooks/ are also copied to `.claude/hooks/runtime/hooks/meta/`.

Runtime/hooks/ not directly registered: all core/, quality/, domains/ hooks, and all meta/ hooks. They are loaded through the dispatch layer.

---

## 5. CLI Commands

### Top-Level Command Groups (37 total)

`py -m interfaces.cli.ds <group>`

| Group | Help Text |
|-------|-----------|
| status | Show installed runtime status |
| version | Show Dream Studio source/runtime version |
| doctor | Run read-only runtime health checks |
| repair | Plan repair actions without mutating state |
| update | Update Dream Studio integration pack |
| dashboard | Show, serve, open, or check the local dashboard |
| validate | Validate installed runtime readiness |
| contract-atlas | Show Contract Atlas summary |
| contract-atlas-refresh | Plan or refresh Contract Atlas lifecycle exports |
| adapters | Show adapter status |
| modules | Show module profile status |
| router | Show adapter router status |
| platform-hardening | Show platform hardening status |
| policy | Preview a policy decision |
| analytics-ingest | Import normalized analytics facts into SQLite authority |
| install | Run first-run setup for selected profiles |
| install-command | Install user-local launchers for the plain ds command |
| acceptance | Run installed platform acceptance against a rehearsal home |
| backup | Plan or create a runtime backup |
| restore-check | Validate a backup without restoring it |
| update-check | Check update readiness without mutation |
| uninstall-check | Inventory uninstall targets without deleting |
| migrate-legacy | Plan or execute a guarded legacy install migration |
| repair-adapters | Plan or repair Dream-Studio-owned adapter surfaces |
| rollback-check | Validate a legacy-upgrade backup without restoring |
| context-packet | Preview a context packet |
| rehearsal-install | Bootstrap a rehearsal runtime |
| spool | Spool event pipeline commands |
| workflow | Workflow execution commands |
| memory | Memory intelligence commands |
| project | Manage Dream Studio projects |
| integrate | Manage AI tool integrations (detect, install, doctor) |
| skill | Invoke or list Dream Studio skills |
| work-order | Manage work orders |
| design-brief | Manage project design briefs |
| milestone | Manage project milestones |
| task | Manage active task context |
| diagnostics | Read or clear the TA3 diagnostic log stream |

### Leaf Commands by Group

**spool**: ingest

**workflow**: start, status, list, advance, run

**memory**: ingest, ingest-sessions

**project**: register, list, status, next, set-active, deactivate, start, delete, state

**integrate**: detect, status, doctor, plan, install

**skill**: invoke, list

**work-order**: start, list, close, block, unblock, task-done, tasks, add-tasks

**design-brief**: show, create, lock, update, set-system

**milestone**: close, list, status

**task**: set-active, active, clear-active

**diagnostics**: list, clear

**dashboard** (flags, not subcommands): --status, --serve, --open, --check

**doctor** (flag): --fix

**Single-action groups** (no subcommands): status, version, repair, update, validate, contract-atlas, adapters, modules, router, platform-hardening, update-check, uninstall-check, restore-check, rollback-check, acceptance, backup, rehearsal-install, context-packet, install, install-command, migrate-legacy, repair-adapters, contract-atlas-refresh, policy, analytics-ingest

---

## 6. Database Tables

*Database: C:\Users\Dannis Seay\.dream-studio\state\studio.db*
*Schema version: 61 migrations applied (_schema_version table)*

### Tables with Non-Zero Row Counts

| Table | Rows |
|-------|------|
| canonical_events | 1,831 |
| ds_design_briefs | 1 |
| ds_documents | 12 |
| ds_documents_fts | 12 |
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
| fts_gotchas_data | 74 |
| fts_gotchas_docsize | 1,488 |
| fts_gotchas_idx | 72 |
| hook_executions | 45 |
| hook_invocations | 917 |
| outcome_records | 2 |
| raw_handoffs | 26 |
| raw_operational_snapshots | 5 |
| raw_sentinels | 112 |
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

### All Tables (147 total, 0-row tables omitted above)

Full list: _schema_version, adapter_authority_profiles, adapter_executions, adapter_result_records, agent_context_scope_policies, agent_invocations, agent_registry_records, agent_result_records, ai_adapter_accounting_profiles, ai_usage_operational_records, alert_history, alert_rules, artifact_authority_records, artifact_records, audit_runs, authority_projection_records, automation_checkpoints, automation_log, blocker_resolution_records, canonical_events, capability_center_records, capability_route_records, career_application_events, career_application_field_mappings, career_applications, career_browser_automation_runs, career_case_studies, career_cover_letter_versions, career_evidence_refs, career_interview_story_bank, career_job_opportunities, career_portfolio_artifacts, career_profile_fields, career_profiles, career_resume_versions, career_role_targets, career_scorecards, compliance_review_flags, connector_ingestion_runs, cor_skill_corrections, dashboard_attention_items, dashboard_authority_reconciliation_records, decision_event_link, decision_log, decision_records, demo_case_study_packets, ds_design_briefs, ds_documents, ds_documents_fts, ds_documents_fts_config, ds_documents_fts_data, ds_documents_fts_docsize, ds_documents_fts_idx, ds_milestones, ds_projects, ds_tasks, ds_technology_signals, ds_work_order_types, ds_work_orders, execution_dependencies, execution_event_links, execution_events, execution_nodes, execution_outputs, fts_gotchas, fts_gotchas_config, fts_gotchas_data, fts_gotchas_docsize, fts_gotchas_idx, github_repo_adoption_decisions, github_repo_attribution_records, github_repo_dependency_findings, github_repo_evaluations, github_repo_integration_candidates, github_repo_license_findings, github_repo_pattern_references, github_repo_security_findings, guardrail_decisions, guardrail_rules_audit, hardening_candidate_records, hook_executions, hook_findings, hook_invocations, installer_distribution_checks, learning_event_records, legacy_canonical_event_import_map, local_watch_schedule_records, log_batch_imports, memory_fts, memory_fts_config, memory_fts_content, memory_fts_data, memory_fts_docsize, memory_fts_idx, model_provider_profiles, outcome_records, pi_analysis_runs, pi_bugs, pi_components, pi_dependencies, pi_improvements, pi_violations, pi_wave_tasks, pi_waves, policy_decision_records, prd_amendment_records, prd_documents, prd_handoffs, prd_plans, prd_route_reconciliation_records, prd_sessions, prd_tasks, prd_version_records, privacy_redaction_export_records, process_runs, production_readiness_assessment_runs, production_readiness_control_results, production_readiness_findings, production_readiness_remediation_work_orders, production_readiness_skill_control_mappings, project_assumption_records, project_change_order_records, project_health_scorecards, project_intake_questions, project_intake_records, project_milestone_records, project_readiness_scorecards, project_work_order_authority_records, raw_approaches, raw_handoffs, raw_lessons, raw_operational_snapshots, raw_planning_specs, raw_pulse_snapshots, raw_research, raw_sentinels, raw_sessions, raw_skill_telemetry, raw_specs, raw_tasks, raw_token_usage, raw_workflow_nodes, raw_workflow_runs, reg_analyzed_repos, reg_gotchas, reg_projects, reg_repo_extractions, reg_repo_research_links, reg_research_sources, reg_skill_deps, reg_skills, reg_workflows, release_readiness_records, research_cache, research_evidence_records, risk_mitigations, risk_register, route_decision_records, sec_cve_matches, sec_hook_checks, sec_manual_reviews, sec_sarif_findings, security_findings, session_tasks, shared_context_packets, skill_evaluation_runs, skill_invocations, sqlite_sequence, sum_analytics_run, sum_skill_summary, task_attribution_records, team_rollup_records, telemetry_entity_registry, telemetry_module_registry, token_usage_records, tool_embeddings_cache, tool_invocations, tool_registry, validation_failures, validation_results, workflow_agent_skill_mappings, workflow_invocations

### Views (13 total)

- effective_skill_runs
- v_active_execution
- v_blocked_nodes
- v_completion_rate
- vw_activity_timeline
- vw_approach_patterns
- vw_guardrail_decisions
- vw_hook_performance
- vw_prd_progress
- vw_project_readiness_latest
- vw_risk_hotspots
- vw_security_summary
- vw_task_details

### Indexes

Cannot enumerate all individually — 200+ indexes exist covering every major table. Naming convention: `idx_<table>_<column(s)>`.

---

## 7. Migrations

*Location: core/event_store/migrations/*
*Total: 64 files (001 through 064, with gaps at 011, 035, 036)*

| File | First Comment |
|------|---------------|
| 001_initial.sql | Migration 001: Initial schema (workflow runs, telemetry, analytics) |
| 002_approaches.sql | Migration 002: Approach capture (tracks what works vs fails per skill) |
| 003_registry.sql | Migration 003: Skill registry (skills, gotchas, workflows, dependencies) |
| 004_operations.sql | Migration 004: Operational tables, indexes, FTS5, column additions |
| 005_automation_tables.sql | Migration 005: Create automation tracking tables |
| 006_alerts.sql | Migration 006: Alert system tables |
| 007_document_system.sql | Migration 007: Document system and analyzed repos registry |
| 008_research_and_waves.sql | Migration 008: Research caching and wave execution tracking |
| 009_project_intelligence.sql | Migration 009: Project Intelligence Wave 2 - Core Analysis Capabilities |
| 010_workflow_learning.sql | Migration 010: Workflow Learning System - Project Intelligence Wave 6 |
| 012_prd_schema.sql | Migration 012: PRD Schema Refactor |
| 013_discovery_tables.sql | Migration 013: Discovery System Tables |
| 014_graph_views.sql | Migration 014: Graph Analysis Views |
| 015_performance_indexes.sql | Migration 015: Performance Indexes |
| 016_tool_embeddings.sql | Migration 016: Tool Embeddings Cache |
| 017_activity_log.sql | Migration 017: Central Activity Log (Hub Table) |
| 018_hook_tracking.sql | Migration 018: Hook Execution Tracking (Spoke Tables) |
| 019_update_project_paths.sql | Migration 019: Update project paths to new structure |
| 020_security_findings.sql | Migration 019: Security Findings Tracking (Spoke Tables) |
| 021_risk_register.sql | Migration 020: Risk Register (Spoke Tables) |
| 022_workflow_connections.sql | Migration 021: Workflow Connections (Phase 3 Cross-Domain Traceability) |
| 023_research_connections.sql | Migration 022: Research Connections (Phase 3 Cross-Domain Traceability) |
| 024_learning_connections.sql | Migration 023: Learning Connections (Phase 3 Cross-Domain Traceability) |
| 025_audit_tracking.sql | Migration 024: Audit Run Tracking |
| 026_consolidate_databases.sql | Migration 021: Consolidate Databases |
| 027_guardrail_metadata.sql | Migration 022: Guardrail metadata tables |
| 028_create_automation_checkpoints.sql | Migration 023: Create automation_checkpoints table |
| 029_analytics_views.sql | Migration: Analytics Views |
| 030_adapter_metadata.sql | Migration 030: Adapter Metadata Tables |
| 031_decision_log.sql | Migration 031: Decision log and causal link tables |
| 032_semantic_memory.sql | Migration 032: Semantic memory convergence — Phase 3B schema extension |
| 033_memory_fts.sql | Migration 033: FTS5 retrieval index for memory_entries |
| 034_execution_graph.sql | Migration 034: Execution Graph Layer (promoted from legacy 003) |
| 037_execution_telemetry_traceability_spine.sql | Migration 037: Execution telemetry traceability spine |
| 038_shared_intelligence_authority.sql | Migration 038: Shared intelligence SQLite authority foundation |
| 039_dashboard_authority_reconciliation.sql | Migration 039: Dashboard Authority Reconciliation |
| 040_production_readiness_authority.sql | Migration 040: Production Readiness Authority |
| 041_legacy_canonical_event_import_map.sql | Migration 041: Legacy canonical event reconciliation import map |
| 042_token_usage_source_refs.sql | Migration 042: Token usage source references |
| 043_ai_usage_accounting.sql | Migration 043: AI adapter usage accounting and operational value telemetry |
| 044_career_capability_agent_github_authority.sql | Migration 044: Career Ops, Capability Center, scoped agents, and GitHub repo intake authority |
| 045_task_attribution_authority.sql | Migration 045: Task Attribution And Execution Outcome Authority |
| 046_platform_hardening_authority.sql | Dream Studio platform hardening authority records |
| 047_prd_lifecycle_authority.sql | Migration 047: PRD Lifecycle And Route Authority |
| 048_project_spine.sql | Migration 048: Project Spine — ds_projects / ds_milestones / ds_work_orders / ds_tasks |
| 049_work_order_type.sql | Slice 5b/5e: work_order_type routing key for the SDLC pipeline |
| 050_documents_source_path.sql | Slice 5d: add source_path to ds_documents for idempotent memory ingest |
| 051_work_order_block.sql | Migration 051: Add block_reason column and extend ds_work_orders.status to include 'blocked' |
| 052_invocation_mode.sql | Migration 052: Add invocation_mode column to canonical_events |
| 053_design_brief.sql | Migration 053: Design brief persistence for UI work orders (Slice 7a) |
| 054_ui_gate_update.sql | Migration 054: Add anti_slop_passed to post_build_gate for UI work order types (Slice 7c) |
| 055_technology_signals.sql | Migration 055: Technology signals table for session intelligence harvest (Slice 8c) |
| 056_milestone_order_index.sql | (no leading comment) |
| 057_work_order_type_extensions.sql | Slice 8c: extend ds_work_order_types with workflow routing and gate resolution |
| 058_ta0b_domain_field_validation.sql | Migration 058: TA0b — Domain field validation requirement |
| 059_ta0b_execution_events_projection_link.sql | Migration 059: TA0b — Add projection link column to execution_events |
| 060_ta0b_backfill_execution_events_from_canonical.sql | Migration 060: TA0b — Backfill domain field and execution_events projection |
| 061_backfill_sdlc_creation_events.sql | TA0: Backfill SDLC entity creation events |
| 062_nullify_activity_id_backfill_and_replace_views.sql | Migration 062: Nullify activity_id FKs, backfill activity_log → canonical_events |
| 063_drop_activity_log.sql | Migration 063: Drop activity_log table |
| 064_backfill_task_creation_events.sql | TA1: Backfill task.created events |

*Note: Files 011, 035, 036 are absent from the directory (gaps in sequence).*

---

## 8. API Endpoints

*FastAPI app: projections/api/main.py*
*Total routes: 141*

### GET Routes by Prefix

**Root / dashboard**
- GET / -> root
- GET /dashboard -> dashboard
- GET /frontend/{file_path:path} -> frontend_assets

**Discovery**
- GET /api/discovery/external/health -> health_check
- POST /api/discovery/external/tools -> search_external_tools
- GET /api/discovery/external/tools/{tool_id} -> get_tool_details
- GET /api/discovery/internal/communities/{project_id} -> detect_communities
- GET /api/discovery/internal/components/{project_id} -> list_components
- GET /api/discovery/internal/cycles/{project_id} -> detect_cycles
- GET /api/discovery/internal/graph/{project_id} -> get_dependency_graph
- GET /api/discovery/internal/impact/{component_id} -> analyze_component_impact
- GET /api/discovery/internal/stats/{project_id} -> get_project_stats
- POST /api/discovery/research -> trigger_research
- GET /api/discovery/research -> get_cached_research_by_topic
- GET /api/discovery/research/{cache_id} -> get_cached_research_by_id
- DELETE /api/discovery/research/{cache_id} -> invalidate_cached_research

**Health / OpenAPI**
- GET /api/health -> health_check
- GET /api/docs -> swagger_ui_html
- GET /api/openapi.json -> openapi
- GET /api/redoc -> redoc_html
- GET /docs/oauth2-redirect -> swagger_ui_redirect

**PRD**
- GET /api/prd/list -> list_prds
- GET /api/prd/{prd_id} -> get_prd
- GET /api/prd/{prd_id}/handoffs -> get_prd_handoffs
- GET /api/prd/{prd_id}/progress -> get_prd_progress
- GET /api/prd/{prd_id}/waves/ready -> get_prd_ready_waves

**Shared Intelligence** (22 routes)
- GET /api/shared-intelligence/adapter-router -> get_adapter_router_status
- GET /api/shared-intelligence/adapters/projections -> get_adapter_projection_report
- GET /api/shared-intelligence/adapters/staleness -> get_adapter_staleness_report
- GET /api/shared-intelligence/agents/context-packet -> preview_scoped_agent_context_packet
- GET /api/shared-intelligence/agents/registry -> get_scoped_agent_registry
- GET /api/shared-intelligence/ai-usage-accounting -> get_ai_usage_accounting
- GET /api/shared-intelligence/analytics-only -> get_analytics_only_status
- GET /api/shared-intelligence/capability-center -> get_capability_center
- GET /api/shared-intelligence/capability-routes -> get_capability_routes
- GET /api/shared-intelligence/capability-routes/recommendation -> preview_capability_route
- GET /api/shared-intelligence/career-ops -> get_career_ops_status
- GET /api/shared-intelligence/context-packets/{adapter_id} -> preview_context_packet
- GET /api/shared-intelligence/contract-atlas -> get_contract_atlas
- GET /api/shared-intelligence/contract-atlas/docs-drift -> get_contract_atlas_docs_drift
- GET /api/shared-intelligence/contract-atlas/freshness -> get_contract_atlas_freshness
- GET /api/shared-intelligence/contract-atlas/maturity-ledger -> get_contract_atlas_maturity_ledger
- GET /api/shared-intelligence/expert-workflows -> get_expert_workflow_catalog
- GET /api/shared-intelligence/github-repo-intake -> get_github_repo_intake
- GET /api/shared-intelligence/learning-dashboard -> get_learning_dashboard
- GET /api/shared-intelligence/model-providers -> get_model_provider_summary
- GET /api/shared-intelligence/model-providers/capability-matrix -> get_model_provider_capability_matrix
- GET /api/shared-intelligence/module-contracts -> get_module_contracts
- GET /api/shared-intelligence/platform-hardening -> get_platform_hardening
- GET /api/shared-intelligence/platform-hardening/connectors -> get_connector_ingestion_framework
- GET /api/shared-intelligence/platform-hardening/demo -> get_demo_case_study_system_status
- GET /api/shared-intelligence/platform-hardening/installer -> get_installer_distribution_status
- GET /api/shared-intelligence/platform-hardening/policy-decision -> preview_policy_decision
- GET /api/shared-intelligence/platform-hardening/privacy -> get_privacy_redaction_status
- GET /api/shared-intelligence/platform-hardening/skill-evaluations -> get_skill_evaluation_harness
- GET /api/shared-intelligence/platform-hardening/team-rollup -> get_team_pilot_rollup_status
- GET /api/shared-intelligence/platform-hardening/watchers -> get_local_watch_scheduler_status
- GET /api/shared-intelligence/prd-authority -> get_prd_authority_lifecycle
- GET /api/shared-intelligence/production-readiness -> get_production_readiness_status
- GET /api/shared-intelligence/production-readiness/controls -> get_production_readiness_controls
- GET /api/shared-intelligence/security-lifecycle -> get_security_lifecycle_status
- GET /api/shared-intelligence/status -> get_shared_intelligence_status
- GET /api/shared-intelligence/task-attribution -> get_task_attribution
- GET /api/shared-intelligence/task-attribution/work-orders/{work_order_id} -> get_work_order_task_attribution

**Telemetry** (12 routes)
- GET /api/telemetry/attention -> get_dashboard_attention
- GET /api/telemetry/components -> get_component_usage
- GET /api/telemetry/components/{component_type}/{component_id} -> get_component_telemetry
- GET /api/telemetry/milestones/{milestone_id} -> get_milestone_telemetry
- GET /api/telemetry/modules -> get_telemetry_modules
- GET /api/telemetry/process-runs/{process_run_id} -> get_process_run_telemetry
- GET /api/telemetry/projects -> list_telemetry_projects
- GET /api/telemetry/projects/{project_id} -> get_project_telemetry
- GET /api/telemetry/status -> get_dashboard_data_status
- GET /api/telemetry/summary -> get_telemetry_summary
- GET /api/telemetry/tasks/{task_id} -> get_task_telemetry

**v1 Alerts** (9 routes)
- GET /api/v1/alerts/analytics, GET /api/v1/alerts/history, GET /api/v1/alerts/rules, POST /api/v1/alerts/rules, PUT /api/v1/alerts/rules/{rule_id}, DELETE /api/v1/alerts/rules/{rule_id}, GET /api/v1/alerts/sla

**v1 Analytics**: GET /api/v1/analytics/anomalies, /trends, /performance

**v1 Audits**: GET /api/v1/audits/runs, POST /api/v1/audits/runs, GET /api/v1/audits/runs/{audit_id}, GET /api/v1/audits/findings/{audit_id}, GET /api/v1/audits/stats

**v1 Exports**: POST /api/v1/export/, GET /api/v1/export/csv, GET /api/v1/export/excel/{report_id}, GET /api/v1/export/pdf/{report_id}, GET /api/v1/export/powerbi, GET /api/v1/export/pptx/{report_id}, GET /api/v1/export/{export_id}, DELETE /api/v1/export/{export_id}, GET /api/v1/export/{export_id}/download

**v1 Hooks**: GET /api/v1/hooks/anomalies, /executions, /executions/{exec_id}, /findings, /performance, /stats

**v1 Insights**: GET /api/v1/insights/ (and 9 sub-routes)

**v1 Intelligence**: GET /api/v1/intelligence/agent-capabilities, /architecture, /overview, /system-controls, /token-intelligence

**v1 Metrics**: GET /api/v1/metrics/ (and 6 sub-routes)

**v1 ML**: GET /api/v1/ml/api/v1/ml/benchmarks, /clustering, /evaluation, /forecast/sessions, /forecast/tokens, /patterns, /recommendations, /status

**v1 Projects**: GET /api/v1/projects, GET /api/v1/projects/analysis-runs/{run_id}, and 7 project-scoped sub-routes

**v1 Reports**: GET /api/v1/reports, POST /api/v1/reports/generate, GET /api/v1/reports/{report_id}, DELETE /api/v1/reports/{report_id}

**v1 Schedules**: CRUD for /api/v1/schedules and pause/resume sub-routes

**v1 Security**: GET /api/v1/security/cve, /findings, /reviews, /sarif, POST /api/v1/security/sarif/import, GET /api/v1/security/stats

**v1 Realtime**: POST /api/v1/broadcast/hook-execution, GET /api/v1/connection-stats

---

## 9. Adapters

### Adapter Directories

**canonical/adapters/**
- claude/ — statusline.py

**core/adapters/**
- models.py, normalizers.py, __init__.py

**adapter-projections/** (7 adapter targets)

| Directory | File |
|-----------|------|
| chatgpt/ | context_packet.md |
| claude/ | CLAUDE.md |
| codex/ | AGENTS.md |
| copilot/ | instructions.md |
| cursor/ | rules |
| local-model/ | context_packet.md |
| mcp/ | server-policy.json |
| shell/ | command-policy.json |

_SUPERSEDED.md present at adapter-projections root.

### Adapter-Related Python Modules

- core/adapters/models.py — adapter data models
- core/adapters/normalizers.py — adapter result normalizers
- integrations/compiler/claude_code.py — Claude Code compiler
- integrations/installer/claude_code.py — Claude Code installer
- integrations/targets/claude_code/ — hooks_template.json, settings_merge.py

---

## 10. Workflows

### canonical/workflows/ (23 YAML files)

- audit-to-fix.yaml
- client-deliverable.yaml
- comprehensive-review.yaml
- daily-close.yaml
- daily-standup.yaml
- domain-ingest.yaml
- domain-refresh.yaml
- feature-research.yaml
- fix-issue.yaml
- game-feature.yaml
- hotfix.yaml
- idea-to-pr.yaml
- optimize.yaml
- pre-push.yaml
- production-readiness.yaml
- project-audit.yaml
- prototype.yaml
- safe-refactor.yaml
- security-audit.yaml
- self-audit.yaml
- studio-analytics.yaml
- studio-onboard.yaml
- ui-feature.yaml

### .claude/workflows/ (22 YAML files — same set minus pre-push.yaml)

Identical to canonical/workflows/ except pre-push.yaml is absent.

### .github/workflows/ (4 CI YAML files)

- ci.yml
- full-ci.yml
- release-validation.yml
- validate-skills.yml

### Database: Workflow Tables with Data

| Table | Rows | Notes |
|-------|------|-------|
| raw_workflow_runs | 2 | 1 aborted, 1 completed (both studio-onboard) |
| raw_workflow_nodes | 25 | Nodes from the 2 studio-onboard runs |
| workflow_invocations | 2 | Links to the 2 studio-onboard workflow runs |
| reg_workflows | 0 | Registry not populated |

---

## 11. Configuration

### core/config/ Files

- database.py
- paths.py
- platform.py
- sqlite_bootstrap.py
- state.py
- __init__.py

### projections/config/ Files

- settings.py
- test_settings.py
- __init__.py

### projections/core/config/

- runtime_paths.py

### .env / config.yaml / settings.yaml Files

None found at repo root. All config.yml files are skill configuration files (not system env config).

### Environment Variables Referenced

| Variable | File | Usage |
|----------|------|-------|
| CLAUDE_PLUGIN_ROOT | core/config/paths.py:27 | Locates plugin root for hook dispatch |
| DREAM_STUDIO_HOME | core/config/paths.py:62 | Overrides default home directory (~/.dream-studio) |
| DS_PLATFORM_PROFILE_PATH | core/config/platform.py:21 | Platform profile override |

---

## 12. Documentation

### docs/ Structure (149 files total)

**Top-level .md files (30)**

- ARCHITECTURE.md — # Dream Studio Detailed Architecture
- client-profile-schema.md — # Client Profile Schema
- copilot-setup.md — # GitHub Copilot Setup — dream-studio Conventions
- coverage-report-phase6.md — # Code Coverage Report - Phase 6
- cursor-setup.md — # Cursor Setup — dream-studio Conventions
- DATABASE.md — # Database Guide
- DECISION_QUERY_EXAMPLES.md — # Decision Query Layer — Usage Examples
- demo-disaster-prevention-scenario.md — # Demo: Preventing An AI Workflow Disaster
- demo-script.md — # Demo Video Script: Idea to PR in dream-studio
- design-skills-guide.md — # Design Skills Guide
- HOOK_RUNTIME.md — # Hook Runtime Authority
- MIGRATION_AUTHORITY.md — # Migration Authority
- operator-guide.md — # Dream Studio Operator Guide
- portfolio-case-study.md — # Dream Studio Portfolio Case Study Package
- PUBLICATION_BOUNDARY.md — # Publication Boundary
- quickstart.md — # Quick Start
- README.md — # Dream Studio Documentation
- RUNTIME_RELIABILITY_GATE.md — # Runtime Reliability Gate
- security-best-practices.md — # Security Skills Best Practices
- security-orchestration-pattern.md — # Security Skills Orchestration Pattern
- security-skills-redundancy-analysis.md — # Security Skills Redundancy Analysis
- security-storage-layout.md — # Security Storage Layout
- token-efficient-prompting.md — # Token-Efficient Prompting Guide
- token-overhead.md — # Token Overhead
- token-reduction-summary.md — # Token Reduction Summary
- TRANSACTION_SAFETY_GUIDE.md — # Transaction Safety Migration Guide
- UAT-Phase6-Checklist.md — # UAT Checklist - Phase 6 Discovery System
- UPGRADE_PLAN.md — # Design Skill Upgrade Plan
- WORKFLOWS.md — # Workflow Guide
- WORKFLOW_RUNTIME.md — # Workflow Runtime Authority

**docs/architecture/ (9 files)**
**docs/authoring/ (1 file)** — skills.md
**docs/canonical/ (2 files)** — canonical_event_v1_schema.json, event_taxonomy_v1.json
**docs/contracts/ (30 files)** — full contract library
**docs/demo/sanitized/ (5 files)**
**docs/operations/ (21 files)**
**docs/pilot/company-internal-pilot/ (5 files)**
**docs/product/ (7 files)**
**docs/publication/ (10 files)**
**docs/schema/ (1 file)** — README.md
**docs/setup/ (1 file)** — claude-code-hooks.md

### docs/audits/ (Prior Audits)

*This audit creates docs/audits/2026-05-22-full-stock/*

Prior audit directories: none found. The existing .audit/ directory at repo root contains the prior audit files (not under docs/audits/).

### Contract Documents

30 contract .md files in docs/contracts/. See docs listing above.

---

## 13. Tools

*Location: tools/*
*10 files total (all prefixed with task-attribution workstream IDs)*

| File | Size (bytes) | Type |
|------|-------------|------|
| _ta0c_activity_log_inventory.md | 17,114 | Markdown report |
| _ta0c_cleanup_dirty_state.py | 2,576 | Python script |
| _ta0c_view_audit-2026-05-22.md | 19,614 | Markdown report |
| _ta3_marker_file_investigation.md | 4,456 | Markdown report |
| _ta3_simulate_post_tool_use.py | 5,407 | Python script |
| _ta4_hardcoded_project_id_inventory.md | 4,456 | Markdown report |
| _ta5_fabricator_inventory.md | 3,664 | Markdown report |
| _ta5_reg_projects_finding.md | 1,489 | Markdown report |
| _ta5_sessions_endpoint_bug.md | 1,942 | Markdown report |
| _ta6_verification_plan.md | 11,154 | Markdown report |

---

## 14. Tests

### File Count by Directory

| Directory | File Count |
|-----------|-----------|
| tests/ (root) | 12 |
| tests/core/ | 1 |
| tests/evals/ | 8 |
| tests/integration/ | 36 |
| tests/integration/emitters/ | 2 |
| tests/integration/integrations/ | 5 |
| tests/integration/spool/ | 9 |
| tests/runtime_verification/ | 1 |
| tests/unit/ | 240 |
| tests/unit/canonical/ | 8 |
| tests/unit/emitters/ | 4 |
| tests/unit/gates/ | 5 |
| tests/unit/health/ | 2 |
| tests/unit/hooks/ | 3 |
| tests/unit/integrations/ | 12 |
| tests/unit/spool/ | 6 |
| tests/validation/ | 4 |
| **Total** | **358 .py files** |

### conftest.py Files

- tests/conftest.py (only one found)

### Fixtures in tests/conftest.py

| Fixture | Name |
|---------|------|
| (helper) | _find_handler |
| (helper) | load_handler |
| (pytest hook) | pytest_configure |
| (fixture) | handler |
| (fixture) | isolated_home |
| (fixture) | reset_warnings |
| (fixture) | spool_root |
| (fixture) | ds_home |
| (fixture) | guard_real_homedir |

---

## 15. Discovered Categories

### 15a. Guardrails

*Location: guardrails/*
*20 files total*

- guardrails/rules/quality.yaml — quality guardrail rules
- guardrails/rules/security.yaml — security guardrail rules
- guardrails/scanners/giskard_scanner.py — Giskard scanner integration
- guardrails/scanners/llm_guard_scorer.py — LLM Guard scorer
- guardrails/scanners/rebuff_validator.py — Rebuff validator
- guardrails/enforcement.py — enforcement engine
- guardrails/evaluator.py — evaluator
- guardrails/loader.py — rule loader
- guardrails/models.py — data models

### 15b. Emitters

*Location: emitters/*
*16 files total*

- emitters/claude_code/emitter.py, project.py, run.py, session.py
- emitters/shared/spool_writer.py
- canonical/events/envelope.py, redactor.py, types.py — canonical event types

### 15c. Spool

*Location: spool/*
*12 files total*

- spool/config.py, ingestor.py, session_harvester.py, states.py, writer.py, __init__.py

### 15d. Projections (Dashboard Layer)

*Location: projections/*
*209 files — full analytics/reporting/API layer*

Sub-directories: api/, config/, core/, exporters/, frontend/, generators/, graph/, models/, parsers/, scoring/, tests/

### 15e. Integrations (Installer Layer)

*Location: integrations/*
*27 files — adapter detection, installation, health*

Sub-directories: compiler/, installer/, targets/

### 15f. Control (Orchestration Engine)

*Location: control/*
*109 files — workflow runner, skill router, dispatch, session management*

Sub-directories: analysis/, context/, execution/, research/, review/, session/, skills/

### 15g. Shared

*Location: shared/*
*24 files*

- shared/repo_analysis/ — formatters/, pattern_extractors/, analyzer.py, cli.py
- shared/mcp-integrations/ — agent-browser docs and test scripts
- shared/config.py, paths.py, version-detection.sh

### 15h. Packs

*Location: packs/*
*37 files — pack-level context, agents, rules, templates*

Sub-directories: analyze/hooks/, career/hooks/, core/agents/, core/context/, domains/agents/, domains/domain_lib/, domains/rules/, domains/templates/, quality/rules/

### 15i. Templates

*Location: templates/*
*34 files — security scan templates, GitHub Actions templates, ETL scripts*

Sub-directories: security/binary/, security/compliance/, security/dast/, security/etl/, security/github-actions/, security/mitigations/, security/powerbi/, security/semgrep-rules/

Also: templates/traceability-registry.yaml

### 15j. Scripts (Utility Scripts at Repo Root)

*Location: scripts/*
*14 files — operational and diagnostic scripts*

- backfill_components.py
- benchmark_tokens.py
- common.py
- dashboard_smoke_harness.py
- dev.ps1
- docker_runtime_check.py — #!/usr/bin/env python3
- ds_dashboard.py — DUPLICATE: Canonical location is interfaces/cli/ds_dashboard.py
- lesson_queue.py
- requeue_failed.py — #!/usr/bin/env python3
- runtime_state_hash_guard.py — #!/usr/bin/env python3
- setup.py

### 15k. Hooks (Repo Root, Git Hooks)

*Location: hooks/ (repo root, not runtime/hooks/)*
*5 files*

- hooks/git/pre-push — git pre-push hook script
- hooks/hooks.json — hook configuration JSON
- hooks/on-commit.py — commit hook
- hooks/run.cmd — Windows runner
- hooks/run.sh — shell runner

### 15l. Examples

*Location: examples/*
*1 file*

- examples/adapter_usage_example.py

### 15m. Adapter Projections (Canonical Projections per AI Tool)

*Location: adapter-projections/*
*Covered in Section 9 above*

### 15n. .planning/ (Local Planning Files, Gitignored)

*49 files — slice completion records, work order contexts, workflow planning outputs*

Not committed to repo. Contains: Slice-1.md through slice-9e-writeup.md, work-order context.md files per WO ID, architectural planning documents.

---

*End of inventory*
