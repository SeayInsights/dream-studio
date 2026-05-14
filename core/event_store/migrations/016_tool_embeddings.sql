-- Migration 016: Tool Embeddings Cache
-- Created: 2026-05-06
-- Purpose: Add embeddings cache for sentence-transformers semantic search
-- T146 from Phase 8 unified discovery system

-- ============================================================================
-- TOOL EMBEDDINGS CACHE
-- ============================================================================

-- Cache for tool description embeddings (sentence-transformers)
CREATE TABLE IF NOT EXISTS tool_embeddings_cache (
    tool_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,                 -- NumPy array serialized as bytes
    model_name TEXT NOT NULL,                -- e.g., 'all-MiniLM-L6-v2'
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (tool_id) REFERENCES tool_registry(tool_id) ON DELETE CASCADE
);

-- Index for model lookups (if we ever switch models)
CREATE INDEX IF NOT EXISTS idx_embeddings_model ON tool_embeddings_cache(model_name);

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- Next steps:
-- 1. Add build_embedding_index() to tool_search.py
-- 2. Implement semantic search with cosine similarity
-- 3. Keep TF-IDF as fallback
