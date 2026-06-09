-- Migration 015: Performance Indexes
-- Created: 2026-05-06
-- Purpose: Add indexes to pi_components and pi_dependencies for fast graph queries
-- Phase 6 T125 from unified-discovery system

-- ============================================================================
-- PERFORMANCE INDEXES
-- ============================================================================

-- 1. Project component lookups (filters by project + component_type)
CREATE INDEX IF NOT EXISTS idx_pi_components_project ON pi_components(project_id, component_type);

-- 2. Dependency graph traversal (from → to)
CREATE INDEX IF NOT EXISTS idx_pi_dependencies_source ON pi_dependencies(from_component);

-- 3. Dependency graph traversal (to ← from)
CREATE INDEX IF NOT EXISTS idx_pi_dependencies_target ON pi_dependencies(to_component);

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- Expected performance improvement:
-- - Graph build time: 10k components in <2s (vs >10s without indexes)
-- - Query plan verification: EXPLAIN QUERY PLAN shows index usage
