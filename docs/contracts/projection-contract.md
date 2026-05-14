# Projection Contract

Phase: 7C - Projection Contract

Dream Studio is a local-first, AI-agnostic, federated operational intelligence platform for AI-assisted work. The projection contract keeps dashboards, API routes, exporters, analytics views, and projection workers in their proper role: derived consumers of local authority, not hidden owners of canonical runtime truth.

## Authority Principles

1. Projections are derived unless a later contract explicitly designates a projection-owned service state table.
2. Rebuildable projections must be rebuildable from canonical events, canonical operational state, local source artifacts, or explicit advisory sources.
3. Projection metadata may track cursors, checkpoints, schedules, or alert rules, but metadata does not become canonical workflow, execution, decision, governance, telemetry, or memory state.
4. Dashboards consume projections or explicit local state through APIs. Dashboards do not write canonical runtime truth.
5. API routes may expose projections and may own explicitly classified local service state. They must not silently become canonical state writers.
6. Exported projections are snapshots. Re-importing an export must not promote it to authority without a future import contract.

## Projection Classes

- Rebuildable projection: table, view, index, file, or response rebuilt from canonical events or canonical operational state.
- Projection metadata: cursor, checkpoint, alert/schedule configuration, or service-local bookkeeping needed to run a projection service.
- Advisory projection: cache, recommendation, forecast, trend, alert, or score that may guide action but cannot force canonical transitions alone.
- Governance ingestion exception: explicit local API or parser path that writes governance/security records. These writes are not dashboard authority and must remain named.
- Authority violation: any dashboard/API/projection path that mutates canonical runtime state without being listed in this contract and the state contract.

## Table Ownership Matrix

