-- Migration 126: ds_escalations — per-work-order escalation ladder state.
--
-- WO-ESCALATION-LADDER. When the deterministic verifier/outcome-eval says a WO is
-- NOT FIXED after close, the platform reopens it and escalates: the retry is routed
-- to a more capable model (Opus) and retries are capped before handing back to the
-- operator. This state is operational SDLC metadata, not business-entity state, so it
-- lives in its own table keyed by work_order_id rather than as columns on
-- business_work_orders (keeps the business entity clean — dependency Rule 3).
--
-- Migration class: routine (additive table create; no DDL on existing tables).
CREATE TABLE IF NOT EXISTS ds_escalations (
    work_order_id TEXT PRIMARY KEY,
    -- How many times this WO has been escalated (reopened-as-not-fixed).
    escalation_level INTEGER NOT NULL DEFAULT 0,
    -- How many retry attempts have been registered against the current escalation.
    retry_count INTEGER NOT NULL DEFAULT 0,
    -- Capability flag the retry must honor; e.g. 'opus'. NULL = default routing.
    designated_executor TEXT,
    -- Last escalation reason (deterministic not-fixed reasons, joined).
    last_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);
