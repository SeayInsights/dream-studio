-- Migration 136: Drop retired eval + decision tables (WO-DBA-EVAL-DECISION T4)
--
-- Target architecture: studio.db = canonical EVENTS + non-event-sourced AUTHORITY
-- + pipeline ONLY. No private direct-write tables for signals that are really
-- events. Migration 135 backfilled the full history of these four tables into
-- business_canonical_events (work_order.verified / eval.run.completed /
-- decision.recorded); this change set repointed every reader to the canonical
-- stream and removed every legacy writer:
--
--   ds_eval_runs        — writers removed: core/work_orders/verify.py::_write_eval_run,
--                         core/eval/runner.py::_write_live_eval_run/_record_outcome_run.
--                         Readers repointed: projections/api/routes/evals.py,
--                         interfaces/cli/commands/eval.py (registry list/show).
--   hook_eval_runs      — writer removed: guardrails/evaluator.py::_write_hook_eval_run.
--                         Readers repointed: same as ds_eval_runs (eval_id LIKE 'hook:%').
--   decision_log        — writer removed: core/decisions/emitter.py::emit_decision (the
--                         decision.recorded spool emission is now the sole durable write;
--                         a spool-write failure raises RuntimeError, preserving the
--                         documented raise contract). Readers repointed:
--                         core/decisions/query_engine.py (get_decisions/explain_decision/
--                         trace_event/audit_decisions), projections/api/routes/intelligence.py
--                         (decision-tracking win counters).
--   decision_event_link — writer removed alongside decision_log (was written in the same
--                         emit_decision transaction). trace_event/explain_decision now use
--                         payload.triggered_event_id instead of the join table.
--
-- decision_records, eval_registry, and ds_eval_baselines are NOT touched by this
-- migration — they are separate authority/registry tables outside this change set.
--
-- Idempotent: DROP TABLE IF EXISTS; associated indexes are dropped automatically
-- by SQLite when their table is dropped.
--
-- Result: 71 - 4 = 67 tables.
-- Reviewed: 2026-07-03 (WO-DBA-EVAL-DECISION, PR B / T4)

DROP TABLE IF EXISTS ds_eval_runs;
DROP TABLE IF EXISTS hook_eval_runs;
DROP TABLE IF EXISTS decision_log;
DROP TABLE IF EXISTS decision_event_link;
