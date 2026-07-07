# Three-Store Data Architecture

**Status:** canonical · **Baseline:** migration `142_lean_baseline` (forward migrations 143+)

Dream Studio persists operator-local state in **three physically separate stores**,
each with a single, non-overlapping responsibility. The split exists so that the
*authority* (what is true) is never conflated with *derived analytics* (what is
computed) or *documentation artifacts* (what is written). Dashboards and reports are
projections of the authority; they are never the source of truth.

```
 spool (events dir)                 SQLite authority            DuckDB analytics        docstore
 ~/.dream-studio/events/     →      studio.db            ⇢      aggregate_metrics.db     files.db
   *.jsonl envelopes              (source of truth)          (derived, rebuildable)   (docs registry)
        │                               │                            │
        │  ingestor (sole writer)       │  projection runner         │  ds files add
        ▼                               ▼                            ▼
   business_canonical_events  ⋈  ai_canonical_events   →   events_fact / metric views
              (join on correlation_id)                     (read-only API/CLI reads)
```

## The three stores

### 1. `studio.db` — SQLite authority (source of truth)

Holds every fact the platform reasons about. Bootstrapped and migrated by
`core/config/sqlite_bootstrap.py`; the DB layer lives behind
`core.event_store.studio_db` (a facade over `connection` / `event_writer` /
`event_reader` / `migration_runner`). Table families:

- **`business_*`** — product entities and the business event log: `business_projects`,
  `business_milestones`, `business_work_orders`, `business_tasks`,
  `business_design_briefs`, `business_work_order_preflights`, `business_work_order_types`,
  and **`business_canonical_events`** (the business half of the canonical event stream).
- **`ai_*`** — AI adapter accounting and the AI event half: **`ai_canonical_events`**,
  `ai_usage_operational_records`, `ai_adapter_accounting_profiles`. Token/cost is
  **derived** from `ai_canonical_events` payloads, never fabricated.
- **`raw_*`** — captured operational substrate: `raw_claude_code_events`, `raw_sessions`,
  `raw_handoffs`, `raw_lessons`, `raw_approaches`, `raw_sentinels`,
  `raw_operational_snapshots`, `raw_skill_telemetry`.
- **`ds_*`** — SDLC operational metadata (not business state): `ds_config`,
  `ds_escalations`, `ds_eval_baselines`, `ds_friction_signals`, `ds_user_extensions`,
  `ds_workflow_pattern_signals`.
- **projection plumbing** — `projection_state`, `projection_retry_queue`,
  `projection_dead_letter`; schema version in `_schema_version`.
- **FTS mirrors** — `memory_fts`, `fts_gotchas` (derived search indexes over authority rows).

### 2. `aggregate_metrics.db` — DuckDB analytics (derived, rebuildable)

A **native DuckDB** file (never SQLite — a wrong-format file is rejected loudly by
`core/analytics/duckdb_store.py`). It holds **only derived aggregates** — `events_fact`,
token-usage/cost views, session metrics — computed by `aggregate_metrics.py` reading
`studio.db`. API routes and the CLI open it **read-only**. It can be deleted and
rebuilt from the authority at any time. **No business entity authority ever lives here.**

### 3. `files.db` — documentation docstore

Registry of persistent documentation artifacts (`ds_documents`, `ds_documents_fts`).
Docs under `docs/**` and `.planning/**` (except `personal/`) are registered via
`ds files add <path> --project-id <id>`; the Stop-hook enforcement blocks a session
that wrote docs without registering them.

## The event spine

1. **Emit** — adapters/hooks write canonical event envelopes as JSONL into the spool
   (`~/.dream-studio/events/`). The spool is append-only capture.
2. **Ingest** — the ingestor is the **sole writer** of `*_canonical_events`; it drains
   the spool into `business_canonical_events` and `ai_canonical_events`, which correlate
   on **`correlation_id`** (the business action ⋈ its AI usage).
3. **Project** — the projection runner (`core/projections/runner.py`) consumes canonical
   events and updates the read models: the `business_*` entity tables (via `sync_tick()`)
   and, separately, the DuckDB derived views. `projection_state` tracks progress;
   failures land in `projection_retry_queue` / `projection_dead_letter`.
4. **Read** — dashboards, the CLI, and reports read projections. They are **derived
   surfaces**, never authority.

## Store-placement (table-vetting) rubric

When adding a table, decide its store by these questions, in order:

1. **Is it the source of truth for a business entity or event?** → `studio.db`
   (`business_*` / `ai_*`). Business authority is *never* placed in DuckDB.
2. **Is it captured operational substrate or SDLC metadata?** → `studio.db`
   (`raw_*` / `ds_*`).
3. **Is it a pure aggregate/rollup derivable from authority rows?** → `aggregate_metrics.db`
   (DuckDB). If it can be dropped and rebuilt from `studio.db`, it belongs here.
4. **Is it a documentation artifact?** → `files.db` via the docstore.
5. **Is it a search index over authority rows?** → an FTS mirror in `studio.db`
   (kept in sync from its base table; not independent authority).

A table that is *migration-recreated dead weight* (no reader, or a duplicate of an
existing family) belongs in **none** of them — it is dropped and tombstoned
(`tests/unit/schema_tombstones_data.py`) so it cannot be resurrected.

## Invariants

- The ingestor is the only writer of canonical events.
- `business_*` authority never lives in DuckDB; DuckDB is derived and rebuildable.
- Read models and dashboards are projections; correcting data means correcting the
  authority + re-projecting, never editing a read model in place.
- Token cost is derived from `ai_canonical_events` payloads, not stored as ground truth.
