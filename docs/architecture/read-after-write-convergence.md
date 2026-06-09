# Read-After-Write Convergence Policy

Part of the [Substrate Policy](substrate-policy.md).

## The problem

`business_work_orders` is the only 100% projection-backed table.  The
`WorkOrderProjection` runner polls `business_canonical_events` every ~5 s and
materializes results into `business_work_orders`.  Every write to
`business_work_orders` flows through the spool → ingestor → canonical →
projection runner pipeline.

Any CLI command that reads from `business_work_orders` immediately after
emitting an event will read stale state.

## Pattern C — the chosen policy

> Writers emit events and return the expected post-state optimistically.
> Within-function post-mutation reads against projected tables use the named
> exclusion pattern (`AND entity_id != <just-mutated-id>`).  Cross-function
> reads that may see stale projected state use the canonical-events fallback:
> when projected state appears stale, check `business_canonical_events` for a
> recent event for that entity and treat it as authoritative.

### Named exclusion (within-function)

Applied when the same function emits an event AND then queries the same
projected table in the same connection scope.

```python
# close_work_order: exclude the just-closed WO from next-WO and remaining-count queries
conn.execute(
    "SELECT ... FROM business_work_orders"
    " WHERE milestone_id = ? AND work_order_id != ? AND status = 'created'",
    (wo_milestone_id, work_order_id),
)
```

### Canonical-events fallback (cross-function)

Applied when a downstream function reads a projected table and may see an
entity in its pre-mutation state because the event was emitted in a previous
function call.

```python
# close_milestone: check canonical events when projected WOs appear open
if open_wos:
    open_wo_ids = [r[0] for r in open_wos]
    placeholders = ",".join("?" * len(open_wo_ids))
    closed_in_canonical = {
        row[0]
        for row in conn.execute(
            f"SELECT work_order_id FROM business_canonical_events"
            f" WHERE event_type = 'work_order.closed'"
            f" AND work_order_id IN ({placeholders})",
            open_wo_ids,
        ).fetchall()
    }
    open_wos = [r for r in open_wos if r[0] not in closed_in_canonical]
```

`work_order.closed` is a terminal state — there is no `work_order.reopened`
event.  The mere presence of a `work_order.closed` event for a WO ID is
sufficient to treat that WO as closed, regardless of the projected row's
current status.  The `work_order_id` column is denormalized on
`business_canonical_events`, so the fallback query requires no JSON extraction.

### Optimistic return

Writers return the expected post-state based on the emitted event, not a
subsequent projection read.

**What this guarantees:** The writer's emit succeeded and the event is in the
spool.  The event will eventually be reflected in the projected table.

**What this does not guarantee:** The projection has applied the event.
Subsequent reads against the projected table are the authoritative answer;
the optimistic return is a convenience for immediate CLI feedback only.

## Known hazards

| Hazard | Location | Status | Resolution |
|--------|----------|--------|------------|
| H4-1: `close_work_order` post-close queries | `core/work_orders/close.py:412-432` | Fixed | Named exclusion (`AND work_order_id != ?`) |
| H4-2: `close_milestone` open WO check | `core/milestones/close.py:152-168` | Fixed | Canonical-events fallback |
| H4-3: `unblock_work_order` pre-check | `core/work_orders/mutations.py:205-219` | Latent | Accepted — only fails if `block` and `unblock` are called in sub-second succession programmatically |
| H4-4: `create_work_order → start_work_order` chain | `core/work_orders/mutations.py:386-416` | Theoretical | No current call site chains these in the same function or CLI session |

## Policy assumptions

**Pattern C's correctness depends on the writer's emit reliably reaching the
spool.**  Hook fail-open semantics mean a silent emit failure produces no
canonical event and breaks the fallback.  Writers that emit events must use
mechanisms that surface failure.  The spool writer's existing error handling
(`spool.writer.write_event`) is sufficient for SDLC mutation paths; emit-from-
hook code paths that swallow errors are out of scope for this policy.

## Event ordering semantics

`business_canonical_events` has no autoincrement primary key.  The primary
key is `event_id` (UUID).  For ordering, use `received_at` (ingestion
timestamp, TEXT ISO-8601 UTC) or `event_timestamp` (event emission timestamp,
TEXT ISO-8601 UTC).  Both are TEXT timestamps in UTC ISO format; TEXT
comparison is chronologically correct for ISO-8601.

For the canonical-events fallback in `close_milestone`, ordering is
irrelevant: `work_order.closed` is terminal, so the mere presence of a
matching event is sufficient.  Use cases that emit multiple events for the
same entity in sub-millisecond succession and rely on ordering should use
`received_at` as the tiebreaker.

## Enforcement

**Integration test:** `tests/integration/substrate/test_read_after_write_under_projection_lag.py`

The test:
1. Inserts events directly into `business_canonical_events` (does NOT run the projection runner).
2. Sets the projected L3 table to the stale pre-mutation state.
3. Calls each writer→reader function chain and asserts it works correctly.

This test grows as new projections land.  Each projection migration in 18.2.3+
adds its writer→reader chains to this file.

## Future projections (18.2.3+)

When `business_tasks` and `business_milestones` become projection-backed:

| Hazard | Writer→reader chain | Required fix |
|--------|---------------------|--------------|
| `mark_task_done` → remaining count | `mutations.py:63-67` | Named exclusion (`AND task_id != ?`) |
| `close_milestone` → milestone count | Future reader TBD | Named exclusion or canonical fallback |
