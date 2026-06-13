-- Migration 123: ds_config — operator-local key/value config store (WO-FRICTION-CONFIG).
--
-- Provides a durable config surface for operator-level settings that are too
-- specific for environment variables but too persistent for CLI flags.
-- Initial use: eval.friction_threshold as a middle tier between
-- DREAM_STUDIO_FRICTION_THRESHOLD (env var) and the per-row friction_threshold
-- column (default 3).
--
-- Resolution order: env var > ds_config row > per-row default.
--
-- Migration class: migration-risk gate acknowledged.

CREATE TABLE IF NOT EXISTS ds_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
