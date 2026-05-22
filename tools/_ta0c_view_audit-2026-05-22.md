# TA0c — View Audit & Dirty-DB State Report
**Date:** 2026-05-22  
**Scope:** Migration 062 broken-view problem, DB state after partial runs, path-forward options.

---

## 1. Current DB State

**Schema version:** 61 (migrations 062 and 063 not yet applied)

### 1a. Leftover `_new` tables from partial migration runs

| Table | Exists | Row count |
|---|---|---|
| `hook_executions_new` | **YES** | **0** (empty) |
| all others (`hook_findings_new`, etc.) | NO | — |

### 1b. Target table status (7 tables migration 062 will recreate)

| Table | Original exists | `_new` exists | `activity_id` nullable |
|---|---|---|---|
| `hook_executions` | YES | YES (empty) | NO — `notnull=1` |
| `hook_findings` | YES | NO | NO — `notnull=1` |
| `sec_sarif_findings` | YES | NO | NO — `notnull=1` |
| `sec_manual_reviews` | YES | NO | NO — `notnull=1` |
| `sec_cve_matches` | YES | NO | NO — `notnull=1` |
| `sec_hook_checks` | YES | NO | NO — `notnull=1` |
| `adapter_executions` | YES | NO | NO — `notnull=1` |

**Dirty state origin:** `hook_executions_new` exists because `CREATE TABLE` auto-commits in Python 3.12 sqlite3 (see §3). The INSERT + DROP TABLE that followed were in an implicit transaction that rolled back when `ALTER TABLE RENAME` failed. The table is empty — no data was ever durably written to it.

### 1c. Views currently in DB

All 12 remaining views are **queryable**. Three views were dropped by failed migration run attempts and have NOT been recreated:

| View | Status | Reason absent |
|---|---|---|
| `vw_graph_edges` | ABSENT | Dropped by `tmp_fix_db.py` cleanup script during debugging |
| `vw_component_stats` | ABSENT | Dropped by partial migration 062 run |
| `vw_guardrail_decisions` | ABSENT | Dropped by partial migration 062 run |

The 12 currently-present views and their queryability:

| View | Status |
|---|---|
| `effective_skill_runs` | OK |
| `v_active_execution` | OK |
| `v_blocked_nodes` | OK |
| `v_completion_rate` | OK |
| `vw_activity_timeline` | OK (still points to `activity_log`) |
| `vw_approach_patterns` | OK |
| `vw_hook_performance` | OK (references `hook_executions`) |
| `vw_prd_progress` | OK |
| `vw_project_readiness_latest` | OK |
| `vw_risk_hotspots` | OK (references `sec_sarif_findings`) |
| `vw_security_summary` | OK (references `sec_sarif_findings`) |
| `vw_task_details` | OK |

### 1d. Backfill progress

- `canonical_events` rows with `event_id LIKE 'backfill-activity-log-%'`: **0**
- `activity_log` rows remaining: **159**
- Migration 062 Part 3 (backfill INSERT OR IGNORE) has never executed.

---

## 2. Broken View Inventory

### 2a. `vw_graph_edges` — ABSENT, was broken

**Original DDL** (from `core/event_store/migrations/014_graph_views.sql`):
```sql
CREATE VIEW vw_graph_edges AS
SELECT
    'component' AS edge_type,
    source_component_id AS source_id,   -- WRONG: column is 'from_component'
    target_component_id AS target_id,   -- WRONG: column is 'to_component'
    'depends_on' AS relationship
FROM pi_dependencies
UNION ALL
SELECT
    'project_session' AS edge_type,
    project_id AS source_id,
    session_id AS target_id,
    'has_session' AS relationship
FROM reg_sessions;  -- WRONG: table never exists
```

**Two distinct breakages:**
1. `pi_dependencies` columns are `from_component` / `to_component` (migration 009), not `source_component_id` / `target_component_id` (migration 014 guessed wrong names).
2. `reg_sessions` table does not exist and has no SQL migration that creates it anywhere in the repo.

