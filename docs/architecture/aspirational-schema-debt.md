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

### canonical_events — Python-owned table referenced by a migration-defined view

**Discovered:** 2026-05-28 during 18.4.2-followup-1 (PR #97) pre-push diligence

**Symptom:** `SELECT COUNT(*) FROM vw_activity_timeline` raises
`no such table: main.canonical_events` on any DB initialized through migrations
alone (without `EventStore` initialization).

**Root cause:** `canonical_events` is created by `EventStore._init_tables()` in
`core/event_store/event_store.py:97` — not by any migration. Migration 062
(`062_nullify_activity_id_backfill_and_replace_views.sql`) created
`vw_activity_timeline`, which queries `FROM canonical_events`. The view has been
unqueryable on migration-only DBs since migration 062, approximately 20 migrations
ago. No test or runtime reader has raised the failure because the exception handler
at `sqlite_bootstrap.py:120` silently swallows `OperationalError` where
`"no such table"` and `"canonical_events"` both appear in the message.

**Reproduction:** Build any DB via the migration runner alone (no `EventStore`
initialization). Query `SELECT COUNT(*) FROM vw_activity_timeline`. Error:
`no such table: main.canonical_events`.

**Inverse-of-080 pattern:** Migration 080 was Python code referencing schema absent
from migrations (forward reference in code). This is the mirror: a migration
creating schema that references a Python-owned table. Both are aspirational-schema
debt; both surface late; both are masked by silent-swallow patterns elsewhere in
the stack.

**Scope for 18.4.6:** The audit should detect both directions — scan migrations for
`FROM`/`JOIN`/`INTO` references to tables that appear in no `CREATE TABLE`
migration statement, then cross-reference against Python `_init_tables()` calls.
`canonical_events` should be the first hit.

**Recommended remediation (decision deferred to 18.4.6):**
- **Option A** — Move `canonical_events` into a migration (e.g., migration 082+).
  Note: EventStore's DDL for `canonical_events` lacks `raw_prompt_retained`,
  `raw_tool_output_retained`, and `schema_version` columns that migration 062's
  backfill assumed. A reconciliation migration would be needed.
- **Option B** — Drop `vw_activity_timeline`. The view has been silently broken for
  ~20 migrations with no identified runtime reader. Grep confirms no production
  call site queries it directly. Cheaper and verifiable.

---

### sqlite_bootstrap.py:120 — schema-error swallowing in migration runner

**Discovered:** 2026-05-28, same diligence session as above

**Location:** `core/config/sqlite_bootstrap.py` lines 116–122

**Current behavior:**
```python
if "no such table" in msg and (
    "fts_gotchas" in msg
    or "memory_entries" in msg
    or "ds_documents" in msg
    or "canonical_events" in msg
):
    continue
```

**Concern:** This swallows schema-coherence failures — missing tables that
migrations reference. It was added to handle graceful degradation for known-absent
optional tables (FTS modules, legacy tables). But applying it to `canonical_events`
hid the `vw_activity_timeline` breakage for ~20 migrations.

**Compare to the approved cq-006 pattern** (documented in
`docs/architecture/event-store-corruption-tolerance.md`): `studio_db.py` swallows
malformed event *payload* errors at ingest time — data is the unknown, and partial
writes are acceptable. That is appropriate graceful degradation. The
`sqlite_bootstrap.py:120` handler swallows schema *reference* errors — schema is
the contract, and a broken contract should surface. These two patterns are not
equivalent.

**FTS/legacy entries are legitimate:** The `fts_gotchas`, `memory_entries`, and
`ds_documents` entries in the list handle optional FTS modules and legacy-compat
paths. Those are defensible. `canonical_events` should be removed once the
remediation in the finding above is applied.

**Scope:** 18.4.6 follow-up, or its own small WO. Not blocking any current work.
After canonical_events is moved into migrations or the view is dropped, audit the
remaining entries to confirm each is optional-module graceful-degradation (as
intended) rather than schema-coherence masking.
