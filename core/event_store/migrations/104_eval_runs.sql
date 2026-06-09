-- Migration 104: ds_eval_runs — full per-run record for behavioral eval harness (18.8.3).
--
-- ds_eval_baselines (migration 092) stores the baseline score per eval_id/version.
-- ds_eval_runs stores the individual run evidence, including skill_versions_snapshot
-- and failure_reasons, enabling regression detection and audit trails.
--
-- baseline_run_id FK is self-referential and nullable (first run has no baseline yet).

CREATE TABLE IF NOT EXISTS ds_eval_runs (
    run_id TEXT PRIMARY KEY,
    eval_id TEXT NOT NULL,
    eval_version TEXT NOT NULL DEFAULT '1.0.0',
    started_at TEXT NOT NULL,
    completed_at TEXT,
    model_tested TEXT NOT NULL DEFAULT 'claude-sonnet-4-6',
    skill_versions_snapshot JSON,
    event_score REAL,
    behavior_score REAL,
    total_score REAL,
    passed INTEGER NOT NULL DEFAULT 0,
    failure_reasons JSON,
    token_cost_usd REAL,
    baseline_run_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_eval_id ON ds_eval_runs(eval_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_started_at ON ds_eval_runs(started_at);
CREATE INDEX IF NOT EXISTS idx_eval_runs_passed ON ds_eval_runs(passed);