**Root cause:** Migration 014 (`014_graph_views.sql`, initial publication commit `790965e`) was written with assumed future column names and a `reg_sessions` table that was never built. `CREATE VIEW IF NOT EXISTS` does not validate referenced columns or tables in SQLite, so the view was silently accepted but has never been queryable.

**Production references:**
- `interfaces/cli/check_migrations.py:51` — checks whether `vw_graph_edges` exists (informational only)
- `interfaces/cli/verify_migrations.py:44,67` — explicitly lists it as **optional**, non-blocking if absent
- `tests/unit/test_native_readiness_gates.py:192` — asserts the "Optional legacy views missing: vw_graph_edges (non-blocking)" message appears

**Categorization: ORPHANED** — no production reader. The test explicitly expects it to be absent. `core/graph/query.py` queries `pi_dependencies` directly using correct column names (`from_component`/`to_component`), never via the view.

### 2b. `vw_component_stats` — ABSENT, was broken

**Original DDL** (from `core/event_store/migrations/014_graph_views.sql`):
```sql
CREATE VIEW vw_component_stats AS
SELECT
    c.component_id,
    COUNT(DISTINCT incoming.source_component_id) AS incoming_edges,  -- WRONG column
    COUNT(DISTINCT outgoing.target_component_id) AS outgoing_edges,  -- WRONG column
    (COUNT(DISTINCT incoming.source_component_id) + ...) AS centrality_score
FROM pi_components c
LEFT JOIN pi_dependencies incoming ON c.component_id = incoming.target_component_id  -- WRONG col
LEFT JOIN pi_dependencies outgoing ON c.component_id = outgoing.source_component_id  -- WRONG col
GROUP BY c.component_id;
```

**Breakage:** Same column-name mismatch as above. `pi_dependencies` has `from_component`/`to_component`, not `source_component_id`/`target_component_id`. All four column references in the view are wrong.

**Production references:** None found via `grep -rn "vw_component_stats" --include="*.py"`.

**Categorization: ORPHANED** — no production reader, no gate check. Can be permanently dropped.

### 2c. `vw_guardrail_decisions` — ABSENT, was broken

**Original DDL** (from `core/event_store/migrations/029_analytics_views.sql`):
```sql
CREATE VIEW vw_guardrail_decisions AS
SELECT
    gd.decision_id,
    gd.rule_id,
    gd.decision,         -- WRONG: column is 'action' in guardrail_decisions
    gd.event_id,
    al.activity_type,    -- from activity_log (TA0c target for retirement)
    al.event_timestamp,  -- from activity_log (TA0c target for retirement)
    gd.reason            -- WRONG: column is 'message' in guardrail_decisions
FROM guardrail_decisions gd
JOIN activity_log al ON gd.event_id = al.activity_id
ORDER BY al.event_timestamp DESC;
```

**Two distinct breakages:**
1. `guardrail_decisions` has columns `action` and `message`, not `decision` and `reason`.
2. The JOIN to `activity_log` is what TA0c is retiring — this view must be rewritten as part of migration 062 Part 2.

**Production references:**
- `interfaces/cli/create_refactor_issues.py:194,219` — GitHub issue text only (not a production query).

**Categorization: MUST REPLACE** — migration 062 Part 2 already has the corrected DDL:
```sql
CREATE VIEW vw_guardrail_decisions AS
SELECT decision_id, rule_id, action AS decision, event_id,
       evaluated_at AS event_timestamp, message AS reason
FROM guardrail_decisions
ORDER BY evaluated_at DESC;
```

---

## 3. ALTER TABLE RENAME — View Recompilation Problem

### 3a. Why SQLite recompiles ALL views on RENAME

SQLite's `ALTER TABLE RENAME` updates the `sqlite_master` entry for the renamed table and scans **all** views (and triggers) in the schema to rewrite any that reference the old table name. During this scan SQLite **recompiles every view** — not just those that reference the renamed table. If any view fails to compile (missing table, missing column), the entire RENAME aborts with an `OperationalError`.

