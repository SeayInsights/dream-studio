-- Migration 013: Discovery System Tables
-- Created: 2026-05-05
-- Purpose: Add tool registry and research cache tables for unified-discovery system
-- FR-001 from unified-discovery spec

-- ============================================================================
-- DISCOVERY SYSTEM SCHEMA
-- ============================================================================

-- 1. Tool Registry (External discovery)
CREATE TABLE IF NOT EXISTS tool_registry (
    tool_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,               -- 'mcp' | 'python_package' | 'api' | 'saas'
    description TEXT,
    source_url TEXT,
    install_command TEXT,
    tags TEXT,                             -- JSON array: ["video", "processing", "ffmpeg"]
    confidence_score REAL DEFAULT 0.5,     -- 0.0-1.0
    last_verified_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

-- 2. Research Cache (Web research)
CREATE TABLE IF NOT EXISTS research_cache (
    cache_id TEXT PRIMARY KEY,
    topic TEXT NOT NULL,
    focus_areas TEXT,                      -- JSON array
    sources TEXT,                          -- JSON array of {url, title, summary, tier}
    findings TEXT,                         -- Markdown summary
    confidence_score REAL,                 -- 0.0-1.0
    triangulation_score REAL,              -- 0.0-1.0 (based on source count)
    created_at TEXT DEFAULT (datetime('now')),
    expires_at TEXT                        -- datetime('now', '+30 days')
);

-- ============================================================================
-- INDEXES FOR PERFORMANCE
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_tool_category ON tool_registry(category);
CREATE INDEX IF NOT EXISTS idx_tool_tags ON tool_registry(tags);
CREATE INDEX IF NOT EXISTS idx_research_topic ON research_cache(topic);
CREATE INDEX IF NOT EXISTS idx_research_expires ON research_cache(expires_at);

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- Next steps:
-- 1. Implement discovery service in hooks/lib/discovery_service.py
-- 2. Integrate with mcp_router for tool recommendation
-- 3. Add web research capability for cache population
