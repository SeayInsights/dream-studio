-- Migration 092: Behavioral eval harness baseline storage (18.8.3)
--
-- Stores per-eval baseline scores and regression flags.
-- Baseline is established on first run; subsequent runs compared against it.
-- Regression = composite_score drops more than regression_threshold below baseline.
-- Baseline updates require explicit 'ds eval baseline --update' (no auto-update).

CREATE TABLE IF NOT EXISTS ds_eval_baselines (
    eval_id TEXT NOT NULL,
    version TEXT NOT NULL DEFAULT '1.0.0',
    baseline_score REAL NOT NULL,
    last_run_score REAL,
    last_run_at TEXT,
    regression_flag INTEGER NOT NULL DEFAULT 0 CHECK(regression_flag IN (0, 1)),
    regression_threshold REAL NOT NULL DEFAULT 0.10,
    run_count INTEGER NOT NULL DEFAULT 0,
    last_updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (eval_id, version)
);

CREATE INDEX IF NOT EXISTS idx_eval_baselines_regression
    ON ds_eval_baselines(regression_flag)
    WHERE regression_flag = 1;
