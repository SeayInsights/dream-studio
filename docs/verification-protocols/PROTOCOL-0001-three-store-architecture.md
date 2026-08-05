# PROTOCOL-0001: Reconstruct the three-store data architecture from code

- **Status:** Active
- **Date:** 2026-08-03
- **Author:** Dannis Seay
- **Applies to:** any high-risk WO touching the event substrate, the store boundaries, or a
  migration/DDL site (the class that historically caused authority-integrity regressions).

> Worked reference protocol (R7). Verifies that Dream Studio's three-store model is intact
> **by reconstructing it from code alone** — never from the architecture docs, which are a
> projection and can lag. Run: `ds work-order verify --protocol PROTOCOL-0001 <wo>`.

## 1. Scope constraint (hard)

- **Inspect ONLY:**
  - `core/event_store/migrations/` (the SQLite schema of the authority store)
  - `core/config/sqlite_bootstrap.py`, `core/config/paths.py` (bootstrap + store paths)
  - `core/analytics/duckdb_store.py` (the DuckDB analytics store + connection factory)
  - `core/files/store.py` (the files/artifact store)
  - `spool/writer.py` and `core/projections/runner.py` (the event → projection spine)
  - `core/gates/authority_boundary_check.py` (the codified boundary)
- **Never open:** `docs/architecture/*`, `docs/DATABASE.md`, `docs/MIGRATION_AUTHORITY.md`,
  or any `tests/**` — those state the intended answer and would turn the review into
  "read the doc, confirm the doc". Reconstruct the model from the code above instead.

## 2. Shape, not current behavior

State the expected shape **first**, from the sources in scope:

- There are exactly **three stores**, each with a single purpose:
  1. `studio.db` (SQLite) — the **authority**: canonical events + business/authority entities.
  2. `aggregate_metrics.db` (DuckDB) — **derived analytics**, `NEVER-AUTHORITY`.
  3. `files.db` (SQLite) — **artifact/blob store**, `NEVER-AUTHORITY`.
- Events flow **spool → canonical events → projections**; the projection runner is the
  **sole read-write** holder of the DuckDB analytics connection. Every other reader opens
  DuckDB **read-only**.

Only after writing that down, compare the code to it.

## 3. Conflict rule (spec/intent wins)

If code diverges from the three-store spec — e.g. a `connect_analytics(read_only=False)`
outside `core/projections/runner.py`, a canonical write to the DuckDB store, a gate reading
the analytics store as authority, or a migration that puts derived data in `studio.db` — the
**spec wins**: it is a finding against the code, not a redefinition. Do not rationalize a
boundary violation as intended.

## 4. Re-runnable by fresh context

Every input is named above; the review needs no conversation history and reproduces the same
verdict on a re-run. Findings still become work orders (the existing `verify` gap→WO behavior
is unchanged).

## Verdict shape

- **Reconstruction:** the three-store model as reconstructed from the code in scope.
- **Divergences:** each boundary the code crosses (with the offending path:line).
- **Verdict:** PASS if the code matches the reconstructed three-store shape; otherwise
  FINDINGS, one work order per divergence.
