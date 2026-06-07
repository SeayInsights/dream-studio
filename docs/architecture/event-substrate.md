# Event Substrate — Authoritative Reference

**Status:** CURRENT  
**Last reviewed:** 2026-06-07 (WO-P, WO-M)

This document is the single authoritative reference for Dream Studio's dual-canonical event store and compatibility view.

---

## Four-Table Model (post WO-M / Migration 102)

| Table | Type | Role | Written by | Status |
|-------|------|------|------------|--------|
| `business_canonical_events` | Physical table | Business-domain events (skill invocations, work order state, project events) | Ingestor (dual-canonical write path) | **AUTHORITY** |
| `ai_canonical_events` | Physical table | AI-domain events (token.consumed, tool calls, session events) | Ingestor (dual-canonical write path) | **AUTHORITY** |
| `canonical_events` | Compatibility VIEW | UNION of both authority tables; preserves existing reader queries | View definition in migration 102 | **COMPAT VIEW** |
| `canonical_events_legacy_backup` | Physical table | Pre-WO-M rows preserved; retired, never written to | Migration 102 rename | **RETIRED** |

### Authority Separation Rule (AD-1)

Events are routed to one of the two authority tables based on their `domain` field in the trace:
- `domain: "sdlc"` or `domain: "system"` → `business_canonical_events`
- `domain: "telemetry"` or AI-origin events → `ai_canonical_events`

Paired events (events that appear in both domains) are written once to each table. The UNION view deduplicates by identical column values.

---

## Table Schema

Both authority tables share this schema:

```sql
CREATE TABLE business_canonical_events (  -- same shape for ai_canonical_events
    event_id        TEXT PRIMARY KEY,
    event_type      TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,   -- ISO 8601 UTC
    trace           JSON,            -- attribution context
    severity        TEXT,
    payload         JSON,
    schema_version  INTEGER NOT NULL DEFAULT 1,
    received_at     TEXT NOT NULL DEFAULT (datetime('now'))
);
```

Key distinction from legacy `canonical_events`: the timestamp column is named `event_timestamp`, not `timestamp`. The compat view remaps this to `timestamp` for backward compatibility.

---

## Compat View Usage

The `canonical_events` view works for **reads**. Do NOT attempt to INSERT/UPDATE/DELETE via the view — it is read-only. Writes go to the authority tables via the ingestor.

```python
# Correct: read from compat view (existing code works unchanged)
conn.execute("SELECT * FROM canonical_events WHERE event_type = 'token.consumed'")

# Correct: write via ingestor (CanonicalEventEnvelope → spool → ingestor → authority table)
write_envelopes([envelope])

# Wrong: direct INSERT to canonical_events (view, not writable)
# Wrong: direct INSERT to canonical_events_legacy_backup (retired table)
```

---

## Write Path (Spool → Authority)

1. Emitter creates a `CanonicalEventEnvelope` and calls `write_envelopes()`
2. `write_envelopes()` serializes to a JSON spool file in `~/.dream-studio/spool/`
3. Ingestor picks up the spool file and writes to the appropriate authority table
4. The compat view `canonical_events` immediately reflects the new row

See [three-store-model.md](three-store-model.md) for the full write-path architecture.

---

## Correlation

Business and AI events are correlated via `correlation_id` in the trace JSON:
```json
{
  "trace": {
    "correlation_id": "<shared-uuid>",
    "project_id": "<optional>",
    "work_order_id": "<optional>",
    "task_id": "<optional>"
  }
}
```

A skill invocation emits a `skill.invoked` event to `business_canonical_events` and the resulting token usage emits `token.consumed` to `ai_canonical_events`, linked by the same `correlation_id`.

---

## Query Patterns

```sql
-- All token events (via compat view)
SELECT payload FROM canonical_events WHERE event_type = 'token.consumed';

-- Business events only (authority table, faster for business queries)
SELECT * FROM business_canonical_events WHERE event_type = 'skill.invoked';

-- AI events only (authority table, faster for token queries)
SELECT * FROM ai_canonical_events WHERE event_type = 'token.consumed';

-- Historical pre-WO-M events
SELECT * FROM canonical_events_legacy_backup WHERE event_type = ?;
```

---

## Migration History

| Migration | Change |
|-----------|--------|
| 037 | Created original `canonical_events` physical table |
| 092 | Added `ds_eval_baselines` (eval scoring) |
| 100 | Dual-canonical write path made primary (WO-M pre-work) |
| 102 | WO-M: Renamed `canonical_events` → `canonical_events_legacy_backup`; created compat VIEW |
| 104 | Added `ds_eval_runs` (per-run eval evidence) |
| 105 | Added `cache_read_tokens` to `token_usage_records` |
