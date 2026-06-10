-- Migration 116: Add acceptance_criteria column to business_tasks.
-- Non-breaking additive column (nullable, no default). Existing tasks are
-- unaffected. New tasks registered after this migration can include structured
-- criteria that the verifier checks specifically.
ALTER TABLE business_tasks ADD COLUMN acceptance_criteria TEXT;
