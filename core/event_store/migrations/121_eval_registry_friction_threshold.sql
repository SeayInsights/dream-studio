-- Migration 121: eval_registry friction threshold columns (WO-EVAL-LOOP-THRESHOLD).
--
-- The initial friction implementation (WO-EVAL-LOOP) flagged targets on the
-- first signal match with no accumulation logic. This migration adds:
--
--   friction_signal_count  — cumulative signal count across aggregation runs.
--   friction_threshold     — per-target threshold before friction_flag is set
--                            (operator-configurable; default 3).
--
-- friction_flag is now only set to 1 when friction_signal_count >= friction_threshold.
-- Existing rows keep friction_flag as-is; signal counts start at 0.
--
-- Migration class: migration-risk gate acknowledged.

ALTER TABLE eval_registry ADD COLUMN friction_signal_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE eval_registry ADD COLUMN friction_threshold INTEGER NOT NULL DEFAULT 3;
