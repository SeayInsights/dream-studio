-- Migration 094: Add label column to ds_eval_baselines (18.10)
--
-- Adds a label field to support named baseline snapshots (e.g., 'pre_phase_19').
-- Used by 18.10 to freeze the pre-Phase-19 baseline as a named reference point.
-- Phase 19 retroactive validation reads rows WHERE label = 'pre_phase_19' to
-- compute improvement/degradation deltas.
--
-- Default NULL: existing rows have no label (they're unlabeled regression detection).
-- Labeled rows: named snapshots created at significant phase transitions.

ALTER TABLE ds_eval_baselines ADD COLUMN label TEXT DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_eval_baselines_label
    ON ds_eval_baselines(label)
    WHERE label IS NOT NULL;
