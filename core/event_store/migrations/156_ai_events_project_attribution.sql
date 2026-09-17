-- Migration 156: ai_canonical_events.project_id — attribute AI spend to a project
-- (Attribution Coherence Phase 3)
--
-- business_canonical_events has carried project_id since it existed, and the spool
-- ingestor already resolves one for every envelope
-- (spool/ingestor.py::_extract_ids reads envelope.project_id, trace.project_id and
-- payload.project_id). ai_canonical_events had no column to put it in, so the
-- INSERT simply omitted it and the resolved value was discarded.
--
-- Measured before this migration: 68,433 token.consumed events, 0 (0.0%) carrying
-- a project_id anywhere the reader could reach. Every cost, model-mix and skill
-- rollup therefore aggregated ALL clients together — SeayInsights, Fulcrum and
-- Hypershift work inflating one another — and the question "what has this
-- engagement cost" was unanswerable at the project level, let alone the client
-- level (client is one join away: business_projects.client_id, migration 155).
--
-- ADDITIVE ONLY: one nullable column and two indexes on an existing table. No
-- table is dropped, no row is deleted or rewritten, and no existing reader
-- changes shape — a reader that does not select project_id is unaffected. The
-- column stays NULLABLE on purpose: an event whose project cannot be established
-- from evidence must read as unattributed, never be assigned a plausible default.
-- A wrong attribution is worse than a missing one here, because it silently moves
-- spend between clients.
--
-- Historical rows are attributed separately by
-- core/telemetry/project_backfill.py, which derives the project from session
-- evidence and leaves anything it cannot establish NULL.
--
-- Paired reverse migration: rollback/156_ai_events_project_attribution.sql.

ALTER TABLE ai_canonical_events ADD COLUMN project_id TEXT;

-- Rollups group by project, usually windowed by time or filtered to one event
-- type, so index the column alone and paired with event_type.
CREATE INDEX IF NOT EXISTS idx_ace_project_id ON ai_canonical_events(project_id);

CREATE INDEX IF NOT EXISTS idx_ace_project_event_type
    ON ai_canonical_events(project_id, event_type);