| Table or view | Writer/owner | Source | Class | Rebuild expectation | Boundary |
| --- | --- | --- | --- | --- | --- |
| `projection_checkpoints` | `core.projections.framework.ProjectionEngine` | projection engine progress | projection metadata | Recreated by projection engine | Cursor only; never canonical state. |
| `consumer_state` | `core.projections.workflow_consumer.WorkflowEventConsumer` | workflow consumer progress | projection metadata | Recreated by consumer | Cursor only; never canonical state. |
| `proj_workflow_runs` | `core.projections.consumers.WorkflowProjection` | `canonical_events` workflow events | rebuildable projection | Rebuild from event stream | Derived workflow summary only. |
| `proj_skill_stats` | `core.projections.consumers.SkillRoutingProjection` | `canonical_events` skill events | rebuildable projection | Rebuild from event stream | Derived skill summary only. |
| `proj_sessions` | `core.projections.consumers.SessionProjection` | `canonical_events` session events | rebuildable projection | Rebuild from event stream | Derived session summary only. |
| `proj_decision_patterns` | `core.projections.consumers.DecisionProjection` | `canonical_events` decision events | rebuildable projection | Rebuild from event stream | Does not replace `decision_log`. |
| `proj_security_summary` | `core.projections.consumers.SecurityProjection` | `canonical_events` security events | rebuildable projection | Rebuild from event stream | Does not replace security finding tables. |
| `workflow_executions` | `core.projections.workflow_metrics.WorkflowMetricsProjection` | workflow canonical events | rebuildable projection | Rebuild from workflow event history | Existing non-`proj_` projection table. |
| `workflow_phases` | `core.projections.workflow_metrics.WorkflowMetricsProjection` | workflow phase events | rebuildable projection | Rebuild from workflow event history | Existing non-`proj_` projection table. |
| `workflow_kpis` | `core.projections.workflow_metrics.WorkflowMetricsProjection` | `workflow_executions` | rebuildable projection | Recompute from workflow projection rows | Existing non-`proj_` projection table. |
| `phase_kpis` | `core.projections.workflow_metrics.WorkflowMetricsProjection` | `workflow_phases` | rebuildable projection | Recompute from phase projection rows | Existing non-`proj_` projection table. |
| `memory_fts` | `core.memory.retrieval.FTS5MemoryRetriever` | `memory_entries` | rebuildable projection index | Rebuild from `memory_entries` | Search acceleration only. |
| `pi_components` | `projections.graph.component_extractor` | repository source files | rebuildable project-intelligence projection | Re-run extraction | Does not replace repo or project registry authority. |
| `pi_dependencies` | `projections.graph.component_extractor` | `pi_components` and imports | rebuildable project-intelligence projection | Re-run extraction | Derived dependency graph only. |
| `vw_security_summary` | SQL migration `029_analytics_views.sql` | security finding tables | rebuildable SQL view | Recreate view | Read-only projection view. |
| `vw_activity_timeline` | SQL migration `029_analytics_views.sql` | `activity_log` | rebuildable SQL view | Recreate view | Timeline projection; not event authority. |
| `vw_risk_hotspots` | SQL migration `029_analytics_views.sql` | `sec_sarif_findings` | rebuildable SQL view | Recreate view | Derived risk view. |
| `vw_hook_performance` | SQL migration `029_analytics_views.sql` | `hook_executions` | rebuildable SQL view | Recreate view | Derived hook view. |
| `vw_guardrail_decisions` | SQL migration `029_analytics_views.sql` | guardrail/activity tables | rebuildable SQL view | Recreate view | Derived governance view. |
| `v_active_execution`, `v_blocked_nodes`, `v_completion_rate` | SQL migration `034_execution_graph.sql` | `execution_nodes`, `execution_dependencies` | rebuildable SQL views | Recreate views | Read-only execution graph projections. |
| `alert_rules` | `projections.core.alerts.RuleManager` | operator-defined alert config | projection service state | Persisted service configuration | Advisory alert rules, not canonical runtime truth. |
| `alert_history` | `projections.core.alerts.AlertEvaluator` | evaluated metrics and `alert_rules` | advisory projection history | Recreated only as future alerts fire | Diagnostic/advisory alert evidence. |
| `sla_definitions` | `projections.core.sla.SLATracker` | operator-defined SLA config | projection service state | Persisted service configuration | Advisory SLA rules, not canonical runtime truth. |
| `scheduled_reports` | `projections.core.scheduler.ScheduleStorage` | operator-defined schedule config | projection service state | Persisted service configuration | Report scheduling state only; stored in the canonical local studio DB, not a separate scheduler DB. |
| `research_cache` | `control.research.web` plus `discovery_research.py` advisory writes | web/research results | advisory cache | May expire or be invalidated | API-triggered cache writes suppress canonical event emission so dashboard/API cache mutation does not become hidden event authority. |
| `audit_runs` | `projections.api.routes.audits` | explicit audit API requests | governance ingestion exception | Persisted governance record | Local audit API write, not dashboard projection authority. |
| `sec_sarif_findings` | `projections.parsers.sarif_parser` | SARIF files | governance ingestion exception | Re-import from SARIF artifacts when available | Explicit security ingestion, not projection ownership of governance. |
| `activity_log` from `sarif_parser` | `projections.parsers.sarif_parser` | SARIF import activity | governance ingestion exception | Re-import from SARIF artifacts when available | Legacy operational hub write; not canonical event authority. |
| `activity_log` from `RiskScoringEngine` | `projections.scoring.engine` | security activity and findings | advisory enrichment exception | Recompute scores from source findings | Risk score evidence only; telemetry/scoring does not own execution truth. |

## Route Ownership Matrix

