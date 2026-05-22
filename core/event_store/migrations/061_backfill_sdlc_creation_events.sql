-- TA0: Backfill SDLC entity creation events
--
-- Inserts synthetic project.created, milestone.created, and work_order.created
-- events into canonical_events for rows that predate event emission.
--
-- Idempotency: deterministic event_id prefix 'backfill-<type>-<entity_id>'
-- combined with INSERT OR IGNORE prevents duplicate rows on re-run.
--
-- attribution_status = 'backfill' distinguishes these from forward-emitted
-- events that carry 'fully_attributed'.
--
-- Timestamps use the original row's created_at to preserve chronological order.

-- Part 1: project.created backfill
INSERT OR IGNORE INTO canonical_events (
    event_id,
    event_type,
    timestamp,
    trace,
    severity,
    payload,
    raw_prompt_retained,
    raw_tool_output_retained,
    schema_version
)
SELECT
    'backfill-project-created-' || project_id,
    'project.created',
    created_at,
    json_object(
        'domain', 'sdlc',
        'project_id', project_id,
        'attribution_status', 'backfill'
    ),
    'info',
    json_object(
        'name', name,
        'description', COALESCE(description, ''),
        'status', status
    ),
    0, 0, 1
FROM ds_projects;

-- Part 2: milestone.created backfill
INSERT OR IGNORE INTO canonical_events (
    event_id,
    event_type,
    timestamp,
    trace,
    severity,
    payload,
    raw_prompt_retained,
    raw_tool_output_retained,
    schema_version
)
SELECT
    'backfill-milestone-created-' || milestone_id,
    'milestone.created',
    created_at,
    json_object(
        'domain', 'sdlc',
        'project_id', project_id,
        'milestone_id', milestone_id,
        'attribution_status', 'backfill'
    ),
    'info',
    json_object(
        'title', title,
        'status', status
    ),
    0, 0, 1
FROM ds_milestones;

-- Part 3: work_order.created backfill
INSERT OR IGNORE INTO canonical_events (
    event_id,
    event_type,
    timestamp,
    trace,
    severity,
    payload,
    raw_prompt_retained,
    raw_tool_output_retained,
    schema_version
)
SELECT
    'backfill-work-order-created-' || wo.work_order_id,
    'work_order.created',
    wo.created_at,
    json_object(
        'domain', 'sdlc',
        'project_id', wo.project_id,
        'milestone_id', wo.milestone_id,
        'work_order_id', wo.work_order_id,
        'attribution_status', 'backfill'
    ),
    'info',
    json_object(
        'title', wo.title,
        'status', wo.status,
        'type', COALESCE(wo.work_order_type, '')
    ),
    0, 0, 1
FROM ds_work_orders wo;