This is documented SQLite behavior since SQLite ≥ 3.26.0, which introduced automatic view/trigger rewriting on `RENAME`. Prior versions did not update view references at all; post-3.26.0, the recompilation check is an unavoidable side-effect.

**The specific failure chain in migration 062:**
1. `DROP TABLE hook_executions` — succeeds (in implicit DML transaction; see §3b)
2. `ALTER TABLE hook_executions_new RENAME TO hook_executions` — SQLite recompiles all views; finds broken views (`vw_graph_edges` missing `reg_sessions`, `vw_component_stats` wrong columns, `vw_guardrail_decisions` wrong columns, `vw_hook_performance` references `hook_executions` which is now absent mid-rename) → **FAILS**

### 3b. Python 3.12 sqlite3 transaction behavior (confirmed by simulation)

Python 3.12 sqlite3 with `isolation_level=""` (the default):

| Statement type | Transaction behavior |
|---|---|
| First DDL before any DML | **Auto-commits** (runs in autocommit mode, immediately durable) |
| DML | Opens `BEGIN DEFERRED` implicit transaction |
| Subsequent DDL while implicit transaction is open | **Does NOT force commit** — runs inside the same implicit transaction |
| Connection close without explicit `COMMIT` | **Rolls back** the implicit transaction |

**Consequence observed:** `CREATE TABLE hook_executions_new` (first DDL in the migration) auto-committed — that's why the empty table persists across failed runs. All subsequent statements (`INSERT`, `DROP TABLE`, `ALTER TABLE RENAME`) are in one implicit transaction that rolls back when `RENAME` fails. This is the source of the dirty DB state.

**Evidence:** Simulation script (`tmp_debug_migrate.py`, `tmp_run_migrations.py`) confirmed: after RENAME failure, `hook_executions` is intact (DROP TABLE rolled back), `hook_executions_new` exists but is empty (CREATE TABLE committed, INSERT rolled back).

### 3c. Options for handling broken views during a SQLite table recreation

| Option | Description | Risk |
|---|---|---|
| **Drop all views upfront** | `DROP VIEW IF EXISTS` every view before the first `CREATE TABLE _new`. Recreate all after the last `RENAME`. | None; this is the SQLite-blessed pattern for bulk schema changes. |
| Drop only broken views | Drop the three broken views; leave working views. | Fails if a working view references a table being dropped+renamed (e.g., `vw_hook_performance` → `hook_executions`). **This is what migration 062 currently attempts — and why it still fails.** |
| `PRAGMA legacy_alter_table = ON` | Disables the post-SQLite-3.26.0 automatic view rewriting. RENAME no longer triggers view recompilation. | The view DDL retains the old table name — views that referenced the old name still reference it after rename. Effectively breaks all dependent views. Not suitable here. |
| Wrap in `BEGIN`/`COMMIT` | No effect on view recompilation; SQLite validates views during RENAME regardless of transaction state. | Not useful. |

**Conclusion:** The only correct approach is Option 1 — drop ALL views before the first table recreation, then recreate all of them after the last rename.

---

## 4. Migration 062 Current State — Logical Issues

File: `core/event_store/migrations/062_nullify_activity_id_backfill_and_replace_views.sql`

### 4a. Idempotency block (lines 28–40)
```sql
DROP TABLE IF EXISTS hook_executions_new;
DROP TABLE IF EXISTS hook_findings_new;
... (7 tables)
```
**Correct.** Handles leftover `_new` tables from prior partial runs.

