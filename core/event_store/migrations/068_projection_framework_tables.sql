-- Migration 068: Projection Framework Tables — Phase 18.1.5
--
-- Establishes the operational infrastructure for the v2 projection framework:
--   1. projection_state    — cursor tracking per projection, per canonical source
--   2. projection_dead_letter — events that exhausted retry budget
--   3. projection_retry_queue — pending retries with next_retry_at scheduling
--
-- These tables support the ProjectionRunner daemon and ProjectionRegistry.
-- Projections use projection_state to resume from where they left off after
-- restart (no re-processing of already-processed events).
--
-- Dead-letter entries are operator-queryable via `ds projection dead-letter list`
-- and resolvable via retry or explicit ignore.
--
-- Idempotent: safe to re-run; uses IF NOT EXISTS throughout.

-- ── 1. Projection State ───────────────────────────────────────────────────
-- One row per registered projection. Tracks cursor position in each canonical.
-- The runner reads this at startup to resume incremental processing.

CREATE TABLE IF NOT EXISTS projection_state (
    projection_name TEXT PRIMARY KEY,

    -- Cursor positions: the last event_id processed in each canonical source.
    -- NULL means the projection has not yet processed any events from that source.
    last_processed_business_event_id TEXT,
    last_processed_ai_event_id TEXT,

    -- Operational metrics for `ds projection status <name>`.
    last_run_at TEXT,
    events_processed_total INTEGER NOT NULL DEFAULT 0,
    events_failed_total INTEGER NOT NULL DEFAULT 0
);

-- ── 2. Projection Dead Letter ─────────────────────────────────────────────
-- Events that failed handle() and exhausted their retry budget.
-- Operator inspects and resolves these; daemon continues with next event.

CREATE TABLE IF NOT EXISTS projection_dead_letter (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    -- Which event failed.
    event_id TEXT NOT NULL,
    event_source TEXT NOT NULL CHECK (event_source IN ('business', 'ai')),

    -- Which projection failed it.
    projection_name TEXT NOT NULL,

    -- Failure details for operator investigation.
    error_message TEXT,
    error_traceback TEXT,
    failed_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),

    -- Retry history.
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_retry_at TEXT,

    -- Operator resolution state.
    -- active   = awaiting attention
    -- resolved = operator confirmed the event was handled (manually or re-queued)
    -- ignored  = operator decided not to retry
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'resolved', 'ignored'))
);

CREATE INDEX IF NOT EXISTS idx_pdl_projection_name
    ON projection_dead_letter(projection_name);
CREATE INDEX IF NOT EXISTS idx_pdl_failed_at
    ON projection_dead_letter(failed_at);
CREATE INDEX IF NOT EXISTS idx_pdl_status
    ON projection_dead_letter(status);
CREATE INDEX IF NOT EXISTS idx_pdl_event_id
    ON projection_dead_letter(event_id);

-- ── 3. Projection Retry Queue ─────────────────────────────────────────────
-- Events scheduled for retry after transient failure.
-- Runner polls this table on each cycle; next_retry_at controls when to attempt.

CREATE TABLE IF NOT EXISTS projection_retry_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    event_id TEXT NOT NULL,
    event_source TEXT NOT NULL CHECK (event_source IN ('business', 'ai')),
    projection_name TEXT NOT NULL,

    -- When the runner should next attempt this event.
    next_retry_at TEXT NOT NULL,

    -- How many retries have already been attempted (0 = first retry pending).
    retry_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_prq_next_retry_at
    ON projection_retry_queue(next_retry_at);
CREATE INDEX IF NOT EXISTS idx_prq_projection_name
    ON projection_retry_queue(projection_name);
