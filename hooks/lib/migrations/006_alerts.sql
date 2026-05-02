-- Migration 006: Alert system tables

-- Alert rule definitions for real-time monitoring
CREATE TABLE IF NOT EXISTS alert_rules (
    rule_id TEXT PRIMARY KEY,
    rule_name TEXT NOT NULL,
    metric_path TEXT NOT NULL,      -- Path to metric being monitored (e.g., 'skill.success_rate', 'api.latency_p95')
    condition TEXT NOT NULL,         -- Comparison operator: 'gt', 'lt', 'eq', 'gte', 'lte'
    threshold REAL,                  -- Threshold value to trigger alert
    severity TEXT,                   -- Alert severity: 'info', 'warning', 'critical'
    enabled BOOLEAN DEFAULT 1        -- Whether rule is active
);

-- Alert trigger history and resolution tracking
CREATE TABLE IF NOT EXISTS alert_history (
    alert_id TEXT PRIMARY KEY,
    rule_id TEXT,
    triggered_at TEXT NOT NULL,
    metric_value REAL,               -- Actual metric value when alert triggered
    severity TEXT,                   -- Severity at time of trigger (captured for historical analysis)
    resolved_at TEXT,                -- When alert was resolved/acknowledged
    FOREIGN KEY (rule_id) REFERENCES alert_rules(rule_id)
);

-- Indexes for efficient alert querying
CREATE INDEX IF NOT EXISTS idx_alert_rules_enabled ON alert_rules(enabled, severity);
CREATE INDEX IF NOT EXISTS idx_alert_history_triggered ON alert_history(triggered_at, resolved_at);
CREATE INDEX IF NOT EXISTS idx_alert_history_rule ON alert_history(rule_id, triggered_at);
