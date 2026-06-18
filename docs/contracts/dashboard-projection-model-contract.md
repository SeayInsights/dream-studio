# Dashboard Projection Model Contract

## Purpose

This contract defines documentation/data shapes for dashboard projections over Work Orders, evals, reports, handoffs, approvals, operator decisions, and Security Review artifacts.

Dashboard projections are read-only views over file-backed artifacts. They are not authority. Work Orders, reports, approvals, operator decisions, eval artifacts, Handoff Packets, and Security Review artifacts remain the source of truth.

This contract does not implement a dashboard UI, dashboard API, runtime projection builder, database table, event ledger, schema migration, scan runner, profile registry, target repo access, Docker expansion, or TORII/cloud/org/global/enterprise integration.

## Projection Artifact Roles

| Artifact | Role |
| --- | --- |
| `DashboardProjectionSnapshot` | Top-level read model snapshot for a bounded set of file-backed artifacts. |
| `WorkOrderOverviewProjection` | Work Order status, readiness, verdict, decision, next action, and risk summary. |
| `EvalProjection` | Deterministic eval result summary and evidence refs. |
| `ApprovalOperatorDecisionProjection` | Approval and operator decision state used for gated execution visibility. |
| `SecurityReviewProjection` | Security Review report, release-gate, findings, evidence, accepted-risk, and next Work Order summary. |

## Authority Model

- Projections are read-only views over artifacts.
- Projections must preserve artifact refs so the source evidence can be opened directly.
- Projections must show stale, missing, incomplete, or conflicting evidence.
- Projections must not claim readiness when source artifacts are missing or stale.
- Projections must not run scans.
- Projections must not approve risk.
- Projections must not mutate repos.
- Projections must not stage, commit, push, write target artifacts, install dependencies, update lockfiles, open native runtime databases, write event ledgers, or bypass Work Order approval.
- Projections must not replace Work Order reports, operator decisions, eval artifacts, Security Review reports, or Handoff Packets.
- Projections must not replace operator decisions.
- Projections must not replace Security Review reports.
- Projections must not replace Handoff Packets.

## DashboardProjectionSnapshot

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `projection_id` | yes | Stable projection snapshot identifier. |
| `generated_at` | yes | Timestamp or `unknown` when generated manually. |
| `source_artifact_refs` | yes | File-backed source artifacts used for the projection. |
| `work_orders` | yes | List of `WorkOrderOverviewProjection` items. |
| `evals` | yes | List of `EvalProjection` items. |
| `approvals_and_operator_decisions` | yes | List of `ApprovalOperatorDecisionProjection` items. |
| `security_reviews` | yes | List of `SecurityReviewProjection` items. |
| `stale_or_missing_evidence` | yes | Evidence gaps, stale refs, missing artifacts, and conflict notes. |
| `non_authority_notice` | yes | Statement that the dashboard projection is not authority. |

## WorkOrderOverviewProjection

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `work_order_id` | yes | Work Order identifier. |
| `phase_name` | yes | Phase name from report or handoff evidence. |
| `approval_mode` | yes | Work Order approval mode. |
| `risk_level` | yes | Work Order risk level. |
| `readiness` | yes | Sequential readiness, if known. |
| `verdict` | yes | Latest report verdict, if known. |
| `final_decision` | yes | Latest final decision, if known. |
| `next_action` | yes | Bounded next action or `unknown`. |
| `report_ref` | yes | File-backed report path or `missing`. |
| `handoff_ref` | yes | Handoff Packet path or `missing`. |
| `blocking_risks` | yes | List of blocking risks, missing evidence, or authority conflicts. |

## EvalProjection

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `eval_artifact_ref` | yes | File-backed eval artifact path. |
| `eval_type` | yes | Eval type identifier. |
| `pass_fail` | yes | `pass`, `fail`, `incomplete`, or `unknown`. |
| `score` | yes | Numeric score, label, or `not_applicable`. |
| `evidence_refs` | yes | File-backed evidence refs used by the eval. |
| `blocking` | yes | Boolean indicating whether the eval blocks continuation. |
| `limitations` | yes | Staleness, missing evidence, or scope caveats. |