### 4b. View-handling block — Part 0 (lines 21–25)
```sql
DROP VIEW IF EXISTS vw_graph_edges;
DROP VIEW IF EXISTS vw_component_stats;
DROP VIEW IF EXISTS vw_guardrail_decisions;
```
**INCOMPLETE AND INCORRECT.** Only drops the three already-absent broken views. Does **not** drop the 9 currently-present views. The first `ALTER TABLE hook_executions_new RENAME TO hook_executions` (line 64) will fail because `vw_hook_performance` references `hook_executions` (which has just been dropped on line 62 and doesn't yet exist at rename time).

Similarly, `vw_risk_hotspots` and `vw_security_summary` reference `sec_sarif_findings`, which will cause identical failures at the `sec_sarif_findings` rename.

### 4c. View recreation block — lines 243–270
```sql
CREATE VIEW IF NOT EXISTS vw_graph_edges AS ...;   -- recreates broken view
CREATE VIEW IF NOT EXISTS vw_component_stats AS ...; -- recreates broken view
```
**PROBLEMATIC** (though benign since these are now absent). These views are broken by design — both reference wrong column names and missing tables. Recreation preserves a broken state. Since both are ORPHANED (§2a, §2b), they should not be recreated at all.

### 4d. Part 2 view replacements (lines 272–299)
```sql
DROP VIEW IF EXISTS vw_activity_timeline;
CREATE VIEW vw_activity_timeline AS SELECT ... FROM canonical_events ...;
DROP VIEW IF EXISTS vw_guardrail_decisions;
CREATE VIEW vw_guardrail_decisions AS SELECT ... FROM guardrail_decisions ...;
```
**CORRECT** logic. The corrected DDL for both views is accurate. However, since `vw_guardrail_decisions` is already absent from the DB (dropped by a prior run), the `DROP VIEW IF EXISTS` is a safe no-op.

### 4e. Part 3 backfill (lines 301–417)
```sql
INSERT OR IGNORE INTO canonical_events ... SELECT ... FROM activity_log WHERE activity_type = '...';
```
**CORRECT** logic. Uses deterministic prefix `backfill-activity-log-<activity_id>` for idempotency. Covers all 6 distinct activity_types (159 rows total). Never executed so far.

---

## 5. Root Cause Trace

### Why `reg_sessions` doesn't exist

`reg_sessions` appears only in:
- `core/event_store/migrations/014_graph_views.sql` — the view DDL references it
- `core/event_store/migrations/062_nullify_activity_id_backfill_and_replace_views.sql` — the view recreation block (which should be removed)

**No migration creates a `reg_sessions` table.** No Python file uses it. The table appears in `014_graph_views.sql` as an expected dependency noted in the file header ("Depends on: pi_components, pi_dependencies, reg_sessions tables") but was never built. This was a planning artifact from the initial publication commit `790965e` — a view was written for a table that was supposed to come later but never landed.

### Why `pi_dependencies` has wrong column names in migration 014

Migration 009 (`009_project_intelligence.sql`) created `pi_dependencies` with columns `from_component` and `to_component`. Migration 014 (same commit, `790965e`) wrote views using `source_component_id` and `target_component_id` — a different naming convention that was never aligned with the actual table.

Migration 015 (`015_performance_indexes.sql`) correctly indexes `from_component` and `to_component`, confirming the intended column names were `from_component`/`to_component` from the start. Migration 014 was simply wrong on delivery and was never fixed because SQLite's `CREATE VIEW` silently accepted the bad DDL.

**Both breakages were introduced in the initial publication commit and have been present since day 1 of this repo's public history.** They were dormant because nothing queried these views, and SQLite doesn't validate view DDL at creation time.

### Why `vw_guardrail_decisions` has wrong column names

Migration 029 (`029_analytics_views.sql`) created `vw_guardrail_decisions` referencing `gd.decision` and `gd.reason`. The actual `guardrail_decisions` table has `action` and `message`. This is a naming inconsistency introduced in migration 029 — the view was written for an older or intended schema that used `decision`/`reason`, but the actual table DDL uses `action`/`message`.

---

## 6. Recommended Paths Forward

### Option A: Continue migration 062 — fix the view handling (recommended)

**What changes in migration 062:**
1. Replace the Part 0 view drop block (currently 3 views) with `DROP VIEW IF EXISTS` for **all 12** currently-present views (plus the 3 already-absent ones as IF EXISTS safety).
2. After all 7 table recreations, recreate **only** the 10 valid views (not `vw_graph_edges` and not `vw_component_stats` — both are orphaned and should be permanently retired).
3. Recreate `vw_activity_timeline` and `vw_guardrail_decisions` with corrected DDL (Part 2 logic already correct).
4. Clean up the `CREATE VIEW IF NOT EXISTS vw_graph_edges` and `vw_component_stats` recreation block — remove entirely.

**DB cleanup needed before running:**
- `DROP TABLE IF EXISTS hook_executions_new` (one statement via a standalone cleanup script, NOT a migration).

**Effort:** ~30 minutes to rewrite migration 062. Migration would be a single file with no known remaining blockers.

**Risk:** Low. All table DDLs have been verified against the live schema. The only remaining unknown is whether additional views appear between now and the next run (they won't — the schema is stable).

**Tradeoff:** This approach keeps all work in TA0c as originally scoped. No additional workstream.

---

### Option B: Split — separate view cleanup from activity_id nullification

**Migration 062a:** `DROP VIEW IF EXISTS` all 14 views, then all 7 table recreations, `PRAGMA foreign_keys = ON`, then recreate only the 10 valid views. **No backfill.** Commits cleanly.

**Migration 062b:** INSERT OR IGNORE backfill of 159 rows from `activity_log` into `canonical_events`.

**Migration 063:** `DROP TABLE IF EXISTS activity_log` (unchanged).

**Effort:** ~45 minutes (two migration files instead of one). Adds one more migration number to the sequence.

**Risk:** Slightly higher — two migration files means two chances for a partial run. But the split makes each migration simpler and more auditable.

**Tradeoff:** Better separation of concerns. The view cleanup (which touches nothing TA0c owns) is isolated from the business logic (backfill).

---

### Option C: Add `PRAGMA legacy_alter_table = ON` to silence view validation during renames

**What it does:** Sets `PRAGMA legacy_alter_table = ON` before the table recreations. In legacy mode, `ALTER TABLE RENAME` does NOT recompile views — it leaves view DDL referencing the old name unchanged. After renames, set `PRAGMA legacy_alter_table = OFF`.

**Why this is wrong for this case:** Legacy mode means the view DDL is NOT updated to reference the new table name. After renaming `hook_executions_new` → `hook_executions`, `vw_hook_performance`'s compiled bytecode still references `hook_executions` — which now works because the table came back. But views that were pointing to tables we just RENAMED might break in non-obvious ways.

More critically: legacy_alter_table was added in SQLite 3.26.0 specifically as a backwards-compatibility escape hatch for applications that relied on broken ALTER TABLE behavior. It is not intended as a migration pattern.

**Verdict: Do not use.** Option A is cleaner, correct, and requires the same effort.

---

## Summary Table

| | Option A (fix 062) | Option B (split) | Option C (pragma) |
|---|---|---|---|
| Migration files changed | 1 | 2 | 1 |
| Risk | Low | Low | Medium |
| Effort | ~30 min | ~45 min | ~20 min |
| Correctness | ✓ | ✓ | ✗ |
| Recommended | **YES** | Acceptable | NO |

---

## Appendix: Evidence File Locations

| Evidence | Path | Key lines |
|---|---|---|
| `pi_dependencies` DDL | `core/event_store/migrations/009_project_intelligence.sql` | `from_component`, `to_component` |
| Broken views DDL | `core/event_store/migrations/014_graph_views.sql` | `source_component_id`, `reg_sessions` |
| `pi_dependencies` indexes | `core/event_store/migrations/015_performance_indexes.sql` | `from_component`, `to_component` |
| `vw_guardrail_decisions` DDL | `core/event_store/migrations/029_analytics_views.sql` | `gd.decision`, `gd.reason` |
| vw_graph_edges optional check | `interfaces/cli/verify_migrations.py:44` | `optional_views = {"vw_graph_edges"}` |
| test expects it absent | `tests/unit/test_native_readiness_gates.py:192` | "Optional legacy views missing" |
| graph.py uses correct columns | `core/graph/query.py:203-211` | `from_component`, `to_component` |
| Current migration 062 | `core/event_store/migrations/062_nullify_activity_id_backfill_and_replace_views.sql` | see §4 |
