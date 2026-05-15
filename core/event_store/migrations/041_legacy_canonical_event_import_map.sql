-- Migration 041: Legacy canonical event reconciliation import map
-- Tracks row-level reconciliation from old backup canonical_events into current
-- authority tables. This table is an import ledger only; it does not recreate
-- canonical_events as active authority.

CREATE TABLE IF NOT EXISTS legacy_canonical_event_import_map (
    import_map_id TEXT PRIMARY KEY,
    legacy_event_id TEXT NOT NULL,
    source_table TEXT NOT NULL DEFAULT 'canonical_events',
    event_type TEXT NOT NULL,
    taxonomy TEXT NOT NULL,
    target_table TEXT,
    target_record_id TEXT,
    import_status TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    payload_hash TEXT NOT NULL,
    reason TEXT NOT NULL,
    source_refs_json TEXT NOT NULL DEFAULT '[]',
    evidence_refs_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (
        import_status IN (
            'pending_import',
            'imported',
            'skipped_duplicate',
            'manual_review_required',
            'retention_only',
            'obsolete_no_action',
            'superseded_by_current_authority',
            'not_mapped',
            'error'
        )
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_legacy_event_import_map_target
ON legacy_canonical_event_import_map(
    legacy_event_id,
    source_table,
    COALESCE(target_table, ''),
    COALESCE(target_record_id, '')
);

CREATE INDEX IF NOT EXISTS idx_legacy_event_import_map_status
ON legacy_canonical_event_import_map(import_status, confidence);

CREATE INDEX IF NOT EXISTS idx_legacy_event_import_map_type
ON legacy_canonical_event_import_map(event_type, taxonomy);
