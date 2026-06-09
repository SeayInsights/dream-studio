-- Phase 18.2.5: Backfill project lifecycle events for pre-event-sourcing rows.
--
-- Inserts synthetic project.created and project.deactivated events into
-- business_canonical_events for any project rows that predate event emission
-- (source_event_id IS NULL). Updates source_event_id / last_event_id on the
-- project rows so the projection is already converged without requiring a rebuild.
--
-- Idempotency: deterministic event_id prefixes with INSERT OR IGNORE prevent
-- duplicate rows on re-run.
--
-- attribution_status = 'backfill' distinguishes synthetic events from forward-
-- emitted 'fully_attributed' events.
--
-- Timestamps use the original row's created_at / updated_at for chronological order.

-- Step 1: Synthetic project.created for every project without source_event_id
INSERT OR IGNORE INTO business_canonical_events (
    event_id,
    event_type,
    event_timestamp,
    trace,
    payload,
    project_id,
    severity,
    source,
    schema_version
)
SELECT
    'backfill-project-created-' || p.project_id,
    'project.created',
    p.created_at,
    json_object(
        'domain', 'sdlc',
        'project_id', p.project_id,
        'attribution_status', 'backfill'
    ),
    json_object(
        'project_id', p.project_id,
        'name', p.name,
        'description', COALESCE(p.description, ''),
        'status', 'active',
        'backfill', 1
    ),
    p.project_id,
    'info',
    'migration-077',
    1
FROM business_projects p
WHERE p.source_event_id IS NULL;

-- Step 2: Synthetic project.deactivated for paused projects
INSERT OR IGNORE INTO business_canonical_events (
    event_id,
    event_type,
    event_timestamp,
    trace,
    payload,
    project_id,
    severity,
    source,
    schema_version
)
SELECT
    'backfill-project-deactivated-' || p.project_id,
    'project.deactivated',
    p.updated_at,
    json_object(
        'domain', 'sdlc',
        'project_id', p.project_id,
        'attribution_status', 'backfill'
    ),
    json_object(
        'project_id', p.project_id,
        'backfill', 1
    ),
    p.project_id,
    'info',
    'migration-077',
    1
FROM business_projects p
WHERE p.status = 'paused'
  AND p.source_event_id IS NULL;

-- Step 3: Update tracking columns on project rows so projection is already converged
UPDATE business_projects
SET source_event_id = 'backfill-project-created-' || project_id,
    last_event_id   = CASE
                          WHEN status = 'paused'
                          THEN 'backfill-project-deactivated-' || project_id
                          ELSE 'backfill-project-created-' || project_id
                      END
WHERE source_event_id IS NULL;
