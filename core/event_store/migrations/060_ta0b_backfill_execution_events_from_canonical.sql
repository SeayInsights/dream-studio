-- Migration 060: TA0b — Backfill domain field and execution_events projection
-- Part of the Token Attribution remediation (TA0b dual-event-store reconciliation).
--
-- Part 1a: Backfill '$.domain' = 'telemetry' in canonical_events trace JSON
--   for known telemetry event types that are missing the domain field.
--   Covers session, prompt, tool, token, skill, workflow, context, security,
--   quality, integration, execution, and wave lifecycle events.
--
UPDATE canonical_events
SET trace = json_set(COALESCE(trace, '{}'), '$.domain', 'telemetry')
WHERE event_type IN (
    'session.lifecycle.started', 'session.lifecycle.ended',
    'prompt.lifecycle.submitted', 'prompt.lifecycle.validated',
    'tool.execution.started', 'tool.execution.completed',
    'token.consumption.recorded',
    'skill.lifecycle.loaded', 'skill.lifecycle.completed',
    'workflow.progress.updated',
    'context.threshold.crossed',
    'security.scan.completed', 'quality.score.recorded',
    'integration.health.changed',
    'execution.complete', 'execution.tests_executed',
    'execution.started', 'execution.completed', 'execution.failed',
    'wave.started', 'wave.completed', 'wave.failed', 'wave.task_updated',
    'workflow.node.completed', 'workflow.learned'
)
AND (json_extract(trace, '$.domain') IS NULL OR json_extract(trace, '$.domain') = '');

-- Part 1b: Backfill '$.domain' = 'sdlc' in canonical_events trace JSON
--   for known SDLC event types that are missing the domain field.
--   Covers work orders, tasks, milestones, skills, gates, projects, and documents.
--
UPDATE canonical_events
SET trace = json_set(COALESCE(trace, '{}'), '$.domain', 'sdlc')
WHERE event_type IN (
    'work_order.started', 'work_order.closed', 'work_order.blocked',
    'task.completed', 'milestone.completed',
    'skill.invoked', 'skill.budget_exceeded',
    'gate.bypassed', 'gate.pre_push.failed',
    'project.registered', 'project.updated',
    'document.created', 'document.updated', 'document.archived'
)
AND (json_extract(trace, '$.domain') IS NULL OR json_extract(trace, '$.domain') = '');

-- Part 2: Populate execution_events from canonical execution events
--   Best-effort replay: inserts execution_events rows for canonical
--   execution.started / execution.completed / execution.failed events
--   that have not yet been projected (checked via _built_from_event_id).
--   Scalar trace fields are lifted from the canonical trace JSON;
--   payload is stored verbatim as metadata_json.
--   Uses SQLite randomblob to generate UUID v4-compatible event IDs.
--
INSERT OR IGNORE INTO execution_events (
    event_id, event_type, event_name, project_id, milestone_id, task_id,
    process_run_id, agent_id, skill_id, workflow_id,
    hook_id, tool_id, model_id, adapter_id,
    source_refs_json, evidence_refs_json, metadata_json,
    outcome_status, _built_from_event_id
)
SELECT
    lower(
        hex(randomblob(4)) || '-' ||
        hex(randomblob(2)) || '-4' ||
        substr(hex(randomblob(2)), 2) || '-' ||
        substr('89ab', abs(random()) % 4 + 1, 1) ||
        substr(hex(randomblob(2)), 2) || '-' ||
        hex(randomblob(6))
    ),
    ce.event_type,
    COALESCE(json_extract(ce.payload, '$.event_name'), ce.event_type),
    json_extract(ce.trace, '$.project_id'),
    json_extract(ce.trace, '$.milestone_id'),
    json_extract(ce.trace, '$.task_id'),
    json_extract(ce.trace, '$.process_run_id'),
    json_extract(ce.trace, '$.agent_id'),
    json_extract(ce.trace, '$.skill_id'),
    json_extract(ce.trace, '$.workflow_id'),
    json_extract(ce.trace, '$.hook_id'),
    json_extract(ce.trace, '$.tool_id'),
    json_extract(ce.trace, '$.model_id'),
    json_extract(ce.trace, '$.adapter_id'),
    '[]',
    '[]',
    COALESCE(ce.payload, '{}'),
    json_extract(ce.payload, '$.outcome_status'),
    ce.event_id
FROM canonical_events ce
WHERE ce.event_type IN ('execution.started', 'execution.completed', 'execution.failed')
AND NOT EXISTS (
    SELECT 1 FROM execution_events ee
    WHERE ee._built_from_event_id = ce.event_id
);
