-- Migration 055: Technology signals table for session intelligence harvest (Slice 8c).
-- Stores file extension counts derived from Claude Code session history.
-- Privacy: only extension counts are stored, never file paths or content.

CREATE TABLE IF NOT EXISTS ds_technology_signals (
    signal_id    TEXT PRIMARY KEY,
    extension    TEXT NOT NULL,
    count        INTEGER NOT NULL DEFAULT 0,
    last_seen    TEXT NOT NULL
);
