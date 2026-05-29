# Aspirational Schema Debt

This document tracks schema-coherence issues where code references schema that
doesn't exist yet (or never will) in the migration sequence. These surface late
because SQLite and Python both allow forward references that compile successfully
but fail at runtime. Findings here feed directly into 18.4.6 (Aspirational Schema
Audit).

**Pattern name:** "Aspirational Schemas Surface Late" — schema references compile
without error but fail at runtime. Two directions:

- **Python → migration**: Python code references a column or table that exists
  in the Python schema model but is absent from migrations. Surfaces when a clean
  migration-only DB is queried. (See: migration 080 case.)
- **Migration → Python**: A migration creates schema (views, indexes, FKs) that
  references a table owned by Python's `_init_tables()`, not by any migration.
  Surfaces the same way. (This document's first entry.)

---

## Findings

### canonical_events — Python-owned table referenced by migration DDL

**Discovered:** 2026-05-28 during 18.4.2-followup-1 (PR #97) pre-push diligence

**Partial remediation (migration 081, Phase 18.4.5):** `vw_activity_timeline`
was permanently dropped in `081_cost_columns_numeric.sql` (Part 0 + Part 3) and
is NOT recreated. The view that triggered this finding is gone.

**Remaining debt:** `canonical_events` is still Python-owned (`EventStore._init_tables()`
at `core/event_store/event_store.py:97`) and is still referenced by 5 migrations:

| Migration | Reference type | Notes |
|-----------|---------------|-------|
| `052_invocation_mode.sql` | `ALTER TABLE canonical_events ADD COLUMN invocation_mode TEXT` | Swallowed: no such table |
| `060_ta0b_backfill_execution_events_from_canonical.sql` | `UPDATE canonical_events ...` | Swallowed |
| `061_backfill_sdlc_creation_events.sql` | `INSERT OR IGNORE INTO canonical_events (... raw_prompt_retained, raw_tool_output_retained, schema_version)` | Swallowed; see column-mismatch finding below |
| `062_nullify_activity_id_backfill_and_replace_views.sql` | 6× `INSERT OR IGNORE INTO canonical_events (... raw_prompt_retained, ...)` | Swallowed |
| `064_backfill_task_creation_events.sql` | `INSERT OR IGNORE INTO canonical_events (...)` | Swallowed |

**Symptom (structural):** On any migration-only DB, all 5 migration operations on
`canonical_events` fail silently (swallowed by `sqlite_bootstrap.py:116`). The
system works only because EventStore initializes after migrations.

**Audit detection:** `ds doctor` → `schema_coherence` check reports these as
`python_owned_table_in_migration` findings (severity: **medium**, scope: structural).

**Recommended remediation:**
- **Option A** — Move `canonical_events` DDL into a new migration (083+) with the
  full column set: 10 Python-declared cols + `raw_prompt_retained` +
  `raw_tool_output_retained` + `schema_version` + `invocation_mode` (added by 052).
  EventStore._init_tables changes to `CREATE TABLE IF NOT EXISTS` (harmless idempotent).
  Then remove the `canonical_events` entry from `sqlite_bootstrap.py:116`.
- **Option B** — Drop migration references to `canonical_events` (migrations
  052/060/061/062/064). The backfill data is already silently lost on fresh installs.
  Remove the `canonical_events` swallow entry afterward.

---

### canonical_events — column mismatch between migration INSERTs and Python DDL

**Discovered:** 2026-05-29 during 18.4.6 pre-flight

**Finding type:** `column_absent_from_python_ddl` (severity: **high**)

**Root cause:** Migrations 061, 062, and 064 insert into `canonical_events` with
columns `raw_prompt_retained`, `raw_tool_output_retained`, and `schema_version`.
`EventStore._init_tables()` creates `canonical_events` with only 10 columns — none
of these three. On upgrade paths from schema 58–62 where `canonical_events` already
exists from a prior EventStore initialization (10 cols), the INSERT fails with
`no such column: raw_prompt_retained` — an error the swallow handler does NOT catch.

**Audit detection:** `ds doctor` → `schema_coherence` reports as
`column_absent_from_python_ddl` (severity: high, scope: structural).

**Remediation:** Resolved by either Option A or Option B above (both cover the
column mismatch as a side effect).

---

### sqlite_bootstrap.py:116 — stale canonical_events swallow entry

**Discovered:** 2026-05-28, same diligence session as the canonical_events finding
**Updated:** 2026-05-29 during 18.4.6 pre-flight

**Location:** `core/config/sqlite_bootstrap.py` lines 116–122

**Status:** Stale. The `canonical_events` entry was added to handle
`vw_activity_timeline` creation failures in migration 062. That view was permanently
dropped in migration 081. The swallow now silently discards ALTER TABLE (migration 052)
and INSERT (migrations 060/061/062/064) failures. The handler believes it is catching
a view-creation error; no such view exists. This is a second-order aspirational-schema
instance: code believing something untrue about the schema it guards.

**Load-bearing:** Do not remove until the root cause is fixed (Option A or B above).
Removing the swallow without fixing the root cause would break fresh-install migration
runs — the ALTER/INSERT failures would become fatal.

**Audit detection:** `ds doctor` → `schema_coherence` reports as `stale_swallow`
(severity: medium, scope: structural).

**FTS/legacy entries are legitimate:** The `fts_gotchas`, `memory_entries`, and
`ds_documents` entries handle optional FTS modules and legacy-compat paths; those
are defensible graceful degradation and are classified as `legitimate` in the audit.
`canonical_events` alone is classified `stale`.

**Remediation:** Remove the `canonical_events` entry from the swallow handler after
applying Option A or Option B from the canonical_events finding above.

---

## Adjacent debt: ambiguous column naming

Not aspirational schema in the strict sense — these columns exist and are queryable.
But similar-sounding column names on the same table lead developers to query the
wrong one, producing the same "code believed something about schema that wasn't true"
failure mode. 18.4.6 should consider including this pattern in its audit scope.

### memory_entries.source vs memory_entries.source_type

**Discovered:** 2026-05-29 during 18.4.5-followup-1 pre-flight
**Symptom:** Pre-flight query used `WHERE source = 'reg_gotchas'` and returned 0 rows.
The correct column was `source_type = 'reg_gotchas'`. The design assumption
("1,488 orphans to dedup") was built on this misread — the D3 concern from
18.4.5 was based on a column confusion, not real data.

**Schema reality:**
- `source` (TEXT NOT NULL) — memory type taxonomy: 'gotcha', 'lesson', 'correction',
  'decision'. This is WHAT the memory IS. Set by ingestion consumers to describe
  the memory's category.
- `source_type` (TEXT, nullable) — provenance domain table: 'reg_gotchas',
  'raw_lessons', 'cor_skill_corrections'. This is WHERE the memory CAME FROM.
  Set by `upsert_by_provenance` as the idempotency key.

Both columns are nullable in the extended schema (source was NOT NULL in the
original 011 DDL; source_type was added by migration 032/080). Both have similar
names. Neither name strongly implies its semantic. A query for "all gotchas" works
on either column for the narrow case where source='gotcha' iff source_type='reg_gotchas'
— which is true today for GotchaIngestionConsumer but is not enforced and could
diverge as more consumers are added.

**Remediation options (18.4.6 to evaluate):**
1. Rename `source_type` to `provenance_table` or `ingestion_source`. Large blast
   radius: touches MemoryStore, ingestion consumers, FTS triggers, hook queries,
   and tests. A dedicated migration + global rename commit.
2. Add a CHECK constraint asserting the implied invariant (or document it in a
   schema comment migration). Cheap, no blast radius.
3. Add a docstring to MemoryStore and a comment to migration 032/080 explaining
   the semantic distinction. Cheapest; documents the debt without fixing it.

**18.4.6 audit scope decision:** The `source`/`source_type` ambiguity is adjacent
debt — columns exist and are queryable; no runtime failure. The 18.4.6 audit
(`schema_coherence` check) focuses on structural references that fail at runtime
(Python-owned tables, column mismatches). The column-naming pattern is out of scope
for the automated audit. Remediation options above remain open for a future WO.