## ApprovalOperatorDecisionProjection

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `approval_artifact_ref` | yes | Approval artifact path or `not_applicable`. |
| `approval_status` | yes | `present`, `missing`, `not_required`, `stale`, or `invalid`. |
| `operator_decision_ref` | yes | Operator decision artifact path or `not_applicable`. |
| `selected_decision` | yes | Selected operator decision or `none`. |
| `reason_required` | yes | Boolean. |
| `reason_present` | yes | Boolean. |
| `execution_allowed` | yes | Boolean derived from source artifacts; this is display-only and not execution authority. |

## SecurityReviewProjection

Required fields:

| Field | Required | Purpose |
| --- | --- | --- |
| `security_review_report_ref` | yes | File-backed Security Review report path. |
| `target_id` | yes | Target identifier or `not_applicable`. |
| `security_pack_id` | yes | Security Review Profile Pack identifier. |
| `verdict` | yes | Security Review report verdict. |
| `release_gate_decision` | yes | Release-gate decision from the report artifact. |
| `taxonomy_coverage` | yes | Category coverage and gaps. |
| `scan_status_counts` | yes | Counts by scan status. |
| `findings_by_severity` | yes | Counts by severity. |
| `findings_by_release_impact` | yes | Counts by release impact. |
| `blocking_findings` | yes | Blocking finding IDs. |
| `accepted_risks` | yes | Accepted risk IDs and decision refs. |
| `deferred_scans` | yes | Deferred scan IDs and reasons. |
| `evidence_inventory_refs` | yes | Evidence record refs. |
| `next_work_order_recommendation` | yes | Bounded next Work Order recommendation from the security report. |

## Stale And Missing Evidence Behavior

- Missing report refs must be displayed as missing, not inferred.
- Missing approval artifacts must display execution as not allowed.
- Missing operator decisions must display risk acceptance as incomplete.
- Missing eval artifacts must display eval status as `unknown` or `incomplete`.
- Missing Security Review reports must display release-gate state as `HOLD` or `unknown`, not clear.
- Stale source artifacts must display staleness and last-known values separately.
- Conflicting source artifacts must display conflict notes and must not be resolved silently.
- Projection snapshots must preserve source artifact refs for manual review.

## Dashboard Boundary

Dashboard projections may show:

- Work Order posture, readiness, verdict, final decision, and next action.
- Eval result summaries, evidence refs, blocking state, and limitations.
- Approval and operator-decision state.
- Security Review posture, taxonomy coverage, scan summary, findings, evidence inventory, release-gate decisions, accepted risks, deferred scans, and next Work Orders.

Dashboard projections must not:

- run scans;
- approve risk;
- mutate repos;
- stage files;
- commit files;
- push;
- write target artifacts;
- install dependencies;
- update lockfiles;
- open native runtime databases;
- write event ledgers;
- create schema migrations;
- replace Work Order reports;
- replace operator decisions;
- replace Security Review reports;
- replace Handoff Packets.

## Security Projection Source Rules

- Security Review projections must read from `SecurityReviewReport` artifacts, not directly from target repositories.
- Security release-gate decisions must come from `ReleaseGateSummary` or the Security Review report.
- Accepted risks must reference `AcceptedRiskRecord` and file-backed operator decision artifacts.
- Finding counts must come from `SecurityFindingRecord` data or report summaries.
- Evidence inventory refs must point to `SecurityEvidenceRecord` data or external report refs.
- Dashboard projection data must not become remediation authority.

## Validation Expectations

Static checks for this contract should verify:

- required projection shapes and fields are documented;
- dashboard non-authority rules are explicit;
- stale and missing evidence behavior is explicit;
- security projection fields are complete;
- sample projection data remains non-executing and not target-specific;
- no dashboard UI, API, runtime builder, DB/event/schema, target repo, scan execution, Docker, TORII/cloud/org/global/enterprise, dependency, or lockfile authority is introduced.

<!-- reviewed: 2026-06-06, WO-B broken surfaces. projections/api/routes/security.py: wired parse_sarif_file() into POST /security/sarif/import (uncommented import + call, removed stub). The endpoint was already listed in ALLOWED_DASHBOARD_WRITES and validated by test_dashboard_write_like_calls_stay_on_named_api_exceptions. No projection contract shape change; no new dashboard authority introduced. -->

