# Operational State Contract

Phase: 7B - Operational State Contract

Dream Studio is a local-first, AI-agnostic, federated operational intelligence platform for AI-assisted work. The operational state contract defines which local state surfaces are authoritative, derived, advisory, or diagnostic so later projections and adapters can build on them without moving authority into dashboards, telemetry, cloud services, or model/provider-specific layers.

## Authority Principles

1. Local canonical runtime state is authoritative.
2. Dashboards and API read routes consume projections or explicit local state.
3. Telemetry observes behavior and may inform decisions; it does not replace orchestration truth.
4. Adapters execute work and normalize outputs through explicit contracts; they do not own operational state.
5. Future cloud/org/global layers may aggregate selected projections only.
6. State authority changes require an explicit contract update and, when persisted shape changes, a versioned migration.

## State Classes

- Canonical: the local source of truth for a state category.
- Derived: rebuildable state created from canonical state or events.
- Advisory: useful evidence that may guide humans or policies but cannot force state transitions alone.
- Diagnostic: debug, monitoring, validation, or performance evidence.
- Transient: local working state that may be archived to canonical tables at lifecycle boundaries.

## Ownership Matrix

| Category | Canonical owner | Canonical tables/files | Derived surfaces | Advisory/diagnostic surfaces | Rule |
| --- | --- | --- | --- | --- | --- |
| workflow state | `control.execution.workflow.state` for active workflows; `core.event_store.studio_db.archive_workflow` for archive | `~/.dream-studio/state/workflows.json`, `~/.dream-studio/state/workflow-checkpoint.json`, `raw_workflow_runs`, `raw_workflow_nodes`, `pi_waves`, `pi_wave_tasks`, `reg_workflows` | `proj_workflow_runs`, `workflow_executions`, `workflow_phases`, `workflow_kpis`, `phase_kpis`, SQL workflow views | workflow cost estimates and readiness calculations | Active workflow JSON is transient runtime state. Terminal workflow state is archived locally; projections are rebuildable summaries. |
| orchestration state | `core.execution.graph.ExecutionGraphManager` and PRD/session writers in `core.event_store.studio_db` | `execution_nodes`, `execution_dependencies`, `execution_outputs`, `execution_event_links`, `prd_documents`, `prd_plans`, `prd_tasks`, `prd_sessions`, `session_tasks`, `raw_specs`, `raw_tasks` | `v_active_execution`, `v_blocked_nodes`, `v_completion_rate`, PRD views | context compiler outputs and repo snapshots | The execution graph owns durable DAG status. Context bundles and projection views do not mutate orchestration truth. |
| execution state | `core.event_store.studio_db` write helpers and explicit execution managers | `activity_log`, `hook_executions`, `hook_findings`, `audit_runs` | hook performance views, activity timeline views, dashboard/API summaries | validation failures, hook stdout/stderr, adapter metadata | `activity_log` is a legacy operational hub and compatibility surface; canonical events remain governed by the event contract. |
| decision lineage | `core.decisions.emitter.emit_decision` | `decision_log`, `decision_event_link` | `proj_decision_patterns`, decision query APIs, coverage reports | decision integrity reports and audit summaries | Decision reasoning/outcome belongs in `decision_log`; causal linkage to events belongs in `decision_event_link`. |
| governance state | governance and security write helpers plus explicit audit/risk endpoints | `audit_runs`, `guardrail_decisions`, `sec_sarif_findings`, `sec_manual_reviews`, `sec_cve_matches` | `vw_security_summary`, `vw_guardrail_decisions`, security API summaries | compliance scores, trend views, rule-load audit rows | Governance records may be written by explicit local governance APIs. Dashboards do not become governance authority by displaying them. |
| telemetry state | local telemetry writers and session hooks | `raw_skill_telemetry`, `raw_token_usage`, `raw_pulse_snapshots`, `raw_operational_snapshots`, local telemetry JSONL buffers | `effective_skill_runs`, `sum_skill_summary`, analytics views, metrics API responses | raw metrics, token logs, pulse snapshots | Telemetry is observational. It can support reports and advisory decisions, but cannot overwrite workflow, execution, or decision state directly. |
| memory/continuity state | `core.memory.store.MemoryStore` and session/handoff writers in `core.event_store.studio_db` | `memory_entries`, `raw_sessions`, `raw_handoffs`, `prd_handoffs`, `raw_lessons`, `reg_gotchas` | `memory_fts`, file-memory FTS indexes, continuity summaries | `research_cache`, `raw_research`, research trust scores, session parsing outputs | `memory_entries` is canonical semantic memory. Retrieval indexes and research caches are rebuildable or advisory. |

