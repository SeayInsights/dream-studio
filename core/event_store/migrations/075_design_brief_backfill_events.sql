-- Phase 18.2.4: Backfill design_brief lifecycle events for pre-event-sourcing rows.
--
-- Inserts synthetic design_brief.created and design_brief.locked events into
-- business_canonical_events for any brief rows that predate event emission
-- (source_event_id IS NULL). Updates source_event_id / last_event_id on the
-- brief rows so the projection is already converged without requiring a rebuild.
--
-- Idempotency: deterministic event_id prefixes with INSERT OR IGNORE prevent
-- duplicate rows on re-run.
--
-- attribution_status = 'backfill' distinguishes synthetic events from forward-
-- emitted 'fully_attributed' events (marks these as pre-event-sourcing data).
--
-- Timestamps use the original row's created_at / updated_at for chronological order.

-- Step 1: Synthetic design_brief.created for every brief without source_event_id
INSERT OR IGNORE INTO business_canonical_events (
    event_id,
    event_type,
    event_timestamp,
    trace,
    payload,
    severity,
    source,
    schema_version
)
SELECT
    'backfill-brief-created-' || b.brief_id,
    'design_brief.created',
    b.created_at,
    json_object(
        'domain', 'sdlc',
        'project_id', b.project_id,
        'brief_id', b.brief_id,
        'attribution_status', 'backfill'
    ),
    json_object(
        'brief_id', b.brief_id,
        'project_id', b.project_id,
        'status', 'draft',
        'backfill', 1
    ),
    'info',
    'migration-075',
    1
FROM business_design_briefs b
WHERE b.source_event_id IS NULL;

-- Step 2: Synthetic design_brief.locked for briefs that are locked
INSERT OR IGNORE INTO business_canonical_events (
    event_id,
    event_type,
    event_timestamp,
    trace,
    payload,
    severity,
    source,
    schema_version
)
SELECT
    'backfill-brief-locked-' || b.brief_id,
    'design_brief.locked',
    b.updated_at,
    json_object(
        'domain', 'sdlc',
        'project_id', b.project_id,
        'brief_id', b.brief_id,
        'attribution_status', 'backfill'
    ),
    json_object(
        'brief_id', b.brief_id,
        'backfill', 1
    ),
    'info',
    'migration-075',
    1
FROM business_design_briefs b
WHERE b.status = 'locked'
  AND b.source_event_id IS NULL;

-- Step 3: Update tracking columns on brief rows so projection is already converged
UPDATE business_design_briefs
SET source_event_id = 'backfill-brief-created-' || brief_id,
    last_event_id   = CASE
                          WHEN status = 'locked'
                          THEN 'backfill-brief-locked-' || brief_id
                          ELSE 'backfill-brief-created-' || brief_id
                      END
WHERE source_event_id IS NULL;
