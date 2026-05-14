-- Migration 034: Execution Graph Layer (promoted from legacy 003)
-- Created: 2026-05-07, promoted: 2026-05-09
-- Phase 3: Persistent DAG for all execution (project → prd → plan → phase → wave → task)

-- ============================================================================
-- EXECUTION NODES - Core DAG structure
-- ============================================================================

CREATE TABLE IF NOT EXISTS execution_nodes (
    -- Identity
    node_id TEXT PRIMARY KEY,
    node_type TEXT NOT NULL CHECK(node_type IN (
        'project', 'prd', 'plan', 'phase', 'wave', 'task'
    )),
    parent_id TEXT,  -- NULL for root nodes (projects)

    -- Hierarchy
    project_id TEXT,  -- Denormalized for fast filtering
    prd_id TEXT,
    plan_id TEXT,
    phase_id TEXT,
    wave_id TEXT,

    -- Content
    title TEXT NOT NULL,
    description TEXT,
    metadata JSON,  -- Flexible storage for node-specific data

    -- Context (what this node was given)
    context_hash TEXT,  -- SHA256 of input context
    context_summary TEXT,  -- Human-readable summary
    context_tokens INTEGER,  -- Token count

    -- State
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN (
        'pending', 'active', 'blocked', 'completed', 'failed', 'skipped'
    )),
    priority INTEGER DEFAULT 0,

    -- Timing
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    duration_seconds REAL,

    -- Relationships
    FOREIGN KEY (parent_id) REFERENCES execution_nodes(node_id),
    FOREIGN KEY (project_id) REFERENCES execution_nodes(node_id),
    FOREIGN KEY (prd_id) REFERENCES execution_nodes(node_id),
    FOREIGN KEY (plan_id) REFERENCES execution_nodes(node_id),
    FOREIGN KEY (phase_id) REFERENCES execution_nodes(node_id),
    FOREIGN KEY (wave_id) REFERENCES execution_nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_execution_nodes_parent ON execution_nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_execution_nodes_project ON execution_nodes(project_id);
CREATE INDEX IF NOT EXISTS idx_execution_nodes_status ON execution_nodes(status);
CREATE INDEX IF NOT EXISTS idx_execution_nodes_type ON execution_nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_execution_nodes_created ON execution_nodes(created_at);


-- ============================================================================
-- EXECUTION DEPENDENCIES - DAG edges
-- ============================================================================

CREATE TABLE IF NOT EXISTS execution_dependencies (
    -- Identity
    dependency_id TEXT PRIMARY KEY,
    source_node_id TEXT NOT NULL,  -- Node that depends
    target_node_id TEXT NOT NULL,  -- Node that is depended on
    dependency_type TEXT NOT NULL CHECK(dependency_type IN (
        'blocks',      -- Source is BLOCKED by target (hard dependency)
        'informs',     -- Source is INFORMED by target (soft dependency)
        'follows'      -- Source FOLLOWS target (ordering only)
    )),

    -- Metadata
    reason TEXT,  -- Why this dependency exists
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (source_node_id) REFERENCES execution_nodes(node_id),
    FOREIGN KEY (target_node_id) REFERENCES execution_nodes(node_id),
    UNIQUE(source_node_id, target_node_id, dependency_type)
);

CREATE INDEX IF NOT EXISTS idx_execution_deps_source ON execution_dependencies(source_node_id);
CREATE INDEX IF NOT EXISTS idx_execution_deps_target ON execution_dependencies(target_node_id);
CREATE INDEX IF NOT EXISTS idx_execution_deps_type ON execution_dependencies(dependency_type);


-- ============================================================================
-- EXECUTION OUTPUTS - What each node produced
-- ============================================================================

CREATE TABLE IF NOT EXISTS execution_outputs (
    -- Identity
    output_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    output_type TEXT NOT NULL CHECK(output_type IN (
        'code',        -- Code files generated
        'document',    -- Documentation produced
        'decision',    -- Decision made
        'artifact',    -- Other artifact
        'result'       -- Execution result
    )),

    -- Content
    output_hash TEXT,  -- SHA256 of output content
    output_summary TEXT,  -- Human-readable summary
    output_data JSON,  -- Structured output data
    file_paths TEXT,  -- Newline-separated list of file paths
    tokens_produced INTEGER,  -- Token count of output

    -- Metadata
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (node_id) REFERENCES execution_nodes(node_id)
);

CREATE INDEX IF NOT EXISTS idx_execution_outputs_node ON execution_outputs(node_id);
CREATE INDEX IF NOT EXISTS idx_execution_outputs_type ON execution_outputs(output_type);
CREATE INDEX IF NOT EXISTS idx_execution_outputs_created ON execution_outputs(created_at);


-- ============================================================================
-- EXECUTION EVENTS - Link canonical events to graph nodes
-- ============================================================================

CREATE TABLE IF NOT EXISTS execution_event_links (
    link_id TEXT PRIMARY KEY,
    node_id TEXT NOT NULL,
    event_id TEXT NOT NULL,  -- Links to canonical_events.event_id
    created_at TEXT NOT NULL DEFAULT (datetime('now')),

    FOREIGN KEY (node_id) REFERENCES execution_nodes(node_id),
    UNIQUE(node_id, event_id)
);

CREATE INDEX IF NOT EXISTS idx_execution_event_links_node ON execution_event_links(node_id);
CREATE INDEX IF NOT EXISTS idx_execution_event_links_event ON execution_event_links(event_id);


-- ============================================================================
-- VIEWS - Convenient queries
-- ============================================================================

-- Active execution tree (what's currently running)
CREATE VIEW IF NOT EXISTS v_active_execution AS
SELECT
    node_id,
    node_type,
    title,
    status,
    started_at,
    (julianday('now') - julianday(started_at)) * 24 * 60 as runtime_minutes
FROM execution_nodes
WHERE status = 'active'
ORDER BY started_at ASC;

-- Blocked nodes (what's waiting)
CREATE VIEW IF NOT EXISTS v_blocked_nodes AS
SELECT
    en.node_id,
    en.node_type,
    en.title,
    en.status,
    COUNT(ed.dependency_id) as blocking_count
FROM execution_nodes en
JOIN execution_dependencies ed ON en.node_id = ed.source_node_id
JOIN execution_nodes blocker ON ed.target_node_id = blocker.node_id
WHERE en.status = 'blocked'
  AND blocker.status != 'completed'
  AND ed.dependency_type = 'blocks'
GROUP BY en.node_id
ORDER BY blocking_count DESC;

-- Node completion rate by type
CREATE VIEW IF NOT EXISTS v_completion_rate AS
SELECT
    node_type,
    COUNT(*) as total,
    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
    ROUND(100.0 * SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) / COUNT(*), 1) as completion_pct
FROM execution_nodes
GROUP BY node_type;