## Duplicate And Ambiguous State

These surfaces intentionally overlap and must remain classified:

- `canonical_events` and `activity_log`: canonical events are the append-only event ledger. `activity_log` is legacy operational hub state and cross-domain linkage, not event authority.
- `workflows.json`, `raw_workflow_runs`, and `execution_nodes`: active CLI workflow state lives in JSON; terminal workflow archives live in `raw_workflow_*`; durable cross-phase DAG state lives in `execution_nodes`.
- `raw_sessions` and `prd_sessions`: `raw_sessions` tracks generic session continuity; `prd_sessions` tracks PRD-scoped work sessions.
- `raw_handoffs` and `prd_handoffs`: `raw_handoffs` is session-wide continuity; `prd_handoffs` is PRD-specific continuity derived at handoff time.
- `decision_log` and `decision.*` canonical events: `decision_log` owns structured reasoning and outcome; canonical events own event chronology; `decision_event_link` records causality.
- `raw_skill_telemetry` and `activity_log`: telemetry records usage observations; `activity_log` records normalized operational activity.
- `memory_entries`, `memory_fts`, and `control.research.memory` indexes: `memory_entries` is canonical semantic memory; FTS tables and file-memory indexes are rebuildable retrieval surfaces.
- `research_cache` and `raw_research`: research outputs are evidence and cache state. They do not become decision, memory, or execution authority until ingested through the owning contract.

Ambiguity resolution rule: when two state surfaces disagree, the owner listed in the matrix wins for that category. Derived/advisory/diagnostic surfaces must be rebuilt, invalidated, or re-ingested rather than promoted silently.

## Read-Only Projection Rules

Projection code may write only projection-owned tables and projection checkpoints:

- `proj_*`
- `workflow_executions`
- `workflow_phases`
- `workflow_kpis`
- `phase_kpis`
- `projection_checkpoints`
- `consumer_state`

Projection code must not write canonical operational tables such as `raw_sessions`, `raw_workflow_runs`, `execution_nodes`, `decision_log`, `memory_entries`, `activity_log`, `hook_executions`, or `canonical_events`.

API routes under `projections/api/routes` are read-first surfaces. Existing explicit local write exceptions are:

- `audits.py`: creates `audit_runs` records through the audit API.
- `discovery_research.py`: invalidates advisory `research_cache` records.

No other API route may mutate operational state without an explicit contract update and tests.

## Adapter Boundary Rules

Adapters may:

- Normalize provider/model/tool output.
- Return adapter metadata.
- Participate in explicit emit/consume contracts.

Adapters must not:

- Open Dream Studio state databases directly.
- Insert, update, or delete authoritative local state tables.
- Make model/provider metadata authoritative over local execution, decision, or memory state.
- Require a specific vendor for core state transitions.

## Telemetry Boundary Rules

Telemetry can be used for analytics, health checks, trend reports, and advisory confidence. Telemetry cannot directly:

- Mark workflow nodes complete or failed.
- Rewrite execution graph state.
- Change decision outcomes.
- Promote memory lifecycle state.
- Override governance/risk status.

If telemetry informs one of those transitions, the owning core module must make the transition and record the decision or event through its contract.

## Replay And Rebuild Expectations

- Derived projection tables must be rebuildable from canonical events or canonical operational state.
- FTS indexes must be rebuildable from their owning canonical tables.
- Advisory caches may be invalidated without data loss to canonical state.
- Diagnostic records may be pruned or summarized, but not treated as replacement authority.
- State exports must preserve each record's classification so imports cannot silently promote derived/advisory/diagnostic data to canonical state.

## Schema Posture

Phase 7B does not require schema changes. If later work needs to consolidate duplicate state surfaces, it must use a targeted migration with dual-read compatibility and a contract update that names the new owner.
