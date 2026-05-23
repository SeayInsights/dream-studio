# Projection Framework

**Status:** Implemented (Phase 18.1.5)
**Date:** 2026-05-23
**Implementation:** `core/projections/framework.py`

---

## Overview

Projections are the L3 population mechanism. They consume canonical events from the dual canonical tables (`business_canonical_events`, `ai_canonical_events`) and write structured rows into hub-and-spoke L3 tables (`business_*`, `ai_*`, `bridge_*`).

Key properties:

- **Code-first:** Projections are Python classes, not SQL triggers or scheduled jobs. Logic lives in code, versioned alongside the tables it populates.
- **Trigger-based scheduling:** The runner polls for new canonical events every 5 seconds or after every 100 events. There is no manual scheduling; new events trigger projection runs automatically.
- **Dual canonical source:** Projections read from `business_canonical_events` or `ai_canonical_events` (or both). They declare which event types they consume; the engine routes accordingly.
- **Derivable:** Every L3 row is derivable from canonical. A full rebuild from canonical must produce the same result as incremental processing. This is testable and enforced.

Projections do NOT write to canonical. They do NOT have side effects beyond their declared `target_tables`. They are pure: canonical events in, structured rows out.

---

## Architecture

Three components make up the framework (`core/projections/framework.py`):

### Projection ABC

The base class every projection inherits from. Defines the contract:

```python
class Projection(ABC):
    name: str                        # Unique identifier, matches CLI references
    consumed_event_types: list[str]  # Event types this projection handles
    source_canonical: str            # "business", "ai", or "both"
    target_tables: list[str]         # Tables this projection writes to
    retry_policy: RetryPolicy        # max_retries, backoff_seconds

    def setup_tables(self, db_path: str) -> None: ...     # DDL guard (no-op after migration)
    def handle(self, event: dict, db_path: str) -> None:  # Incremental event handler
    def rebuild_from_canonical(self, db_path: str) -> int: ...  # Full replay
```

### ProjectionRegistry

Maps event types to projection instances. When the engine receives a canonical event, it asks the registry which projections consume that event type and dispatches accordingly.

```python
registry = ProjectionRegistry()
registry.register(WorkOrderProjection())
# Later:
projections = registry.get_for_event_type("work_order.created")
```

### ProjectionEngine

Coordinates the run cycle. On each tick:

1. Reads unprocessed canonical events from the appropriate source table(s) since the last watermark
2. For each event, looks up consuming projections in the registry
3. Calls `projection.handle(event, db_path)`
4. On success: advances the watermark in `projection_state`
5. On failure: increments retry count; after `max_retries`, moves event to `projection_dead_letter`

Watermarks are per-projection, not global. Each projection tracks its own position independently so a slow or failing projection doesn't block others.

---

## Writing a New Projection

### Class declaration

```python
from core.projections.framework import Projection, RetryPolicy

class MyProjection(Projection):
    name = "my_projection"
    consumed_event_types = ["entity.created", "entity.updated", "entity.deleted"]
    source_canonical = "business"          # or "ai" or "both"
    target_tables = ["business_entities"]
    retry_policy = RetryPolicy(max_retries=3, backoff_seconds=5)
```

### setup_tables()

DDL should live in a numbered migration (see Migrations below). The `setup_tables()` method is a no-op guard — it verifies the table exists but does not run DDL itself. This keeps table creation deterministic and version-controlled.

```python
def setup_tables(self, db_path: str) -> None:
    # No-op: migration NNN creates business_entities.
    # This method exists to satisfy the ABC contract.
    pass
```

### handle()

The incremental event handler. Called once per canonical event. Must be:

- **Idempotent:** Calling `handle()` twice with the same `event_id` must produce the same final state. Use `INSERT OR REPLACE` or upsert patterns, never bare `INSERT`.
- **Out-of-order tolerant:** Events can arrive late due to replay or reprocessing. Use the skeleton row pattern: if a later event (e.g. `entity.updated`) arrives before the creation event, insert a skeleton row so the update has somewhere to land. The creation event fills in the full row when it arrives.

```python
def handle(self, event: dict, db_path: str) -> None:
    payload = event.get("payload", {})
    event_type = event["event_type"]

    with sqlite3.connect(db_path) as conn:
        if event_type == "entity.created":
            conn.execute("""
                INSERT OR REPLACE INTO business_entities
                    (entity_id, name, status, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (
                payload["entity_id"],
                payload["name"],
                payload.get("status", "active"),
                event["event_timestamp"],
                event["event_timestamp"],
            ))
        elif event_type == "entity.updated":
            # Skeleton row pattern: ensure row exists before updating
            conn.execute("""
                INSERT OR IGNORE INTO business_entities (entity_id) VALUES (?)
            """, (payload["entity_id"],))
            conn.execute("""
                UPDATE business_entities
                SET status = ?, updated_at = ?
                WHERE entity_id = ?
            """, (payload["status"], event["event_timestamp"], payload["entity_id"]))
        elif event_type == "entity.deleted":
            conn.execute("""
                UPDATE business_entities SET deleted_at = ? WHERE entity_id = ?
            """, (event["event_timestamp"], payload["entity_id"]))
```

### rebuild_from_canonical()

The default implementation replays all matching events from the source canonical table in timestamp order, calling `handle()` for each. Override only if a full replay requires special pre/post logic (e.g. truncating the target table first for a clean rebuild).

