-- Migration 069: business_work_orders — Phase 18.1.5
--
-- L3 business entity table: the projection-populated, v2-compliant structured
-- representation of work order state, derived from business_canonical_events.
--
-- Writer contract (Commitment 1 from data-model-v2.md):
--   This table is populated EXCLUSIVELY by WorkOrderProjection
--   (core/projections/work_order_projection.py).
--   Do NOT insert/update this table from CLI/API/hook/skill code.
--   Writers emit business canonical events; the projection writes here.
--
-- Relationship to ds_work_orders:
--   ds_work_orders is the current operational table (direct-write).
--   business_work_orders is the v2 projection-populated equivalent.
--   In Phase 18.6, ds_work_orders will be renamed to business_work_orders
--   after writer migration (Phase 18.2) converts all direct writers to
--   emit canonical events. Until then, both tables coexist.
--
-- Schema follows the placement rule: work orders are "planned and persistent"
-- → business domain. All columns are denormalized from canonical event payloads
-- for direct query access (no JSON extraction required for common queries).
--
-- Idempotent: safe to re-run; uses IF NOT EXISTS throughout.

CREATE TABLE IF NOT EXISTS business_work_orders (
    -- Identity: the work_order_id from the canonical event payload.
    work_order_id TEXT PRIMARY KEY,

    -- SDLC context (denormalized from canonical event payloads).
    project_id TEXT,
    milestone_id TEXT,
    title TEXT,

    -- State machine: created → in_progress → (blocked ↔ in_progress) → closed
    status TEXT NOT NULL DEFAULT 'created',

    -- Timestamps for each state transition (NULL until that transition occurs).
    created_at TEXT,
    started_at TEXT,
    closed_at TEXT,
    blocked_at TEXT,
    unblocked_at TEXT,

    -- Block reason (set on work_order.blocked, cleared on work_order.unblocked).
    block_reason TEXT,

    -- Canonical event provenance: tracks which events produced this row.
    -- source_event_id: the first canonical event that created this row.
    -- last_event_id: the most recent canonical event that updated this row.
    source_event_id TEXT,
    last_event_id TEXT,

    -- Housekeeping: when the projection last wrote this row.
    last_updated_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Access pattern indexes (Commitment 8: mandatory indexing).
-- Primary access patterns: by project, by status, by recency, by milestone.
CREATE INDEX IF NOT EXISTS idx_bwo_project_id
    ON business_work_orders(project_id);
CREATE INDEX IF NOT EXISTS idx_bwo_milestone_id
    ON business_work_orders(milestone_id);
CREATE INDEX IF NOT EXISTS idx_bwo_status
    ON business_work_orders(status);
CREATE INDEX IF NOT EXISTS idx_bwo_created_at
    ON business_work_orders(created_at);
CREATE INDEX IF NOT EXISTS idx_bwo_last_updated_at
    ON business_work_orders(last_updated_at);

-- Composite: active work orders per project (dashboard common query)
CREATE INDEX IF NOT EXISTS idx_bwo_project_status
    ON business_work_orders(project_id, status);
