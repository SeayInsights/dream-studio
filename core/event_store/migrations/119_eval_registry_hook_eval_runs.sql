-- Migration 119: eval_registry + hook_eval_runs (WO-EVAL-REGISTRY).
--
-- eval_registry: unified view of the latest eval status for every known
-- skill / hook / workflow / agent target. One row per target; updated on
-- each new run via the write path in guardrails/evaluator.py and the eval
-- runner. Backfilled from skill_evaluation_runs and hook_executions at
-- migration time.
--
-- hook_eval_runs: mirrors ds_eval_runs for hooks. Populated by
-- guardrails/evaluator.py after each guardrail evaluation that has a
-- hook_id in context.
--
-- Note: hook_invocations was dropped in migration 106 (replaced by
-- execution_events). Backfill uses hook_executions (migration 018)
-- which persists and holds per-hook run history.
--
-- Migration class: migration-risk gate acknowledged.

CREATE TABLE IF NOT EXISTS eval_registry (
    eval_id        TEXT PRIMARY KEY,
    target_type    TEXT NOT NULL CHECK(target_type IN ('skill','hook','workflow','agent')),
    target_id      TEXT NOT NULL,
    rubric_score   INTEGER,
    last_run_at    TEXT,
    last_run_id    TEXT,
    baseline_run_id TEXT,
    friction_flag  INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_eval_registry_target ON eval_registry(target_type, target_id);
CREATE INDEX IF NOT EXISTS idx_eval_registry_last_run ON eval_registry(last_run_at);

CREATE TABLE IF NOT EXISTS hook_eval_runs (
    run_id          TEXT PRIMARY KEY,
    hook_id         TEXT NOT NULL,
    eval_type       TEXT NOT NULL DEFAULT 'guardrail',
    passed          INTEGER NOT NULL DEFAULT 0 CHECK(passed IN (0, 1)),
    score           REAL,
    failure_reasons TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_hook_eval_runs_hook_id ON hook_eval_runs(hook_id);
CREATE INDEX IF NOT EXISTS idx_hook_eval_runs_created_at ON hook_eval_runs(created_at);

-- Backfill eval_registry from skill_evaluation_runs (most recent run per target).
INSERT OR IGNORE INTO eval_registry (eval_id, target_type, target_id, last_run_at, last_run_id, created_at, updated_at)
SELECT
    target_id || '::' || target_type,
    target_type,
    target_id,
    created_at,
    evaluation_id,
    created_at,
    datetime('now')
FROM (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY target_type, target_id ORDER BY created_at DESC) AS rn
    FROM skill_evaluation_runs
)
WHERE rn = 1;

-- Backfill eval_registry from hook_executions (latest run per hook_name).
-- hook_invocations was dropped in migration 106; hook_executions (migration 018) persists.
INSERT OR IGNORE INTO eval_registry (eval_id, target_type, target_id, last_run_at, created_at, updated_at)
SELECT
    hook_name || '::hook',
    'hook',
    hook_name,
    MAX(started_at),
    MIN(started_at),
    datetime('now')
FROM hook_executions
GROUP BY hook_name;
