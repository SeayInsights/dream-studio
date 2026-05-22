-- TA1: Backfill task.created events
--
-- Inserts synthetic task.created events into canonical_events for the 9 task
-- rows that predate event emission.  The trace is fully resolved by joining
-- ds_tasks → ds_work_orders to obtain milestone_id.
--
-- Idempotency: deterministic event_id prefix 'backfill-task-created-<task_id>'
-- combined with INSERT OR IGNORE prevents duplicate rows on re-run.
--
-- attribution_status = 'backfill' distinguishes synthetic events from the
-- forward-emitted 'fully_attributed' events produced by the new emitters.
--
-- Timestamps use the original row's created_at to preserve chronological order.

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
    'backfill-task-created-' || t.task_id,
    'task.created',
    t.created_at,
    json_object(
        'domain', 'sdlc',
        'project_id', t.project_id,
        'milestone_id', wo.milestone_id,
        'work_order_id', t.work_order_id,
        'task_id', t.task_id,
        'attribution_status', 'backfill'
    ),
    'info',
    json_object(
        'title', t.title,
        'description', COALESCE(t.description, ''),
        'status', 'created'
    ),
    0, 0, 1
FROM ds_tasks t
LEFT JOIN ds_work_orders wo ON t.work_order_id = wo.work_order_id;
