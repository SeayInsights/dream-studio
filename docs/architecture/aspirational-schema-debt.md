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

### canonical_events — REMEDIATED (18.4.6-followup-1, migration 083)

**Remediated:** 2026-05-29 via PR #105 (migration 083).

**Option chosen:** Option A — moved canonical_events DDL into migration 083 with the
authoritative 14-column schema from `spool/ingestor.py:_write_to_sqlite`.

**What changed:**
- `core/event_store/migrations/083_canonical_events_migration_authority.sql`: declares canonical_events with 14 columns (CREATE TABLE IF NOT EXISTS — safe no-op on live upgrade)
- `core/event_store/event_store.py:_init_tables`: aligned to 14-column schema, now an idempotent fallback
- `core/config/schema_coherence.py`: canonical_events removed from `_PYTHON_OWNED_TABLES`; canonical_events swallow reclassified from "stale" to "legitimate" (intentional graceful degradation for migrations 052-064 that predate 083)
- `core/config/sqlite_bootstrap.py`: swallow comment updated to document intentional status

**Audit verification:** After migration 083, `ds doctor schema_coherence` reports:
- 0 `python_owned_table_in_migration` for canonical_events (was 5 medium)
- 0 `column_absent_from_python_ddl` (was 3 high)
- 0 `stale_swallow` (was 1 medium)
- Status: `low_findings` (only proj_* no-migration-ref lows remain, unchanged)

**Remaining structural note:** The swallow for `canonical_events` in sqlite_bootstrap.py:116
is intentionally retained. Migrations 052-064 still run before migration 083 in the sequence
and still fail with "no such table: canonical_events" on fresh installs. The swallow handles
these gracefully. Removing it would require superseding migrations 052-064.

---

### canonical_events — HISTORY (pre-remediation finding)

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

### sqlite_bootstrap.py:116 — canonical_events swallow (RECLASSIFIED to legitimate)

**Discovered:** 2026-05-28 as stale; **reclassified:** 2026-05-29 (18.4.6-followup-1)

**Location:** `core/config/sqlite_bootstrap.py` lines 116–122

**Status after remediation:** Legitimate intentional graceful degradation.
Migration 083 creates canonical_events at position 83, but migrations 052-064 run before it
in the sequence and still fail with "no such table: canonical_events" on fresh installs.
The swallow correctly handles these failures — it is no longer stale.

**Why it stays:** Removing the swallow would cause migrations 052-064 to fail fatally
on fresh installs. They would need to be superseded to make the swallow removable.
This is a separate WO if/when those migrations are ever retired.

**Audit status:** `schema_coherence` now classifies this entry as `legitimate` and does
not report it as a finding.

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

---

## Closed instance: coherence checks satisfiable by relabeling (the Phase 18.4 meta-pattern)

**Discovered:** 2026-05-29 post-merge of PR #105, during 18.4.6-followup-1-postmerge coherence audit.
**Fixed:** PR #106 (`_effective_swallow_classification()` in `core/config/schema_coherence.py`).
**Cross-reference:** `.planning/workstreams/18-4-consolidation/coupling-map-audit.md` documents the same pattern in the docs-drift gate.

**What happened:**

PR #105 (migration 083) reclassified the canonical_events swallow entry in `_SWALLOW_INVENTORY` from `"classification": "stale"` to `"classification": "legitimate"`. The `schema_coherence` audit's `stale_swallow` finding immediately cleared — the headline "9 → 0 findings" was true, but the Q2 post-merge audit revealed that the finding cleared *because a string changed*, not because the audit probed whether the underlying condition had actually changed.

The `stale_swallow` detection at the time was:
```python
for entry in _SWALLOW_INVENTORY:
    if entry["classification"] == "stale":
        findings.append(...)
```

This is a label-based check. Editing `"stale"` → `"legitimate"` silences the finding regardless of whether anything in the schema changed. The reclassification was factually correct (canonical_events IS now in `migration_tables` after migration 083), but the audit couldn't verify it — it just believed the label.

**The fix:**

