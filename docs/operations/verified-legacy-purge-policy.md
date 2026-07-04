# Verified Legacy Purge Policy

Dream Studio may remove duplicate legacy rows only after migration proof,
reference checks, backup verification, and dashboard/API validation.

## Classifications

- `current_authority_keep`: keep as canonical current state.
- `migrated_then_purge_source`: purge only after the migrated target is proven.
- `obsolete_purge`: purge after proof that no active source reads it.
- `not_migrated_manual_review`: keep out of normal views and review manually.
- `sensitive_manual_review`: do not inspect values; classify by path/category.
- `rollback_backup_keep_until_final_cleanup_approval`: keep until separate
  final cleanup approval.

## Required Proof

Before purging rows:

1. create and verify a fresh backup;
2. prove the target current-authority table contains the migrated data;
3. prove active dashboard/API/read models read the current table;
4. run reference checks for the old table/path;
5. validate summaries and detail rows after purge;
6. record exact criteria and row counts.

Dropping tables is not part of ordinary purge. Deleting unknown useful data,
secret-bearing config, rollback backups, current evidence, current telemetry,
or repo source is forbidden without a new approval boundary.

## Current Legacy Guidance

`raw_sessions` remains current session-continuity authority until a future
session authority migration supersedes it. `raw_skill_telemetry` still has
correction lineage attached and requires manual review before row purge.

<!-- 2026-07-03: `raw_token_usage` dropped in migration 138 (WO 468ce225) —
this closes the condition above. `token_usage_records` (the table the old
guidance pointed to) was itself dropped in migration 137; dashboard/API token
reads now go through the DuckDB aggregate_metrics.db token_usage_records VIEW,
which is strictly more informative than either dropped SQLite table.
Reference-evidence proof: no FK, no view, and (post-migration) no production
writer/reader references raw_token_usage; the 3 stale rows carried no
accounting fields the canonical token.consumed event stream doesn't already
carry. Dropping the table (not just purging rows) was in scope here because
every writer was already vestigial (one-time migration/backfill tooling only)
— see migration 138's header comment for the full writer/reader inventory. -->

