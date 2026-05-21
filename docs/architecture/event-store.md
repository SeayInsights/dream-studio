# Event Store Architecture

## Overview

Dream Studio uses a two-layer event storage model:

1. **`canonical_events`** — the single source of truth for all events
2. **`execution_events`** — a projection table, rebuilt from canonical events

## canonical_events (Authoritative)

All events flow through the spool pipeline:
1. Emitter writes `CanonicalEventEnvelope` to spool (a JSON file in `.dream-studio/spool/`)
2. Ingestor picks up the file and writes to `canonical_events` table
3. Projections and read models are built from `canonical_events`

### Event Schema

```json
{
  "event_id": "<uuid>",
  "event_type": "<domain>.<noun>.<verb>",
  "timestamp": "<iso8601>",
  "schema_version": 1,
  "trace": {
    "domain": "sdlc | telemetry | system",
    "project_id": "<optional>",
    "milestone_id": "<optional>",
    "task_id": "<optional>",
    "process_run_id": "<optional>"
  },
  "payload": { ... }
}
```

### Domain Field

Every canonical event trace must include a `domain` field:

| Domain | Description | Example event types |
|--------|-------------|---------------------|
| `sdlc` | Work orders, tasks, milestones, projects, skills | `work_order.started`, `task.completed`, `skill.invoked` |
| `telemetry` | Token usage, tool execution, session lifecycle, execution runs | `token.consumption.recorded`, `tool.execution.completed` |
| `system` | Infrastructure, internal Dream Studio events | (reserved) |

Events emitted without a domain field trigger a `[ds-ingestor] WARNING` to stderr.

## execution_events (Projection)

`execution_events` is rebuilt by the ingestor from `canonical_events`. It is NOT a primary
write target. Historical rows direct-written before TA0b have `_built_from_event_id = NULL`.
Projected rows carry the source canonical event's `event_id` in `_built_from_event_id`.

### Projection Trigger

When the ingestor writes an execution-domain event to `canonical_events`, it immediately
calls `projections.core.execution_events_projection.apply()` to write the corresponding
row to `execution_events`. The projection is idempotent — replaying the same event is safe.

### Projected Event Types

- `execution.started`
- `execution.completed`
- `execution.failed`

## Dashboard Status (TA0b)

The dashboard's telemetry endpoints may return reduced data during the TA-series.
This is expected and accepted. Full dashboard restoration is TA5.

## Migration History

| Migration | Description |
|-----------|-------------|
| 037 | Initial execution_events table |
| 058 | Domain field validation requirement documented |
| 059 | `_built_from_event_id` column added to execution_events |
| 060 | Backfill: domain added to existing events; execution_events populated from canonical |
