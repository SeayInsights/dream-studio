-- Migration 031: Decision log and causal link tables
-- Enables structured decision transparency and event-decision linking

-- Decision log table
CREATE TABLE IF NOT EXISTS decision_log (
    decision_id TEXT PRIMARY KEY,
    decision_type TEXT NOT NULL,
    context TEXT,              -- JSON
    outcome TEXT,              -- JSON
    reasoning TEXT NOT NULL,   -- JSON
    confidence REAL,
    policy_applied TEXT,
    source_subsystem TEXT,
    timestamp TEXT NOT NULL
);

-- Decision-Event causal link table
CREATE TABLE IF NOT EXISTS decision_event_link (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    decision_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,  -- "caused_by", "triggered", "influenced"
    FOREIGN KEY (decision_id) REFERENCES decision_log(decision_id)
);

-- Indexes for query performance
CREATE INDEX IF NOT EXISTS idx_decision_type ON decision_log(decision_type);
CREATE INDEX IF NOT EXISTS idx_decision_subsystem ON decision_log(source_subsystem);
CREATE INDEX IF NOT EXISTS idx_decision_timestamp ON decision_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_decision_confidence ON decision_log(confidence);

CREATE INDEX IF NOT EXISTS idx_link_decision ON decision_event_link(decision_id);
CREATE INDEX IF NOT EXISTS idx_link_event ON decision_event_link(event_id);
CREATE INDEX IF NOT EXISTS idx_link_relation ON decision_event_link(relation_type);