```python
# Default — inherited, no override needed in most cases:
# def rebuild_from_canonical(self, db_path: str) -> int:
#     Clears target tables, replays all events in order, returns event count.

# Override example (if you need to truncate first):
def rebuild_from_canonical(self, db_path: str) -> int:
    with sqlite3.connect(db_path) as conn:
        conn.execute("DELETE FROM business_entities")
    return super().rebuild_from_canonical(db_path)
```

### Full example: WorkOrderProjection (abbreviated)

The first production v2 projection. Derives `business_work_orders` from `work_order.*` business canonical events.

```python
class WorkOrderProjection(Projection):
    name = "work_order_projection"
    consumed_event_types = [
        "work_order.created", "work_order.started", "work_order.closed",
        "work_order.blocked", "work_order.unblocked",
    ]
    source_canonical = "business"
    target_tables = ["business_work_orders"]
    retry_policy = RetryPolicy(max_retries=3, backoff_seconds=5)

    def setup_tables(self, db_path: str) -> None:
        pass  # Migration 069 creates business_work_orders

    def handle(self, event: dict, db_path: str) -> None:
        # See core/projections/work_order_projection.py for full implementation
        ...
```

See `core/projections/work_order_projection.py` for the full implementation.

---

## Contracts

These are non-negotiable. A projection that violates any of these is incorrect.

### Deterministic

Given the same sequence of canonical events, the projection must always produce the same final state. No random values, no wall-clock timestamps, no external reads that could change between runs. Use event timestamps (`event["event_timestamp"]`) not `datetime.now()`.

### Idempotent

Calling `handle()` twice with the same `event_id` must leave the target table in the same state as calling it once. This is enforced by design via upsert patterns. The engine uses the `event_id` to track processed events in `projection_state`, so duplicate calls shouldn't happen in normal operation — but replay and rebuild paths depend on idempotency being correct.

### Out-of-order tolerant

Events can arrive out of order during replay or when the projection is behind. Use the skeleton row pattern: if an update event arrives before the creation event, insert a minimal skeleton row with `INSERT OR IGNORE` so the update has somewhere to land. When the creation event arrives later, `INSERT OR REPLACE` overwrites the skeleton with full data.

---

## Lifecycle

### Registration

Register projections with the engine before starting the runner:

```python
engine = ProjectionEngine(db_path=db_path)
engine.register(WorkOrderProjection())
engine.register(MyProjection())
```

The runner (`core/projections/runner.py`) registers all production projections on startup.

### Incremental processing

The `ProjectionRunner` daemon calls `engine.run_cycle()` on two triggers:

- **Time trigger:** Every 5 seconds (configurable via `PROJECTION_POLL_INTERVAL` env var)
- **Event trigger:** After every 100 new canonical events (configurable via `PROJECTION_EVENT_TRIGGER` env var)

Each cycle reads unprocessed events from the canonical table(s) since each projection's last watermark, dispatches to the appropriate projection's `handle()`, and advances the watermark on success.

### Rebuild

A full rebuild replays all matching canonical events from the beginning:

```
# CLI rebuild
py -m interfaces.cli.ds projection rebuild work_order_projection

# Programmatic
projection = WorkOrderProjection()
count = projection.rebuild_from_canonical(db_path)
```

Rebuild is safe to run at any time. It clears and repopulates the target table(s). Running a rebuild while the daemon is active will cause temporary inconsistency; prefer stopping the daemon first for production rebuilds.

### Dead-letter

If `handle()` raises an exception, the engine increments the retry counter in `projection_retry_queue`. After `max_retries` (default: 3) failures, the event is moved to `projection_dead_letter` and processing continues with the next event. The daemon never stalls permanently due to a single bad event.

Dead-letter events require operator review. Use `ds projection dead-letter` to inspect them.

---

## Running the Daemon

```bash
py -m core.projections.runner
```

The runner:
- Registers all production projections
- Creates a PID file at `~/.dream-studio/projection-runner.pid`
- Runs `engine.run_cycle()` on the time + event triggers
- Handles SIGTERM gracefully (completes the current cycle, then exits)
- Removes the PID file on shutdown

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `PROJECTION_POLL_INTERVAL` | `5` | Seconds between cycles |
| `PROJECTION_EVENT_TRIGGER` | `100` | New events per cycle that trigger an early run |

---

## CLI Reference

| Command | Description |
|---------|-------------|
| `ds projection list` | List all registered projections with their watermarks |
| `ds projection status <name>` | Detailed status for one projection (watermark, last event, lag) |
| `ds projection rebuild <name>` | Full rebuild of a projection from canonical |
| `ds projection dead-letter` | Show events in the dead-letter queue |
| `ds projection daemon` | Start the projection runner daemon |

---

## Tables Created by This Framework

Implemented in migrations 068 and 069.

### Migration 068 — Framework infrastructure

| Table | Purpose |
|-------|---------|
| `projection_state` | Watermarks and run metadata per projection |
| `projection_dead_letter` | Events that failed all retries, awaiting operator review |
| `projection_retry_queue` | Transient retry tracking for in-progress failures |

### Migration 069 — First L3 business table

| Table | Purpose |
|-------|---------|
| `business_work_orders` | Structured work order state, populated by `WorkOrderProjection` |

`business_work_orders` is the first v2 L3 business entity table. It is populated exclusively by `WorkOrderProjection` consuming `work_order.*` events from `business_canonical_events`. Direct writes to this table from CLI or hook code are prohibited.
