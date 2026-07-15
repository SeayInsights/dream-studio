-- Migration 146: raw_runtime_state — singleton runtime-state JSON moved into the authority
-- (WO-FILESDB-P2, files-in-database directive 2026-07-07)
--
-- The active skill (active_skill.json), active task (active_task.json), and platform
-- profile (platform.json) were loose ~/.dream-studio/state/*.json files, each read and
-- written wholesale by the skill/token-capture, SDLC, and platform layers. The
-- files-in-database directive moves this operational substrate into the authority as one
-- key -> JSON-value row per state kind. These are process-durable singletons (one active
-- skill/task at a time; one machine profile), so a single keyed table is the lean home for
-- them ("runtime-state JSON -> rows") rather than three per-kind tables.
--
-- Writers/readers degrade to the legacy JSON files when this table is absent (migration
-- 146 stays unreleased on the live authority DB until `ds migrate activate`); fresh
-- installs and CI apply it immediately. Sibling of migration 145
-- (raw_session_token_accumulators) under the same directive.

CREATE TABLE IF NOT EXISTS raw_runtime_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);
