-- Migration 105: Add cache_read_tokens to token_usage_records.
--
-- The cached_tokens column (added in migration 037) was ambiguous — it conflated
-- cache creation and cache read. This column adds an explicit cache_read_tokens
-- counter so prompt-caching effectiveness can be tracked separately.
--
-- Intelligence routes query this column to surface cache-hit wins in the
-- token intelligence panel (see projections/api/routes/intelligence.py).
--
-- Default 0: existing rows have no cache_read data so they remain at 0.

ALTER TABLE token_usage_records ADD COLUMN cache_read_tokens INTEGER NOT NULL DEFAULT 0;
