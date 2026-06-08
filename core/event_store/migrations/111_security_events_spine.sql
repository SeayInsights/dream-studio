-- Migration 111: Findings event spines — security_events + readiness_events
--
-- Adds two self-nesting append-only event spines for security and readiness
-- findings (AD-10). Peers to execution_events (migration 037). Status is NOT
-- a column — it is an event (finding.status_changed). Current status is a
-- projection over spine history.
--
-- security_events: SAST/DAST/SCA/secrets findings
-- readiness_events: control-framework assessment results
--
-- Both spines are strictly append-only. Rows are never updated after INSERT.

-- ── security_events ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS security_events (
    event_id          TEXT PRIMARY KEY,
    parent_event_id   TEXT REFERENCES security_events(event_id),
    event_kind        TEXT NOT NULL,    -- finding.recorded | finding.status_changed | finding.resolved | scan_run.started
    correlation_id    TEXT,             -- → ai_canonical_events skill run that produced it
    project_id        TEXT,
    work_order_id     TEXT,
    scanner_type      TEXT,             -- SAST | DAST | SCA | secrets
    cwe_id            TEXT,
    owasp_category    TEXT,
    cve_id            TEXT,
    file_path         TEXT,
    line_number       INTEGER,
    vuln_class        TEXT,             -- injection | auth | crypto | ...
    exploitability    TEXT,             -- critical | high | medium | low | info
    severity          TEXT,             -- critical | high | medium | low | info
    title             TEXT,
    body              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

CREATE INDEX IF NOT EXISTS idx_security_events_project
ON security_events(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_events_parent
ON security_events(parent_event_id);

CREATE INDEX IF NOT EXISTS idx_security_events_kind
ON security_events(event_kind, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_security_events_severity
ON security_events(project_id, severity, event_kind);

-- ── readiness_events ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS readiness_events (
    event_id          TEXT PRIMARY KEY,
    parent_event_id   TEXT REFERENCES readiness_events(event_id),
    event_kind        TEXT NOT NULL,    -- assessment.started | control_result.recorded | control_result.status_changed | assessment.closed
    correlation_id    TEXT,             -- → ai_canonical_events skill run that produced it
    project_id        TEXT,
    work_order_id     TEXT,
    framework         TEXT,             -- SOC2 | NIST | ISO27001 | custom
    control_id        TEXT,
    result            TEXT,             -- pass | fail | na | incomplete
    evidence          TEXT,
    remediation_wo    TEXT,             -- → business_work_orders(work_order_id)
    title             TEXT,
    body              TEXT,
    created_at        TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

CREATE INDEX IF NOT EXISTS idx_readiness_events_project
ON readiness_events(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_readiness_events_parent
ON readiness_events(parent_event_id);

CREATE INDEX IF NOT EXISTS idx_readiness_events_kind
ON readiness_events(event_kind, project_id);

-- ── findings_current_status projection table ──────────────────────────────────
-- Materialized by FindingsProjection; rebuilt from security_events history.
-- NOT a canonical authority — derived read-model only.

CREATE TABLE IF NOT EXISTS findings_current_status (
    finding_id            TEXT PRIMARY KEY, -- = security_events.event_id of the finding.recorded event
    project_id            TEXT,
    work_order_id         TEXT,
    severity              TEXT,
    title                 TEXT,
    file_path             TEXT,
    line_number           INTEGER,
    scanner_type          TEXT,
    current_status        TEXT NOT NULL DEFAULT 'open',  -- open | mitigated | false_positive | accepted | resolved
    last_status_event_id  TEXT,           -- = event_id of latest finding.status_changed / finding.resolved
    created_at            TEXT NOT NULL,
    updated_at            TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_findings_current_status_project
ON findings_current_status(project_id, current_status);

CREATE INDEX IF NOT EXISTS idx_findings_current_status_severity
ON findings_current_status(project_id, severity, current_status);
