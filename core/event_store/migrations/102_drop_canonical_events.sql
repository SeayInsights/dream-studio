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
--
-- View-safety: SQLite 3.26+ validates ALL existing views during ALTER TABLE RENAME.
-- Drop views that reference tables absent from partial/test DBs before the rename,
-- then recreate any live views afterwards (migration 062/088/089 pattern).
-- prd_* views are not recreated here; migration 103 drops their base tables.

-- ── Drop views before rename ──────────────────────────────────────────────────
DROP VIEW IF EXISTS vw_approach_patterns;
DROP VIEW IF EXISTS vw_guardrail_decisions;
DROP VIEW IF EXISTS vw_prd_progress;
DROP VIEW IF EXISTS vw_task_details;

-- ── Rename ────────────────────────────────────────────────────────────────────
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

-- ── Recreate live views (reference tables still exist after rename) ───────────
CREATE VIEW IF NOT EXISTS vw_approach_patterns AS
SELECT
    skill_id,
    approach,
    COUNT(*) AS times_tried,
    SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes,
    ROUND(
        CAST(SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS REAL)
        / COUNT(*) * 100, 1
    ) AS success_pct,
    CAST(AVG(tokens_used) AS INTEGER) AS avg_tokens,
    ROUND(AVG(duration_s), 1) AS avg_duration
FROM raw_approaches
GROUP BY skill_id, approach
HAVING COUNT(*) >= 2;

CREATE VIEW IF NOT EXISTS vw_guardrail_decisions AS
SELECT
    decision_id,
    rule_id,
    action AS decision,
    event_id,
    evaluated_at AS event_timestamp,
    message AS reason
FROM guardrail_decisions
ORDER BY evaluated_at DESC;
