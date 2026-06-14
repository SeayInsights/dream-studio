-- Add file store pointer columns to raw_handoffs.
-- file_id references ds_files.file_id in files.db (cross-store FK, not enforced by SQLite).
-- checksum is SHA-256 of the content blob for integrity verification.
-- Both columns are nullable — existing rows and rows from producers not yet wired get NULL.
ALTER TABLE raw_handoffs ADD COLUMN file_id TEXT;
ALTER TABLE raw_handoffs ADD COLUMN checksum TEXT;
