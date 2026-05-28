-- Migration 011: Create memory_entries table.
-- Previously created at startup by core/memory/store.py; moved to migration
-- so fresh databases work. IF NOT EXISTS is intentional: existing DBs that had
-- the table created by application code before this migration was added will
-- skip the CREATE without error.

CREATE TABLE IF NOT EXISTS memory_entries (
    memory_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    category TEXT NOT NULL,
    content TEXT NOT NULL,
    metadata JSON,
    importance REAL NOT NULL DEFAULT 0.5,
    created_at TEXT NOT NULL,
    last_accessed TEXT,
    access_count INTEGER NOT NULL DEFAULT 0,
    tags TEXT,
    project TEXT,
    skill TEXT
);

CREATE INDEX IF NOT EXISTS idx_memory_source
ON memory_entries(source);

CREATE INDEX IF NOT EXISTS idx_memory_category
ON memory_entries(category);

CREATE INDEX IF NOT EXISTS idx_memory_project
ON memory_entries(project);

CREATE INDEX IF NOT EXISTS idx_memory_importance
ON memory_entries(importance DESC);
