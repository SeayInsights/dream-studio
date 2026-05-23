-- Migration 067: v2 Dual Canonical Layer — business_canonical_events + ai_canonical_events
--
-- Establishes the L2 dual canonical structure per data-model-v2.md Commitment 2.
-- The single canonical_events table (L2, legacy) is split into two domain-specific
-- parallel event logs. canonical_events is NOT dropped here — it remains during the
-- Phase 18.1.x transition period so existing readers continue to work.
--
-- Layer 2a: business_canonical_events — operator-facing facts
--   Records: project/milestone/work-order/task lifecycle, gate decisions,
--   security findings, audit findings, document changes, PRD/change-order events.
--
-- Layer 2b: ai_canonical_events — AI execution facts at meaningful-unit granularity
--   Records: skill invocations, workflow runs, hook executions at boundary level,
--   token consumption summaries, session lifecycle, research/analysis pipelines.
--   Per Commitment 9: individual tool calls stay in raw (not in AI canonical).
--
-- Routing: the event type registry (config/event_type_registry.py) determines
-- which canonical table(s) each event_type writes to. The spool ingestor applies
-- the registry at ingest time. Paired events (AI-produced business outcomes) write
-- to both canonicals and share a correlation_id for cross-layer joins.
--
-- Schema design note: high-frequency join fields (correlation_id, project_id, etc.)
-- are denormalized as top-level columns for index-backed queries. Remaining context
-- lives in the trace/payload JSON fields.
--
-- Idempotent: safe to re-run; uses IF NOT EXISTS throughout.

-- ── Layer 2a: Business Canonical ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS business_canonical_events (
    -- Identity
    event_id TEXT PRIMARY KEY,

    -- Ingestion timestamp (when the ingestor wrote this row, not the event emission time)
    received_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),

    -- Classifier fields extracted from source event for fast filtering
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,

    -- Full event context (immutable; preserved in native form)
    trace JSON NOT NULL DEFAULT '{}',
    payload JSON NOT NULL DEFAULT '{}',

    -- Correlation ID links this event to related events in ai_canonical_events and raw.
    -- Format: "sess-{id}:wf-{id}:skill-{id}:..." (colon-joined non-null prefix segments)
    correlation_id TEXT,

    -- Denormalized SDLC context from trace for index-backed SDLC queries.
    -- These are the primary join fields for business L3 projections.
    project_id TEXT,
    milestone_id TEXT,
    work_order_id TEXT,
    task_id TEXT,

    -- Metadata
    severity TEXT NOT NULL DEFAULT 'info',
    -- source distinguishes forward-written events from backfilled historical rows
    source TEXT NOT NULL DEFAULT 'ingestor'
);

-- Individual SDLC context indexes (primary join paths for business L3)
CREATE INDEX IF NOT EXISTS idx_bce_correlation_id  ON business_canonical_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_bce_event_type      ON business_canonical_events(event_type);
CREATE INDEX IF NOT EXISTS idx_bce_event_timestamp ON business_canonical_events(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_bce_received_at     ON business_canonical_events(received_at);
CREATE INDEX IF NOT EXISTS idx_bce_project_id      ON business_canonical_events(project_id);
CREATE INDEX IF NOT EXISTS idx_bce_milestone_id    ON business_canonical_events(milestone_id);
CREATE INDEX IF NOT EXISTS idx_bce_work_order_id   ON business_canonical_events(work_order_id);
CREATE INDEX IF NOT EXISTS idx_bce_task_id         ON business_canonical_events(task_id);

-- Compound indexes for common analytical access patterns
-- "All business events for project X in a time window"
CREATE INDEX IF NOT EXISTS idx_bce_project_time ON business_canonical_events(project_id, event_timestamp);
-- "All events of type Y (across time)"
CREATE INDEX IF NOT EXISTS idx_bce_type_time    ON business_canonical_events(event_type, event_timestamp);
-- "All events of type Y for project X"
CREATE INDEX IF NOT EXISTS idx_bce_project_type ON business_canonical_events(project_id, event_type);


-- ── Layer 2b: AI Canonical ────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS ai_canonical_events (
    -- Identity
    event_id TEXT PRIMARY KEY,

    -- Ingestion timestamp
    received_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),

    -- Classifier fields
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,

    -- Full event context
    trace JSON NOT NULL DEFAULT '{}',
    payload JSON NOT NULL DEFAULT '{}',

    -- Correlation ID links this event to related events in business_canonical_events and raw.
    correlation_id TEXT,

    -- Denormalized AI execution context from trace for index-backed AI queries.
    -- These are the primary join fields for AI execution L3 projections.
    session_id TEXT,
    skill_id TEXT,
    workflow_id TEXT,
    agent_id TEXT,
    hook_id TEXT,
    model_id TEXT,

    -- Metadata
    severity TEXT NOT NULL DEFAULT 'info',
    source TEXT NOT NULL DEFAULT 'ingestor'
);

-- Individual AI context indexes (primary join paths for AI execution L3)
CREATE INDEX IF NOT EXISTS idx_ace_correlation_id  ON ai_canonical_events(correlation_id);
CREATE INDEX IF NOT EXISTS idx_ace_event_type      ON ai_canonical_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ace_event_timestamp ON ai_canonical_events(event_timestamp);
CREATE INDEX IF NOT EXISTS idx_ace_received_at     ON ai_canonical_events(received_at);
CREATE INDEX IF NOT EXISTS idx_ace_session_id      ON ai_canonical_events(session_id);
CREATE INDEX IF NOT EXISTS idx_ace_skill_id        ON ai_canonical_events(skill_id);
CREATE INDEX IF NOT EXISTS idx_ace_workflow_id     ON ai_canonical_events(workflow_id);
CREATE INDEX IF NOT EXISTS idx_ace_agent_id        ON ai_canonical_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_ace_hook_id         ON ai_canonical_events(hook_id);
CREATE INDEX IF NOT EXISTS idx_ace_model_id        ON ai_canonical_events(model_id);

-- Compound indexes for common AI analytical queries
-- "All AI events for session S in time order"
CREATE INDEX IF NOT EXISTS idx_ace_session_time ON ai_canonical_events(session_id, event_timestamp);
-- "All events of type Y across time"
CREATE INDEX IF NOT EXISTS idx_ace_type_time    ON ai_canonical_events(event_type, event_timestamp);
-- "All events for skill S across time"
CREATE INDEX IF NOT EXISTS idx_ace_skill_time   ON ai_canonical_events(skill_id, event_timestamp);
-- "All events for workflow W across time"
CREATE INDEX IF NOT EXISTS idx_ace_workflow_time ON ai_canonical_events(workflow_id, event_timestamp);