<!-- reviewed: 2026-06-12, WO-C full-CI fixes. core/telemetry/read_models.py: qualified fcs.project_id in _security_remediation_intelligence LEFT JOIN WHERE clause — bug fix for "ambiguous column name" SQLite error; no shape change. core/telemetry/execution_spine.py: record_security_finding now emits a status_changed event when a non-open status is supplied; added "resolved" and "closed" to resolve_security_finding valid_resolutions. Both are correctness fixes with no new projection authority, no new tables, and no contract shape changes. -->

<!-- reviewed: 2026-06-06, WO-D dead discovery route removal. discovery_external.py and discovery_research.py deleted (no live callers). Dead endpoints removed from discovery_internal.py (now only /graph/{project_id}). Dead endpoints removed from prd.py (handoffs, progress, ready-waves). No projection contract shape change; no new dashboard authority introduced. Removal of dead routes reduces the projection surface. -->

<!-- reviewed: 2026-06-06, WO-A telemetry write-path honesty. dashboard_freshness.py: removed raw_token_usage from table_counts (retire path b — zero-token writes stopped at source). legacy_backfill.py: removed raw_token_usage → token_usage_records backfill mapping (source table no longer written). token_usage_records section of dashboard_freshness.py (lines 206-225) already reads from token_usage_records for the legacy_token_metrics section — no change required there. Dashboard projection contract shape unchanged; no new tables, no removed authority paths. -->

<!-- Last reviewed 2026-06-07 — WO-F prd_* cluster drop (migration 103): migration 103 drops the entire prd_* cluster (prd_documents, prd_plans, prd_tasks, prd_sessions, prd_handoffs, session_tasks, prd_version_records, prd_amendment_records, prd_route_reconciliation_records) and the views vw_prd_progress and vw_task_details. AD-10 decision: business_projects IS what PRD was. All prd_* callers removed from studio_db.py, prd_authority.py (deleted), routes/prd.py (deleted), analytics_ingestion.py, module_contracts.py, dashboard_freshness.py, contract_atlas.py, contract_registry.py, project_intelligence.py, shared_intelligence.py, resume_from_handoff.py, and migrate_prd_schema.py (deleted). -->

<!-- Last reviewed 2026-06-07 — WO-N behavioral eval harness (18.8.3): Eval Health dashboard panel added (id="evals" tab-content). Projections API route at /api/v1/evals/health reads ds_eval_baselines and ds_eval_runs. Dashboard surfaces: total evals, pass rate, baselines table, recent runs table. No change to existing dashboard projection shape; new panel reads from new tables only. -->

<!-- Last reviewed 2026-06-07 — WO-J cache_read_tokens (migration 105): intelligence.py token panel updated to query SUM(cache_read_tokens) from token_usage_sql() subquery and surface prompt-caching wins as a 'whats_working' item. token_attribution.py canonical_token_metrics() now returns actual cache_read_total as cache_hits (was hardcoded 0). Dashboard projection contract shape unchanged: no new routes, no removed fields; cache_hits field was already in the API model (metrics.py:46). -->

<!-- Last reviewed 2026-06-07 — WO-R AI spine consolidation: DASHBOARD_MODULES in execution_spine.py updated — agent_analytics, skill_analytics, workflow_analytics, hook_analytics now declare owns_tables=["execution_events"] and source_tables without per-type invocation tables. COMPONENT_TABLES in read_models.py repointed from per-type tables to execution_events filtered by component_column IS NOT NULL. tool_analytics module declaration source_tables updated to ["execution_events"]. process_run_timeline() invocations section now queries execution_events per component instead of per-type tables. workflow_execution_graph() queries execution_events instead of workflow_invocations. Dashboard projection contract shape preserved: same route endpoints, same field shapes, same derived_view semantics. Source authority changes from 5 per-type tables to execution_events (unified). -->

