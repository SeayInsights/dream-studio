-- Migration 083: Establish canonical_events as a migration-owned table.
--
-- Background:
--   canonical_events was previously Python-owned (created by EventStore._init_tables
--   and spool/ingestor.py _write_to_sqlite) but not by any migration. Migrations 052,
--   060, 061, 062, and 064 referenced it, causing aspirational-schema debt: the
--   migration runner could not reproduce the table on a fresh DB without EventStore
--   or the ingestor running first.
--
--   The 18.4.6 schema_coherence audit surfaced this as 5 medium structural findings
--   + 3 high column-mismatch findings (migrations 061/062/064 insert into columns
--   raw_prompt_retained, raw_tool_output_retained, schema_version that EventStore's
--   10-column DDL did not declare) + 1 stale-swallow finding.
--
-- Fix:
--   This migration declares canonical_events with the authoritative 14-column schema
--   from spool/ingestor.py:_write_to_sqlite (the de-facto canonical creator).
--   EventStore._init_tables and _write_to_sqlite both use CREATE TABLE IF NOT EXISTS
--   and align with this schema — both become idempotent no-ops after this migration runs.
--
-- Sequencing note:
--   This migration runs at position 083, AFTER migrations 052-064 in the sequence.
--   On fresh installs (schema 0 → 083+), migrations 052-064 still run BEFORE 083 and
--   still fail with "no such table: canonical_events". The swallow entry in
--   sqlite_bootstrap.py:116 handles these gracefully and is intentional.
--   This migration resolves the structural debt; the swallow remains necessary
--   until migrations 052-064 are superseded or the migration numbering is restructured.
--
-- Live-upgrade safety:
--   On any DB at schema 82 (canonical_events already exists with 14 cols from the
--   ingestor), this migration is a no-op via CREATE TABLE IF NOT EXISTS.
--   All existing rows and columns are preserved unchanged.

CREATE TABLE IF NOT EXISTS canonical_events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    trace JSON NOT NULL DEFAULT '{}',
    severity TEXT NOT NULL DEFAULT 'info',
    payload JSON NOT NULL DEFAULT '{}',
    actor JSON,
    confidence_score REAL,
    source_type TEXT,
    raw_prompt_retained INTEGER NOT NULL DEFAULT 0,
    raw_tool_output_retained INTEGER NOT NULL DEFAULT 0,
    schema_version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    invocation_mode TEXT
);

CREATE INDEX IF NOT EXISTS idx_canonical_events_event_type
    ON canonical_events(event_type);

CREATE INDEX IF NOT EXISTS idx_canonical_events_timestamp
    ON canonical_events(timestamp);