| Route group | Reads | Writes | Classification | Boundary |
| --- | --- | --- | --- | --- |
| `analytics.py` | `raw_sessions`, `raw_token_usage` | none | dashboard read API | Derived analytics response only. |
| `metrics.py` | telemetry, session, workflow, lesson tables | none | dashboard read API | Metrics do not mutate telemetry authority. |
| `insights.py` | collectors over raw operational tables | none | advisory read API | Recommendations are advisory. |
| `intelligence.py` | telemetry, hooks, activity, decision tables | none | advisory/read API | Intelligence does not own decisions or telemetry. |
| `hooks.py` | `hook_executions`, `hook_findings`, `activity_log`, `vw_hook_performance` | none | dashboard read API | Hook views do not mutate hook execution state. |
| `security.py` GET routes | security tables and `vw_security_summary` | none | dashboard read API | Security reads do not own governance state. |
| `security.py` SARIF import route | uploaded SARIF file | currently stubbed; parser path writes `activity_log` and `sec_sarif_findings` if enabled | governance ingestion exception | Must remain explicit before parser activation. |
| `audits.py` | `audit_runs`, `activity_log` | `audit_runs` | governance ingestion exception | Explicit local audit write API. |
| `alerts.py` | `alert_rules`, `alert_history`, SLA data | `alert_rules` through `RuleManager`; `sla_definitions` table initialization through `SLATracker` | projection service state | Alert config is advisory projection state. |
| `schedules.py` | `scheduled_reports` | `scheduled_reports` through scheduler storage in the canonical local studio DB | projection service state | Report schedules do not own canonical runtime state or create a separate scheduler authority. |
| `reports.py` | report service memory/store | in-memory report metadata | projection service state | Generated reports are derived artifacts. |
| `exports.py` | export service memory/files | in-memory/file export metadata | projection service state | Exports are snapshots, not upstream authority. |
| `realtime.py` | WebSocket manager memory | in-memory broadcast state | projection service state | Realtime broadcast does not persist canonical state. |
| `prd.py` | PRD/session/handoff tables | none | dashboard read API | PRD API reads local state only. |
| `project_intelligence.py` | `reg_projects`, `pi_*`, PRD/security/activity tables | WebSocket memory only | dashboard read/API projection | Project health is derived from local state. |
| `discovery_internal.py` | `reg_projects`, `pi_components`, `pi_dependencies` | none | dashboard read API | Dependency graph is derived project-intelligence state. |
| `discovery_external.py` | tool registry and external search services | none | advisory discovery API | External discovery does not own local tool registry. |
| `discovery_research.py` | `research_cache`, research service | advisory `research_cache` writes and invalidation with route-level canonical event emission suppressed | advisory cache API | Cache mutation cannot become memory, decision, execution, or hidden canonical event authority. |
| `frontend.py` | dashboard static files | none | frontend surface | Serves assets only. |
| `ml.py` | no local canonical data; enterprise stubs | none | advisory placeholder API | Forecasts/patterns are not canonical state. |

## Write Classification Rules

Projection writes are allowed only when one of these classifications applies:

- Derived rebuildable projection writes: `proj_*`, `workflow_executions`, `workflow_phases`, `workflow_kpis`, `phase_kpis`, `memory_fts`, `pi_components`, `pi_dependencies`, and SQL views.
- Projection metadata writes: `projection_checkpoints`, `consumer_state`, `alert_rules`, `alert_history`, `sla_definitions`, `scheduled_reports`, in-memory report/export/realtime metadata.
- Explicit local governance/API write exceptions: `audit_runs`, SARIF ingestion to `sec_sarif_findings` and `activity_log`, risk-score enrichment to `activity_log`.
- Advisory cache writes: `research_cache` updates and invalidations; projection API route cache writes must not emit canonical events unless a future contract names that event wrapper explicitly.

Any new write from `projections/`, `core/projections/`, or `projections/api/routes/` to canonical operational tables must update this contract and add focused tests before it ships.

## Dashboard Rules

Dashboard HTML and frontend integration scripts must not open the Dream Studio database, import state writers, or emit canonical events. Frontend code may call API endpoints and render derived data. If a dashboard action needs to mutate local state, the mutation must go through an explicitly classified API route with tests and contract coverage.

## Export Rules

Exports must label their output as derived projection snapshots. Exporters may write files requested by the user, but those files do not become local canonical state. If an import path later consumes export files, that path needs its own import contract.

## Rebuild Rules

Rebuildable projections must document their source and be safe to recreate without altering the owner tables listed in the state contract. If a projection cannot be fully rebuilt because it stores operator configuration or history, it must be classified as projection service state or diagnostic/advisory history.

## Violations

Phase 7C found no authority violation requiring schema or production code changes. The existing write surfaces are classified above, with the highest-risk exceptions being API-created `audit_runs`, alert/schedule service state, SARIF/security ingestion, and risk-score enrichment writes to the legacy `activity_log` hub.

## Schema Posture

Phase 7C does not require schema changes. Future projection consolidation, table renaming, or route restructuring must be handled in a targeted phase with migration tests and updated ownership matrices.
