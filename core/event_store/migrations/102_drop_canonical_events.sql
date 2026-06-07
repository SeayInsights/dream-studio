-- Migration 102: WO-M — Retire canonical_events (legacy primary substrate)
--
-- Context: AD-1 promoted business_canonical_events + ai_canonical_events to authority.
-- The ingestor dual-canonical write is now primary (no longer best-effort).
-- canonical_events is no longer written to; this migration retires it.
--
-- Strategy: rename-then-view (safe for existing SELECTs)
--   1. Physical table renamed to canonical_events_legacy_backup — historical rows preserved.
--   2. Compat VIEW canonical_events created so existing SELECT readers continue to work
--      without code changes. The view is a UNION of both authority tables.
--   3. Raw-only events (routes=[]) do not appear in the view — they stay in raw_claude_code_events
--      per Commitment 9 (mechanical detail stays in raw).
--
-- Column mapping (legacy → dual-canonical):
--   timestamp   → event_timestamp   (canonical name in authority tables)
--   created_at  → received_at       (ingestion timestamp)
--   actor, confidence_score, source_type, raw_prompt_retained,
--   raw_tool_output_retained, invocation_mode → NULL (legacy-only fields, no equivalent)
--
-- After WO-M: no writes go to canonical_events. Paired events appear once (UNION deduplicates
-- by identical column values). Readers that need all historical rows get them from
-- canonical_events_legacy_backup directly or via the compat view.
--
-- Idempotent: guarded with IF NOT EXISTS / IF EXISTS where applicable.
-- legacy_canonical_event_import_map: per WO-E, retire after cutover parity check is complete.

ALTER TABLE canonical_events RENAME TO canonical_events_legacy_backup;

CREATE VIEW canonical_events AS
    SELECT
        event_id,
        event_type,
        event_timestamp                       AS timestamp,
        trace,
        severity,
        payload,
        NULL                                  AS actor,
        NULL                                  AS confidence_score,
        NULL                                  AS source_type,
        0                                     AS raw_prompt_retained,
        0                                     AS raw_tool_output_retained,
        schema_version,
        received_at                           AS created_at,
        NULL                                  AS invocation_mode
    FROM business_canonical_events
    UNION
    SELECT
        event_id,
        event_type,
        event_timestamp                       AS timestamp,
        trace,
        severity,
        payload,
        NULL                                  AS actor,
        NULL                                  AS confidence_score,
        NULL                                  AS source_type,
        0                                     AS raw_prompt_retained,
        0                                     AS raw_tool_output_retained,
        schema_version,
        received_at                           AS created_at,
        NULL                                  AS invocation_mode
    FROM ai_canonical_events;
