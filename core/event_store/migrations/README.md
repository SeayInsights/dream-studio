# Migration Sequence

Migrations are numbered `NNN_description.sql` and applied in ascending order by the runner in `core/config/sqlite_bootstrap.py`. Applied versions are tracked in the `_schema_version` table.

## Known Gaps

The following numbers are intentionally absent from the migration sequence. They were skipped during schema development and no files were ever created for them.

- **011** — Filled in 2026-05-24 by migration `011_memory_entries.sql` (was the gap that caused fresh-install BLOCKER; the table was previously created at application startup by `core/memory/store.py`). Briefly renamed to 078 during CI repair batch2 (2026-05-28); restored to 011 in batch3. Migration 078 is a retained no-op guard.
- **035** — Intentional skip. Number was reserved but never used; no migration was created or deleted.
- **036** — Intentional skip. Number was reserved but never used; no migration was created or deleted.

## Adding new migrations

1. Use the next sequential number (currently 072 as of 2026-05-24).
2. Name the file `NNN_short_description.sql`.
3. Every statement must end with `;`.
4. Prefer `CREATE TABLE IF NOT EXISTS` and `CREATE INDEX IF NOT EXISTS` for idempotent DDL.
5. `ALTER TABLE ... ADD COLUMN` is safe; SQLite does not support `IF NOT EXISTS` for it, but the runner skips `duplicate column name` errors.
6. Run the full migration regression test before pushing: `py -m pytest tests/integration/migrations/test_full_migration_sequence.py -v`
