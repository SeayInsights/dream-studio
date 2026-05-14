# Dream Studio Execution Telemetry Traceability Spine

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
- `telemetry_module_registry`
- `telemetry_entity_registry`

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
- `security_findings`
- `decision_records`
- `research_evidence_records`
- `blocker_resolution_records`
- `validation_results`
- `artifact_records`
- `outcome_records`
- `route_decision_records`
- `dashboard_attention_items`
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
