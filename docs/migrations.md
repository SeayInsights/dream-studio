# Migrations & Rollbacks

Authority schema migrations are SQL files in `core/event_store/migrations/`, named
`NNN_short_description.sql` and applied in ascending order by the runner in
`core/config/sqlite_bootstrap.py` (applied versions are tracked in `_schema_version`).
The migration-by-migration history and the operator-approved 142 baseline squash are
documented in [`MIGRATION_AUTHORITY.md`](./MIGRATION_AUTHORITY.md) and the
[migrations README](../core/event_store/migrations/README.md).

## Reversible migrations (rollback pairing)

Every forward migration must be **reversible**: it ships a paired reverse under
`core/event_store/migrations/rollback/` with the same `NNN_` number, undoing exactly
what the forward migration did — drop what it created, recreate/restore what it
dropped or altered. The reverse is authored by hand (SQLite has no automatic down
migrations) and is not applied by the bootstrap runner; it is the reviewed,
version-controlled recovery path for a schema change that must be backed out.

Guidelines for a reverse migration:

- Mirror the forward file's number and description: `rollback/NNN_description.sql`.
- Reverse each statement: `CREATE TABLE` → `DROP TABLE IF EXISTS`; `ADD COLUMN` →
  rebuild-without-column (SQLite cannot `DROP COLUMN` on older engines) or document
  that the column is left in place as a no-op; `DROP` of a table with data → recreate
  the table's DDL (data is not recoverable from the migration alone — note that).
- Prefer idempotent, `IF EXISTS`/`IF NOT EXISTS` DDL so a partial rollback re-runs
  cleanly.

The same convention applies in spirit to **Python DDL sites** (`event_store.py`
`_init_tables()`): a schema object those create should have a documented reverse in
the paired rollback file for the migration that introduced the dependency.

## Grandfather cutover: migration 154

Pairing is **enforced from migration 154 onward**. Migrations `<= 153` are
grandfathered and intentionally have no rollbacks, for three reasons:

1. They predate this convention.
2. The chain is anchored by `142_lean_baseline.sql`, an operator-approved
   **irreversible** squash of migrations 001–141 (see the migrations README) — there
   is no meaningful reverse for the baseline.
3. Several post-baseline migrations are `DROP`s of dead, permanently-empty tables
   (147–151); their only possible reverse would recreate an empty tombstoned table,
   which is worse than leaving it dropped.

Authoring 11 low-value or impossible reverses for the grandfathered range would add
risk without buying real reversibility, so the cutover starts at the next new
migration. Change `ROLLBACK_ENFORCED_FROM` in
`core/gates/migration_rollback_pairing.py` only with a documented rationale.

## Enforcement

`core/gates/migration_rollback_pairing.py::find_unpaired_migrations()` lists any
forward migration `>= 154` missing a paired reverse. It is invoked by the
`migration-risk` pre-push gate (`core/gates/migration_risk.py`) on any
migration-touching push, and fails the push (hard — `MIGRATION_RISK_ACKNOWLEDGED`
does not bypass it) until the reverse is added. Regression test:
`tests/unit/test_migration_rollback_pairing.py`.
