-- Migration 122: eval_registry pending_rerun column (WO-EVAL-QUEUE).
--
-- pending_rerun is an explicit durable queue marker for the ds eval queue CLI.
-- It is set to 1 alongside friction_flag when aggregate_friction_signals() flags
-- a target, and cleared to 0 by ds eval queue run after a passing live re-run.
-- Kept in sync with friction_flag so the queue state survives as a standalone
-- queryable column without relying on friction_flag semantics.
--
-- Migration class: migration-risk gate acknowledged.

ALTER TABLE eval_registry ADD COLUMN pending_rerun INTEGER NOT NULL DEFAULT 0;
