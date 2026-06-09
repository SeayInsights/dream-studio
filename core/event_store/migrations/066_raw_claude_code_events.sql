-- Migration 066: v2 Raw Layer — raw_claude_code_events (Phase 18.1.1)
--
-- Establishes the L1 raw layer for the Claude Code adapter per data-model-v2.md
-- Layer 1 contract. This is the queryable analytical detail layer below canonical.
--
-- Purpose:
--   1. Adapter independence — Claude Code events are preserved in their native
--      source shape. Future adapters (raw_cursor_events, raw_codex_events) get
--      their own tables with their own shapes.
--   2. Analytical drill-down — Tool-level and hook-level questions that canonical
--      doesn't carry are answered here, indexed for drill-down by correlation ID.
--
-- Transitional note (Phase 18.1.x):
--   The spool ingestor dual-writes to raw_claude_code_events AND canonical_events
--   during this phase. Phase 18.1.2 will introduce dual canonical (business + AI)
--   and eventually retire the single canonical_events table.
--
-- Idempotent: safe to re-run; uses IF NOT EXISTS throughout.

CREATE TABLE IF NOT EXISTS raw_claude_code_events (
    -- Identity: native event_id from source event (UUID string)
    event_id TEXT PRIMARY KEY,

    -- Ingestion timestamp: when the ingestor wrote this row to SQLite.
    -- Distinct from event_timestamp (the source event's own emission time).
    received_at TEXT NOT NULL DEFAULT (datetime('now', 'utc')),

    -- Top-level classifier fields extracted from native shape for fast filtering.
    -- These are duplicated from source_payload for query efficiency.
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,

    -- Full source payload: the entire event envelope JSON as emitted to the spool.
    -- This is the "native shape" preservation — do not normalize this column.
    -- Querying this column with JSON functions provides complete source fidelity.
    source_payload TEXT NOT NULL DEFAULT '{}',

    -- Extracted correlation ID components (promoted to top-level for indexing).
    -- In the current (pre-18.1.3) era, most of these come from the trace field
    -- of the source event. After Phase 18.1.3 (correlation ID infrastructure),
    -- all events will carry full correlation chains.
    --
    -- session_id: top-level field in CanonicalEventEnvelope
    session_id TEXT,
    -- project_id: top-level field in CanonicalEventEnvelope, or trace.project_id
    project_id TEXT,
    -- workflow_id: trace.workflow_id or trace.stream_id (workflow runner uses stream_id)
    workflow_id TEXT,
    -- skill_id: trace.skill_id or trace.skill_specifier (pre-18.1.3 events use specifier)
    skill_id TEXT,
    -- agent_id: trace.agent_id
    agent_id TEXT,
    -- hook_id: trace.hook_id
    hook_id TEXT,
    -- tool_id: trace.tool_id (individual tool call identity)
    tool_id TEXT,
    -- model_id: trace.model_id
    model_id TEXT,
    -- adapter_id: trace.adapter_id
    adapter_id TEXT,

    -- Composed correlation_id: colon-joined non-null IDs in canonical order.
    -- Format: "sess-{session_id}:wf-{workflow_id}:skill-{skill_id}:..."
    -- Only present components are included. NULL if no correlation context available.
    -- Used for cross-layer drill-down joins (raw ↔ canonical, raw ↔ L3).
    correlation_id TEXT
);

-- ── Indexes (Commitment 8: mandatory indexing for expected access patterns) ──

-- Individual correlation ID component lookups.
-- These support "give me all events for session X" or "find all hook-Y events" queries.
CREATE INDEX IF NOT EXISTS idx_raw_cce_session_id   ON raw_claude_code_events(session_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_project_id   ON raw_claude_code_events(project_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_workflow_id  ON raw_claude_code_events(workflow_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_skill_id     ON raw_claude_code_events(skill_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_agent_id     ON raw_claude_code_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_hook_id      ON raw_claude_code_events(hook_id);
CREATE INDEX IF NOT EXISTS idx_raw_cce_tool_id      ON raw_claude_code_events(tool_id);

-- Composed correlation_id: full chain drill-down from canonical to raw.
-- Primary join path for "given a canonical correlation_id, find all raw events".
CREATE INDEX IF NOT EXISTS idx_raw_cce_correlation_id ON raw_claude_code_events(correlation_id);

-- Temporal and type filtering (most common analytical query shapes).
CREATE INDEX IF NOT EXISTS idx_raw_cce_event_type    ON raw_claude_code_events(event_type);
CREATE INDEX IF NOT EXISTS idx_raw_cce_received_at   ON raw_claude_code_events(received_at);
CREATE INDEX IF NOT EXISTS idx_raw_cce_event_timestamp ON raw_claude_code_events(event_timestamp);

-- Compound: project × time — filters all events for a project in a time window.
CREATE INDEX IF NOT EXISTS idx_raw_cce_project_time ON raw_claude_code_events(project_id, received_at);

-- Compound: type × time — dashboard/monitoring queries ("all skill.invoked in last 7 days").
CREATE INDEX IF NOT EXISTS idx_raw_cce_type_time ON raw_claude_code_events(event_type, received_at);

-- Compound: session × event_type — drill-down within a session by event category.
CREATE INDEX IF NOT EXISTS idx_raw_cce_session_type ON raw_claude_code_events(session_id, event_type);
