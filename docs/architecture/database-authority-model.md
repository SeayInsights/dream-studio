# Dream Studio Database Authority Model

This document defines the **authority model** for Dream Studio's three-store database
architecture: what each store owns, what it consumes, and what it must never do.

For the **pipeline** (event flow through spool → canonical → business entities), see
[three-store-model.md](three-store-model.md). That document covers the data flow.
This document covers the authority contract.

---

## Three-Store Authority Matrix

| Store | File | Authority | Consumes | Outputs | Never |
|---|---|---|---|---|---|
| **SQLite authority** | `~/.dream-studio/state/studio.db` | Execution + operational state: canonical events, all `business_*` entities, execution events, token records, hook/skill/validation/security telemetry, gate decisions, shared intelligence | Spool events (via ingestor), CLI mutations | Dashboard reads, source rows to DuckDB projections, gate verdicts | Write to DuckDB or files.db; emit canonical events from a read |
| **DuckDB analytics** | `~/.dream-studio/state/aggregate_metrics.db` | **NEVER-AUTHORITY** — analytical rollups only | studio.db (read-only, via `core/analytics/aggregate_metrics.py`) | Rollup tables: `finding_rollups`, `rule_fire_rates`, `baseline_trends`; analytics API reads | Emit canonical events; make gate decisions; own business entity state; be opened with `sqlite3.connect()` |
| **Files store** | `~/.dream-studio/state/files.db` | Artifact content: handoff docs, evidence bundles, release notes, rollback state, exports — versioned by `(project_id, name)` | Producer writes (CLI, skills, release commands) | Content blobs, version history | Emit canonical events; own business entity state; be the authority for any gate decision |

---

## Per-Store Authority Detail

### SQLite authority — `studio.db`

**What it owns:**
- All `business_*` tables (projects, milestones, work orders, tasks)
- All canonical events (`canonical_events`, `ai_canonical_events`, `execution_events`)
- Telemetry facts: token usage, hook executions, skill invocations, validation results, security findings
- Gate decisions: `guardrail_decisions`, `policy_decision_records`
- Shared intelligence: adapter profiles, context packets, evaluation records, learning events
- The schema itself: migrations apply to studio.db only

**What it consumes:**
- Spool events written by emitters (PostToolUse, Stop, pre-push hook, skill invocations)
- CLI mutations (`ds work-order`, `ds project`, `ds task` commands)

**What it outputs:**
- Read-model rows for dashboard API routes (`/api/v1/`, `/api/v2/`, `/api/telemetry/`)
- Source rows projected to DuckDB analytics store
- Gate verdicts consumed by CI/pre-push gate checks

**Invariants:**
- Only `spool/ingestor.py` writes canonical events (rule 4)
- DuckDB reads never trigger canonical event emission
- Dashboard/API routes never bootstrap, migrate, or mutate studio.db
- Schema changes require numbered migration files under `core/event_store/migrations/`

---

### DuckDB analytics — `aggregate_metrics.db`

**What it owns:**
- Analytics rollup tables: `finding_rollups`, `rule_fire_rates`, `baseline_trends`
- DuckDB-side projection tables derived from studio.db business_* entities

**What it consumes:**
- Read-only reads from studio.db via `core/analytics/aggregate_metrics.py`

**What it outputs:**
- Aggregated analytics reads for `/api/v1/analytics/aggregate` and similar endpoints
- Cross-skill findings summaries

**Invariants:**
- NEVER-AUTHORITY: no gate decision or canonical event uses DuckDB as its source
- Must be a DuckDB file, not SQLite — `sqlite3.connect()` must never target this file
- Write access restricted to `core/projections/runner.py` only (enforced by `authority-boundary` pre-push gate)
- API routes open read-only connections only (`read_only=True`)
- `framework.py._analytics_conn` is the wiring point; currently `None` — DuckDB projection
  dispatch is a future milestone (WO-TS3)

---

### Files store — `files.db`

**What it owns:**
- Versioned artifact blobs: handoff documents, evidence bundles, release packages,
  rollback state, exports
- Version history per `(project_id, name)` key via auto-incrementing version column

**What it consumes:**
- Producer writes from CLI commands (`ds files`), release skills, handoff skills

**What it outputs:**
- Content blobs and version history for retrieval: `ds files list [--project-id] [--category]`

**Valid `ds_files.category` values:** `handoff`, `evidence`, `release`, `rollback`, `export`

**Invariants:**
- NEVER-AUTHORITY for events or gate decisions
- No canonical event is emitted based on files.db reads
- No gate verdict is derived from files.db content
- Schema: single `ds_files` table, forward-only writes (append/version)

---

## Separation Boundaries

These boundaries are enforced by the `authority-boundary` pre-push gate:

| Boundary | Rule |
|---|---|
| Adapter projections | Must not write to authority tables (`business_*`, `execution_events`) |
| Projections layer | Read-only from authority; write only to derived-view tables |
| CLI / business state | Only permitted writer of `business_*` mutations |
| Ingestor | Sole writer of canonical events |
| DuckDB | Write access to `aggregate_metrics.db` restricted to `core/projections/runner.py` |

---

## Cross-Reference

| Topic | Document |
|---|---|
| Event pipeline (spool → canonical → business) | [three-store-model.md](three-store-model.md) |
| Schema DDL and migration history | `core/event_store/migrations/` |
| Live schema verification | `py -m interfaces.cli.ds doctor schema_coherence` |
| Schema debt history | [aspirational-schema-debt.md](aspirational-schema-debt.md) |
| Database paths and authority rules | [../DATABASE.md](../DATABASE.md) |
