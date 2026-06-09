-- Migration 107: Preflight findings layer.
--
-- preflight_events: append-only self-nesting event spine for pre-execution findings.
-- business_work_order_preflights: read-model folded from the spine by PreflightProjection.

CREATE TABLE IF NOT EXISTS preflight_events (
    event_id        TEXT PRIMARY KEY,
    parent_event_id TEXT REFERENCES preflight_events(event_id),
    work_order_id   TEXT NOT NULL,
    correlation_id  TEXT,
    event_kind      TEXT NOT NULL CHECK (event_kind IN ('preflight.created', 'preflight.status_changed')),
    finding_type    TEXT CHECK (finding_type IN ('blast_radius', 'impact', 'risk', 'spec_reference', 'dependency')),
    source          TEXT,
    severity        TEXT CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
    summary         TEXT,
    body            TEXT,
    author_type     TEXT,
    status          TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Read-model: one row per finding, current status from latest status_changed.
CREATE TABLE IF NOT EXISTS business_work_order_preflights (
    finding_id          TEXT PRIMARY KEY,
    work_order_id       TEXT NOT NULL,
    correlation_id      TEXT,
    finding_type        TEXT,
    source              TEXT,
    severity            TEXT,
    summary             TEXT,
    body                TEXT,
    author_type         TEXT,
    status              TEXT NOT NULL DEFAULT 'open',
    last_status_event_id TEXT,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_preflight_events_work_order
    ON preflight_events (work_order_id, event_kind, created_at);

CREATE INDEX IF NOT EXISTS idx_preflight_events_parent
    ON preflight_events (parent_event_id)
    WHERE parent_event_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_wo_preflights_work_order
    ON business_work_order_preflights (work_order_id, severity, status);
