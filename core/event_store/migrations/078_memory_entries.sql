-- Migration 078: Retained no-op guard for memory_entries table.
-- The canonical CREATE is at 011_memory_entries.sql (restored 2026-05-28).
-- This migration was briefly used as the sole source of the table creation
-- after 011 was renamed; 011 is now restored and this is a safe no-op.
-- IF NOT EXISTS means this is harmless on any DB state.

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
