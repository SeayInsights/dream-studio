-- Migration 014: Graph Analysis Views
-- Created: 2026-05-05
-- Purpose: Create unified graph views for dependency analysis (FR-001 from unified-discovery spec)
-- Depends on: pi_components, pi_dependencies, reg_sessions tables

-- ============================================================================
-- GRAPH ANALYSIS VIEWS
-- ============================================================================

-- Unified graph edges view
-- Combines component dependencies and project-session relationships into a single graph structure
CREATE VIEW IF NOT EXISTS vw_graph_edges AS
SELECT
    'component' AS edge_type,
    source_component_id AS source_id,
    target_component_id AS target_id,
    'depends_on' AS relationship
FROM pi_dependencies
UNION ALL
SELECT
    'project_session' AS edge_type,
    project_id AS source_id,
    session_id AS target_id,
    'has_session' AS relationship
FROM reg_sessions;

-- Component statistics view (for graph analysis)
-- Calculates incoming/outgoing edges and centrality score for each component
CREATE VIEW IF NOT EXISTS vw_component_stats AS
SELECT
    c.component_id,
    COUNT(DISTINCT incoming.source_component_id) AS incoming_edges,
    COUNT(DISTINCT outgoing.target_component_id) AS outgoing_edges,
    (COUNT(DISTINCT incoming.source_component_id) + COUNT(DISTINCT outgoing.target_component_id)) AS centrality_score
FROM pi_components c
LEFT JOIN pi_dependencies incoming ON c.component_id = incoming.target_component_id
LEFT JOIN pi_dependencies outgoing ON c.component_id = outgoing.source_component_id
GROUP BY c.component_id;
