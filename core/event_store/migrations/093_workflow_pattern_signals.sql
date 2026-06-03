-- Migration 093: Workflow pattern detection signals table (18.8.4)
--
-- Stores detected skill co-occurrence patterns for the "Patterns Dream Studio
-- Noticed" dashboard panel. Observation-only in Phase 18; Phase 19 reads
-- WHERE confidence_score >= 0.8 AND suppressed = 0 as input to adaptive learning.
--
-- Pattern types:
--   post_completion  — skill_a consistently invoked after work_order.closed
--   pre_close        — skill_a consistently invoked just before work_order.closed
--   always_paired    — skill_a and skill_b almost always invoked together in same session
--
-- Confidence formula:
--   co_occurrence_count / total_sessions_where_either_appeared
--   Range: 0.0 (never co-occur) to 1.0 (always co-occur)
--
-- Phase 19 read contract:
--   SELECT * FROM ds_workflow_pattern_signals
--   WHERE confidence_score >= 0.8 AND suppressed = 0

CREATE TABLE IF NOT EXISTS ds_workflow_pattern_signals (
    pattern_id TEXT PRIMARY KEY,
    project_id TEXT,
    pattern_type TEXT NOT NULL CHECK(pattern_type IN (
        'post_completion', 'pre_close', 'always_paired'
    )),
    skill_a TEXT NOT NULL,
    skill_b TEXT,                           -- NULL for post_completion and pre_close
    co_occurrence_count INTEGER NOT NULL DEFAULT 0,
    total_sessions INTEGER NOT NULL DEFAULT 1,
    confidence_score REAL NOT NULL
        CHECK(confidence_score >= 0.0 AND confidence_score <= 1.0),
    suppressed INTEGER NOT NULL DEFAULT 0 CHECK(suppressed IN (0, 1)),
    suppressed_at TEXT,
    last_observed_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_workflow_patterns_project
    ON ds_workflow_pattern_signals(project_id, confidence_score DESC);

CREATE INDEX IF NOT EXISTS idx_workflow_patterns_phase19
    ON ds_workflow_pattern_signals(confidence_score, suppressed)
    WHERE suppressed = 0;
