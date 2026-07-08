-- Migration 145: raw_session_token_accumulators — per-session token running totals in the authority
-- (WO-FILESDB-P2, files-in-database directive 2026-07-07)
--
-- token_capture wrote per-session running token totals to loose
-- ~/.dream-studio/state/session-tokens-<sid>.json files (one per session), read
-- back by the Claude Code emitter's normalize_stop to reconstruct the Stop-event
-- totals. The files-in-database directive moves this operational substrate into
-- the authority. The accumulator must persist across hook processes (each
-- PostToolUse hook is a separate process), so it stays durable — as a row, not a file.
--
-- Writers/readers degrade to the legacy JSON files when this table is absent
-- (migration 145 stays unreleased on the live authority DB until `ds migrate
-- activate`); fresh installs and CI apply it immediately.

CREATE TABLE IF NOT EXISTS raw_session_token_accumulators (
    session_id TEXT PRIMARY KEY,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_creation_input_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_input_tokens INTEGER NOT NULL DEFAULT 0,
    model TEXT,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
