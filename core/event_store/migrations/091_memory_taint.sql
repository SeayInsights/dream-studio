-- Migration 091: Add taint tracking columns to memory_entries.
--
-- Purpose: When a memory entry is extracted from a repo that had CRITICAL guard
-- findings, it may carry adversarial content that was designed to persist into
-- future LLM prompts (indirect injection via memory). Taint tracking:
--   1. source_repo_id: business_projects UUID of the source repo (if any)
--   2. tainted: 1 if a CRITICAL guard finding was logged against source_repo_id
--   3. taint_reason: description of why it was tainted
--   4. taint_timestamp: when the taint was applied
--
-- Memory entries from non-repo sources (manual, system) have:
--   source_repo_id = NULL, tainted = 0
--
-- on-memory-retrieve.py filters tainted=1 entries before surfacing into prompts.
--
-- NOTE: Inline -- comments intentionally on separate lines (not end-of-line)
-- to ensure the bootstrap runner's split_statements() parses each ALTER correctly.

ALTER TABLE memory_entries ADD COLUMN source_repo_id TEXT;

ALTER TABLE memory_entries ADD COLUMN tainted INTEGER NOT NULL DEFAULT 0;

ALTER TABLE memory_entries ADD COLUMN taint_reason TEXT;

ALTER TABLE memory_entries ADD COLUMN taint_timestamp TEXT;

CREATE INDEX IF NOT EXISTS idx_memory_tainted
ON memory_entries(tainted, project) WHERE tainted = 1;

CREATE INDEX IF NOT EXISTS idx_memory_source_repo
ON memory_entries(source_repo_id) WHERE source_repo_id IS NOT NULL;
