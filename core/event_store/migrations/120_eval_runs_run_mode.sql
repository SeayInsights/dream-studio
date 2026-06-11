-- Migration 120: add run_mode column to ds_eval_runs (WO-EVAL-LIVE).
--
-- Distinguishes fixture-mode runs (deterministic event matching against
-- pre-specified fixture_events) from live-mode runs (subagent spawn + event
-- capture) and verify-mode runs (work-order close verification in
-- core/work_orders/verify.py).
--
-- ALTER TABLE ADD COLUMN with NOT NULL DEFAULT is safe on all existing rows;
-- SQLite stores the default without back-filling each row.
--
-- Migration class: migration-risk gate acknowledged.

ALTER TABLE ds_eval_runs ADD COLUMN run_mode TEXT NOT NULL DEFAULT 'fixture';
