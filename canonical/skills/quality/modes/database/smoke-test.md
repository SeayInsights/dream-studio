# Database Skill — Smoke Test

Quick validation procedure after install or update.

## 1. Skill loads

```
ds skill list | grep database
```
Expected: `quality:database` appears in output.

## 2. Dry-run invocation

```
ds skill invoke ds-quality:database --dry-run
```
Expected: No error. Prints skill summary and mode options.

## 3. Audit mode — single migration file

```
ds skill invoke ds-quality:database:audit core/event_store/migrations/011_memory_entries.sql
```
Expected: Runs without crash. Produces a report (may have 0 findings on a well-formed file).

## 4. Build mode smoke

```
ds skill invoke ds-quality:database:build "CREATE TABLE example (id TEXT);"
```
Expected: Fires db-001 (no primary key) as a high finding. Does not crash.

## 5. --changed scope

```
ds skill invoke ds-quality:database:audit . --changed
```
Expected: Resolves changed files vs main, scopes to .sql and .py files, produces report.

## Pass criteria

- No Python exceptions
- Skill dispatcher reaches the correct submode
- At least one static rule evaluates on a real input
- Token usage logged in report footer

## Known acceptable outcomes on a fresh repo

- db-019 (DB engine version) may show `PASS` if engine version not determinable
- db-016/017/018 (backup rules) will show `WARN: manual verification required` — they are checklist-style, no auto-detection
- db-005 (money as float) will show `PASS` on a financial-data-free repo — that's correct