<!-- Last reviewed 2026-06-08 — WO-Y findings event-spine: FindingsProjection registered in core/projections/runner.py via runner.register_spine(FindingsProjection()). Folds security_events spine into findings_current_status. DASHBOARD_MODULES security_analytics entry in execution_spine.py updated: owns_tables and source_tables now reference security_events and findings_current_status instead of the retired findings/sec_sarif_findings tables. read_models.py security rollup (_security_rollup, _security_remediation_intelligence, _security_status_counts, _security_attribution) repointed to findings_current_status LEFT JOIN security_events. Dashboard projection contract shape preserved: same route endpoints (/api/v1/security/*), same field shapes, same derived_view semantics. -->

<!-- Last reviewed 2026-06-09 — WO-TS3 DuckDB-first read path: project_intelligence.py _project_row_for_authority() now tries DuckDB analytics store first via core/analytics/duckdb_read.get_project_row_duckdb(), falling back to SQLite authority. discovery_internal.py verify_project_exists() similarly tries DuckDB first via project_exists_duckdb(), falling back to SQLite. Dashboard projection contract shape is unchanged: same /api/v1/projects/* and /api/discovery/* route endpoints, same field shapes, same derived_view semantics. The read source layer changed (DuckDB-first, SQLite fallback) but the projection model contract is unaffected. DuckDB is NEVER-AUTHORITY — SQLite business_projects remains the canonical source. -->

<!-- Last reviewed 2026-06-09 — WO-TS4 correction: reverting DuckDB-first read paths in project_intelligence.py and discovery_internal.py — both now read from SQLite business_projects directly. Dashboard projection contract shape is unchanged: same endpoints, same field shapes, same derived_view semantics. The revert fixes a 404 bug where duckdb_projects (0 rows) caused project-not-found before the SQLite fallback was reached. -->

<!-- Last reviewed 2026-06-10 — WO-DEBT-B research router: discovery_research.py added as a new FastAPI router under /api/discovery/research (POST, GET, GET/{cache_id}, DELETE/{cache_id}). Routes read and write the research_cache SQLite table only (no authority tables). Dashboard projection contract shape is unchanged: no new projection shapes, no removed fields, no new authority introduced. The discovery research router is a cache-backed lookup surface, not a dashboard projection. -->

<!-- Last reviewed 2026-06-11 — WO-FULLCI-RED findings/read_models correction: FACT_TABLES in read_models.py updated — "findings" replaced with "findings_current_status" (findings retired in migration 112). All direct "findings" table references in read_models.py updated to use findings_current_status with project-only scope (the projection table lacks milestone_id/task_id/process_run_id). record_security_finding() in execution_spine.py now eagerly calls FindingsProjection.fold_spine() after writing to security_events, keeping findings_current_status in sync at write time. Dashboard projection contract shape preserved: same /api/telemetry/* route endpoints, same field shapes, same derived_view semantics. The read source changed (findings_current_status + security_events spine) but the model contract is unchanged. -->

<!-- Last reviewed 2026-06-14 — WO-DASH-EVAL: New route GET /api/v1/eval/registry added (projections/api/routes/evals.py, registry_router; registered in main.py at prefix /api/v1/eval). Returns list of {target_id, target_type, rubric_score, baseline_score, friction_flag, last_run_at, last_run_id} from eval_registry LEFT JOIN ds_eval_runs on baseline_run_id. Returns [] gracefully when eval_registry table is absent (migration 119 not run). Eval Health panel added to dashboard Overview tab (dashboard.html): table showing Skill/Target | Type | Score | Baseline | Friction | Last Run; friction_flag=true rows highlighted in yellow. Route is a read-only derived projection over eval_registry + ds_eval_runs — no authority writes, no new scans, no schema changes. Dashboard projection contract model is unchanged. -->

<!-- Last reviewed 2026-06-14 — WO-DASH-CONFIG: New route GET /api/v1/config added (projections/api/routes/config.py; registered in main.py at prefix /api/v1). Returns list of {key, value, updated_at} from ds_config ordered by key. Returns [] gracefully when ds_config table is absent. Config tab added to dashboard with sidebar nav item (CF mark, Governance section): table showing Key | Value | Last Updated. Route is read-only over ds_config — no authority writes, no schema changes. Dashboard projection contract model is unchanged. -->

<!-- Last reviewed 2026-06-14 — WO-READMODEL-WIRING: Three read-model repoints, no new routes or schema changes. (1) skill_usage_sql() in authority_sources.py now prefers execution_events WHERE event_type='skill.invoked' (199 rows, direct skill_id column) over the dropped skill_invocations table; canonical_events remains as a fallback. (2) _fallback_hook_invocations() in hooks.py updated with accurate commentary — hook.tool_activity IS emitted (5,094 rows in execution_events); hook_executions primary path has 1,151 rows. (3) _process_run_drilldowns() in read_models.py now derives process run entries from execution_events GROUP BY process_run_id instead of the empty process_runs table. Dashboard projection contract shape is unchanged: same route endpoints, same field shapes, same derived_view semantics. Read sources corrected; no authority writes. -->

<!-- Last reviewed 2026-06-14 — WO-DASH-FRONTEND: Removed Shared Intelligence section from Overview (HTML + JS; shared_intelligence.py route re-registered for Adapter projections endpoint). Added Adapter Projections panel to Overview (GET /api/shared-intelligence/adapters/projections). Added "Development — Not Yet Wired" collapsible section with static cards for process_runs drilldown, SI learning/context/capability/models panels — each labeled with source table. Removed Goal to Action static card (overview entry from DASHBOARD_PAGE_STORIES). Moved telemetry drilldown-detail to Development section. Registered /api/v2/eval/registry and /api/v2/config routes (same handlers, v2 prefix). Dashboard fetches for eval/registry and config updated to /api/v2/*. No new authority writes. -->

<!-- Last reviewed 2026-06-14 — WO-DASH-VALIDATION-GAPS (T4): dashboard.html loadHooksData() rewritten — now uses Promise.all for parallel fetches, updates summary cards (total executions, failures, success rate, anomalies), creates hooks timeline chart (7-day bucket) and performance distribution chart via Chart.js lazy initialization from real API data, and populates per-hook status cards from statsData.by_hook. initHooksCharts() on-load call removed (was creating empty placeholder charts before data arrives). Dashboard projection contract shape unchanged: same /api/telemetry/hooks/* route endpoints, same field shapes, same derived_view semantics. -->

<!-- Last reviewed 2026-06-17 — WO-DASH-RENDER-FIX: frontend render-path fixes in dashboard.html only — NO projection-model contract change. Null-guarded the hooks-total-anomalies write (element removed from DOM); added honest empty-states for hooks cards, hooksPerformance / model-distribution / cost-over-time / workflow-success / skill-success / skill-execution-time charts (replace stuck 'Loading…'/blank canvas); initSkillsTab no-data + catch paths call populateSkillsLeaderboard([]); initWorkflowsTab early-return + initPromotedVsDraftChart show honest empty-states. Same API routes, field shapes, and derived_view semantics; the Dev "Not Yet Wired" section is unchanged. -->

<!-- Last reviewed 2026-06-17 — WO-DASH-DEVDIAG-CONSOLIDATE: dashboard.html only, NO projection-model contract change. Consolidated developer diagnostics into ONE dedicated "Developer Diagnostics" tab: moved the Tool Activity / Event Validation Failures / Raw Event Stream three-block out of the loose hooks-scoped hooks-invisible-tables div into a new id="developer-diagnostics" tab-content (same element ids, fed by the same /api/v1/hooks/tool-activity|validation-failures|raw-events routes), and removed the per-page createDeveloperDiagnostics RAW_TECHNICAL_MARKERS drawer that ensureBusinessStorySections() injected into every page. loadInvisibleTables() now loads on the new tab. Security tab still leads with its findings summary cards; the Overview "Development — Not Yet Wired" section is untouched. Same routes, field shapes, derived_view semantics. -->

<!-- Last reviewed 2026-06-17 — WO-DASH-COST-PLAN: reportable cost is unchanged and honest (read_models._token_rollup still sums only provider-backed cost_visibility rows). Added a NEW, gate-safe API-equivalent cost surface: projections/core/cost_analysis.py (api_equivalent_cost + plan_comparison) computes API-equivalent USD over all token_usage_records via core/pricing/claude_models.compute_cost, honest priced/unpriced coverage; exposed via new route GET /api/v1/cost/plan-comparison (projections/api/routes/cost_plan.py, registered in projections/api/main.py). dashboard.html adds a "Plan vs API-equivalent cost" panel on the Models tab (config-driven plan from ds_config cost.plan_name/cost.plan_monthly_usd, honest empty-state when unset; label "API-equivalent cost", never "Estimated cost") plus a coverage note on the reportable-cost KPI. Fake-cost regression gate still passes (no cost math in the four scanned files). No change to existing projection routes/shapes/derived_view semantics. -->

<!-- Last reviewed 2026-06-17 — WO-EVALS-RENDER: bug fix only, NO contract change. projections/api/routes/evals.py GET /api/v1/evals/health queried non-existent ds_eval_baselines columns (eval_version/score/passed) and 500-ed, blanking the Evals tab despite ds_eval_runs=287/ds_eval_baselines=8. Corrected to the real schema (version, baseline_score, regression_flag; pass = NOT regression_flag) per migration 092. Same route, same response shape/field names (version/score/passed in the JSON), same derived_view semantics; dashboard.html render unchanged (it was already correct once the route returns 200). -->

<!-- Last reviewed 2026-06-18 — WO-DASH-ANALYTICS-TABS: analytics-tab render fixes; one genuine backend bug fix, no contract shape change. analytics.py session-outcome-flow: 'timeout' previously absorbed 'unknown'+'in_progress' (every unresolved session looked like a timeout) — now 'timeout' counts only real timeouts and a new 'other' bucket holds unknown/in_progress (session_flow gains an 'other' key). New read-only route GET /api/v1/insights/attribution-breakouts (insights.py) aggregates token_usage_records by project/milestone/task/skill/agent (top-20 each, existence-guarded) for the Token-Attribution tab. dashboard.html: Learning/Adaptation charts now show honest empty-states when their source tables are empty (learning_event_records=0 etc.) instead of flat-zero/blank; trend-regression series key corrected (reportable_cost); Config + Memory-Surface tabs gain explanatory descriptions (kept, not removed). No fabricated cost/data; fake-cost gate still passes. -->

<!-- Last reviewed 2026-06-18 — WO-DASH-OVERVIEW-ORDER: pure Overview-tab reordering in dashboard.html, NO contract/route/shape change. The Telemetry Traceability section was rendered BEFORE the primary graphs (confusing); moved it BELOW the four primary graphs (Session Timeline, Top Skills, Model Distribution, Cost Over Time) and before the Eval Health panel. KPIs (reportable cost / success rate / active alerts) stay at the top. Same elements, ids, routes, and derived_view semantics — only DOM order changed. -->

<!-- Last reviewed 2026-06-18 — WO-CAPTURE-SKILL-DURATION: derive per-invocation skill duration READ-ONLY (no schema change, no new execution_events writer). projections/core/collectors/authority_sources.py LEFT-JOINs execution.started↔execution.completed on process_run_id and computes execution_time_s = (julianday(completed)-julianday(started))*86400; unpaired invocations stay NULL (excluded from AVG, never fabricated). skill_collector.py surfaces min/avg/max; metrics.py /skills leaderboard falls back to the derived min/max when canonical skill.executed ranges are absent, so the Skills avg-duration card + execution-time-distribution chart render real data (honest empty-state when no paired events). Same routes/shapes/derived_view; no cost math (fake-cost gate green). -->

<!-- Last reviewed 2026-06-18 — WO-DASH-ATTRIBUTION-SURFACES: Token-Attribution breakouts now enrich by_project with the project NAME (read-only JOIN to business_projects in projections/api/routes/insights.py; dashboard.html shows name not UUID). Token→skill attribution fixed at CAPTURE (core/skills/invocation.py writes active_skill.json; core/telemetry/token_capture.py stamps skill_id into the token.consumed trace) — historical rows were NOT backfilled (process_run_id is NULL across token rows → no honest correlation; not fabricated). cost-by-model verified correct (blank is data-quality: 33 of 40 token rows have NULL model_id; the 7 known-model rows compute non-zero). Project Security 'blank' is an HONEST empty state (the 15 findings belong to DreamySuite, not Dream Studio) — no code change. Read-only for projection tables; no cost math in scanned files (fake-cost gate green); same routes/shapes/derived_view. -->