`_effective_swallow_classification()` (PR #106) probes `migration_tables` for "no such table: X" patterns and overrides the hardcoded label with real evidence:
- If X is in `migration_tables` → auto-classify as `"legitimate"` (table exists migration-side, sequencing issue)
- If X is not in `migration_tables` AND X is in `_PYTHON_OWNED_TABLES` → auto-classify as `"stale"` (Python-owned table, real debt)
- Otherwise → fall back to hardcoded classification

This makes the canonical_events swallow classification *self-verifying*: if migration 083 were removed, canonical_events would drop out of `migration_tables` and the finding would automatically return. The reclassification is locked by two regression tests that confirm the check cannot be silenced by relabeling alone.

**The meta-pattern:**

Phase 18.4 encountered this same failure mode across multiple systems. A coherence check enforces a *label* rather than a *condition*. The label can be edited to satisfy the check without changing reality. Instances:

1. **`stale_swallow` in `schema_coherence.py`** (this instance): fixed in PR #106.
2. **`<!-- Last reviewed ... -->` stamps in docs-drift domains**: the coupling map fires when certain source files change; the gate is satisfied by appending a `<!-- Last reviewed -->` comment to a doc regardless of whether the doc was actually reviewed. See `coupling-map-audit.md` for the over-broad source_patterns that cause this gate to fire on unrelated changes, training operators to paste boilerplate. (Narrowing the coupling map is 18.4-consolidation-followup-1.)

The pattern: **a check that enforces a label rather than a condition can be silenced by editing the label**. The fix is always the same — replace the label check with a probe of the underlying condition. For `stale_swallow`: probe `migration_tables`. For docs-drift stamps: narrow the source_patterns so the gate only fires on genuine dependencies, reducing the incentive to paste boilerplate.

**Status of the two instances:**
- Instance 1 (stale_swallow): CLOSED. Fixed in PR #106.
- Instance 2 (docs-drift stamp-traps): OPEN as O1 in the Phase 18.4 open-debt ledger. Narrowing is 18.4-consolidation-followup-1.

---

## Live mechanism: swallowed migration statements (silent schema loss)

**Discovered:** 2026-05-29, divergence diagnosis (followup-2) + complete sweep (followup-2-close).
**Status:** OPEN as O7 in the Phase 18.4 open-debt ledger (Medium priority, not an 18.5 blocker).
**Relation to Q2:** Same family — a signal that quietly stops meaning what it claims. Q2 was a check enforcing a label. This is a migration runner reporting "applied" while silently discarding the migration's effects.

**Mechanism:**

`sqlite_bootstrap.py`'s swallow handler catches "no such table" errors for covered tables (`memory_entries`, `canonical_events`, `fts_gotchas`, `ds_documents`, `ds_*`, `token_usage_records`, `ai_usage_operational_records`). The match is substring-based: `"memory_entries" in error_message`. When a migration statement references a covered table that is absent at run time — because it hasn't been created yet, was temporarily removed from the migration sequence, or the migration runner hasn't reached the table's own creating migration — the statement fails, the error is swallowed, and the migration is recorded as successfully applied in `_schema_version`. The statement's intended effect is silently discarded.

**Confirmed casualty:**

`idx_memory_lifecycle` (migration 032) — a non-unique index on `memory_entries(lifecycle_state)`.

Root cause chain: migration 011 (`011_memory_entries.sql`) was absent from the initial publication (2026-05-14) and was added on 2026-05-24. The live DB was created on 2026-05-16. When migration 032 ran on this DB, `memory_entries` did not exist — there was no migration to create it, only Python code (MemoryStore) which hadn't run yet. All of migration 032's statements failed with "no such table: memory_entries" and were swallowed. The index was never created. Memory_entries was later created by Python code and extended by migration 080, which does not declare `idx_memory_lifecycle`. Result: the column exists, the index does not.

**Complete sweep result (2026-05-29):**

A comprehensive diff of all 511 migration-declared objects against the live DB copy found `idx_memory_lifecycle` is the **only** swallowed-statement casualty on this DB. No other index, trigger, view, or table-column is missing because of M2. The mechanism's realized blast radius on this specific live DB is exactly one benign index on a 1,488-row table.

**Why it matters despite being benign:**

The schema_coherence audit compares Python-owned tables vs. migrations and checks column mismatches. It does NOT detect swallowed-statement casualties — objects a migration tried to create but the swallow handler silently discarded. The audit's foundational assumption (`_schema_version` says applied → migration took effect) is exactly what M2 violates. A swallowed index leaves no trace. The audit would report "clean" on a DB that is missing an arbitrary number of swallowed objects; you find the casualties only by diffing live vs. fresh.

This is the audit's documented blind spot. A future extension could add live-vs-fresh index and trigger comparison to the live-drift probe. This is not implemented.

**Relation to the swallow handler (N2):**

N2 in the ledger marks removal of the `canonical_events` swallow as intentionally-never (removing it would break fresh installs until migrations 052-064 are superseded). O7 reopens the narrowing question specifically: the `"memory_entries" in msg` pattern that swallowed migration 032 is a substring match that catches anything mentioning memory_entries — including CREATE INDEX statements on memory_entries that have nothing to do with the "graceful degradation for optional FTS module" intent. Narrowing from substring-match to table-and-statement-specific matching would prevent future M2 casualties without requiring migration supersession. This is a distinct operation from removal; N2's "never" applies to removal, not to narrowing.

**O7 RESOLVED (18.4-consolidation-followup-3):** The `"memory_entries"` substring swallow is narrowed. `CREATE INDEX` and `CREATE TRIGGER` on memory_entries now propagate; INSERT/UPDATE/ALTER TABLE/DROP still swallow. The change is in `core/config/sqlite_bootstrap.py` (S3b clause). Seam verification: all CREATE INDEX/TRIGGER on memory_entries are in migrations 032, 078, 079, 080, 082 — all run after migration 011 creates the table, so the propagation only fires on installations with a broken missing-011 state (which should surface).

**Audit blind spot CLOSED:** `check_schema_coherence()` now includes a direction-aware index/trigger diff in the live-drift probe. Objects present in a fresh migration-only DB but absent in the live DB are flagged as `swallowed_statement_casualty` (medium for non-unique indexes, high for UNIQUE indexes and triggers). The probe builds the migration inventory from the same migration-replay machinery as the structural checks. Verified: the live DB copy correctly reports `idx_memory_lifecycle` as the one medium casualty; a coherent DB reports zero casualties.

<!-- reviewed: 2026-05-30, migration 084 (project model unification A2). reg_projects deleted; business_projects is the sole project authority. Session hooks now use marker-based UUID resolution. No semantic changes to this document required. -->

<!-- reviewed: 2026-05-30, brownfield vertical slice migration 085. Stack profile + security_scan_runs. No semantic changes required to this document. -->
