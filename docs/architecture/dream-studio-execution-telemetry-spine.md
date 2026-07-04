# Dream Studio Execution Telemetry Traceability Spine

<!-- Last reviewed 2026-07-04 — migration 139 (WO-AI-SPINE, AD-5): decision_records, outcome_records, and dashboard_attention_items dropped; their writers in core/telemetry/emitters.py already dual-wrote execution_events, so the per-type tables were pure duplication. Dashboard/read-model consumers now derive decisions/outcomes/attention from execution_events filtered by event_type. -->

> **ASPIRATIONAL** — This document describes the intended target state of the telemetry spine. Some referenced tables (`telemetry_entity_registry`, `blocker_resolution_records`, `authority_projection_records`) do not yet exist in the schema. Treat as design intent, not current implementation. (Flagged: WO-P 2026-06-07)

Lifecycle status: draft_generated

Authority role: local-first execution telemetry and orchestration intelligence
contract.

## Product Direction

Dream Studio must trace every meaningful action by project, milestone, task,
process run, agent, skill, workflow, hook, tool, model/provider, token usage,
security finding, file/line, decision, research evidence, validation, artifact,
and outcome.

The dashboard should support drilldown from global views to project, milestone,
task, process run, and exact event/fact records.

## Core Spine

The core tables are:

- `execution_events`
- `process_runs`

(`telemetry_module_registry` and `telemetry_entity_registry` were declared in
the original spine but never carried live data; both were dropped 0-row in Wave 6
/ migration 101. Module declarations are now served in-memory by
`dashboard_module_declarations()`.)

Each module fact table links back to project, milestone, task, process run, and
event where applicable. This keeps the system modular without losing global
analytics.

## Module Fact Tables

The first additive telemetry spine defines:

- `agent_invocations`
- `skill_invocations`
- `workflow_invocations`
- `hook_invocations`
- `tool_invocations`
- `token_usage_records`
- `ai_adapter_accounting_profiles`
- `ai_usage_operational_records`
- `security_findings`
- `decision_records` (dropped migration 139, WO-AI-SPINE — pure duplication of execution_events dual-write)
- `research_evidence_records`
- `blocker_resolution_records`
- `validation_results`
- `artifact_records`
- `outcome_records` (dropped migration 139, WO-AI-SPINE — pure duplication of execution_events dual-write)
- `route_decision_records`
- `dashboard_attention_items` (dropped migration 139, WO-AI-SPINE — pure duplication of execution_events dual-write)
- `authority_projection_records`

## Dashboard Modules

Dashboard modules can be enabled independently:

- security analytics
- token analytics
- agent analytics
- skill analytics
- workflow analytics
- hook analytics
- research/decision analytics
- validation analytics
- artifact analytics
- route/milestone analytics

Each module declares source tables, required core tables, optional tables,
dashboard cards, drilldown paths, validation requirements, and empty-state
behavior when disabled or empty.

Token analytics report usage and operational value, not fake billing. Plan
adapters such as Claude Code subscription and Codex via ChatGPT plan can record
observed tokens or run outcomes while showing cost as unknown. Token-metered or
API-metered adapters may report exact/provider-reported cost only when the
source metadata, export, or billing API evidence exists.

Dashboard projections remain derived views and not primary truth.

## Docker Boundary

Docker is a pluggable runtime and repeatability layer. It can isolate scanners,
workers, adapters, dashboard/API profiles, and validation sandboxes when
explicitly enabled. Dream Studio core must work without Docker, and Docker must
not replace local-first SQLite authority.

## Research And Blocker Routing

Research/blocker routing classes:

- `no_blocker_continue`
- `local_evidence_resolved_continue`
- `concrete_research_resolved_continue`
- `concrete_research_requires_dashboard_approval`
- `true_unknown_prompt_required`
- `unsafe_hard_stop`
- `team_or_department_decision_prompt_required`

High-confidence, sufficient, low-risk research can be recorded and continued.
Material-risk research can create dashboard approval items when safe work can
pause or route around the issue. Low-confidence, conflicting, sensitive, or
split-ownership blockers require prompt-required state.

## Additive Migration

The schema is introduced by:

`core/event_store/migrations/037_execution_telemetry_traceability_spine.sql`

The migration is additive only. It creates tables and indexes with
`CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS`; it does not drop
tables, delete records, or overwrite authority.
