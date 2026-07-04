-- Migration 141: Drop write-orphaned raw_workflow_runs / raw_workflow_nodes
-- (WO 9f47a1a0-11db-4fcb-9d93-d350fd9a5a6f, operator-approved pre-squash removal)
--
-- raw_workflow_runs (2 rows) and raw_workflow_nodes (25 rows) both last wrote
-- 2026-05-18 despite daily workflow runs continuing since. Root cause: the sole
-- writer, core/event_store/studio_db.py::archive_workflow (called from
-- control/execution/workflow/state.py::_try_archive_and_prune), inserted into
-- these tables inside the same best-effort try/except that also emitted
-- workflow.completed / workflow.node.completed canonical events — an INSERT
-- failure anywhere in that block silently aborted the whole write (the
-- exception was swallowed and archive_workflow() returned False). The
-- canonical event emission itself kept firing independently for a while
-- longer (last workflow.completed 2026-06-11 in ai_canonical_events;
-- workflow.node.completed last 2026-05-18) before also going dark, since
-- per-node event emission was interleaved with the raw_workflow_nodes INSERT
-- loop and both raw tables share the same failure surface.
--
-- Fix (this change set): control/execution/workflow/state.py no longer calls
-- archive_workflow() at all. It now writes workflow.completed (+ one
-- workflow.node.completed per node) canonical event envelopes directly to the
-- spool via emitters/shared/spool_writer.py — decoupled from any SQLite
-- INSERT, so a schema-drift failure in a legacy raw table can never again
-- silently swallow event emission. archive_workflow() and its
-- _emit_workflow_telemetry() helper are deleted from studio_db.py.
--
-- Readers repointed off the dropped tables in the same change set:
--   projections/core/collectors/workflow_collector.py — now reads
--     ai_canonical_events WHERE event_type IN ('workflow.completed',
--     'workflow.node.completed'), honest-empty when none.
--   projections/core/sla/tracker.py (workflows_success_rate branch) — same
--     source table.
--   core/event_store/studio_db.py::last_run / run_count — now derive from
--     ai_canonical_events filtered by json_extract(payload, '$.workflow'),
--     preserving their return shapes for control/execution/workflow/registry.py
--     (the sole caller, via list_workflows()).
--
-- Both event types (workflow.completed, workflow.node.completed) already
-- exist in canonical/events/types.py and are already registered in
-- config/event_type_registry.py (AI-only routing — ai_canonical_events is the
-- sole destination table; no registry changes needed).
--
-- Evidence this is safely droppable:
--   * grepped core/event_store/migrations/ for
--     "REFERENCES raw_workflow_runs(" / "REFERENCES raw_workflow_nodes(" —
--     the only reference is raw_workflow_nodes.run_key -> raw_workflow_runs
--     (both tables dropped together in this migration; no external table
--     references either).
--   * grepped CREATE VIEW bodies for both table names — no hits.
--   * fresh bootstrap_database() PRAGMA foreign_key_list confirms the same:
--     the sole FK offender is (raw_workflow_nodes -> raw_workflow_runs).
--
-- Result: 60 - 2 = 58 tables (fresh bootstrap_database() count of
-- sqlite_master tables excluding sqlite_%, measured 2026-07-04).
-- Reviewed: 2026-07-04 (WO 9f47a1a0-11db-4fcb-9d93-d350fd9a5a6f)

DROP INDEX IF EXISTS idx_wfnodes_runkey;
DROP INDEX IF EXISTS idx_workflow_nodes_activity;
DROP TABLE IF EXISTS raw_workflow_nodes;

DROP INDEX IF EXISTS idx_wfruns_workflow;
DROP INDEX IF EXISTS idx_workflow_runs_prd;
DROP INDEX IF EXISTS idx_workflow_runs_task;
DROP INDEX IF EXISTS idx_workflow_runs_activity;
DROP TABLE IF EXISTS raw_workflow_runs;
