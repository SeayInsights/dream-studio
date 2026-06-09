# Token Attribution Coverage

## What It Measures

Attribution coverage is the percentage of AI spend (`token.consumed` events) that can
be traced to a specific unit of work (task, work order, project). It is Dream Studio's
primary moat metric: no peer system captures it at this granularity.

Three buckets:

| Status | Meaning |
|---|---|
| **fully_attributed** | Traced to task + work order + project |
| **partial** | Traced to project only (task/WO missing) |
| **orphan** | No attribution context captured |

## Reading the Dashboard Panel

The panel lives under **Intelligence → Token Attribution** in the dashboard sidebar.

- **Primary metric** (`NN.N% Fully Attributed`): green ≥ 90%, yellow ≥ 70%, red < 70%.
- **Three-segment bar**: visual proportion of fully / partial / orphan.
- **Orphan drill-down** (`View recent orphans`): expands a table of the 50 most recent
  orphan events with `probable_cause` hints. No raw prompts or PII are shown.

## Coverage Threshold

`ATTRIBUTION_COVERAGE_MIN = 0.90` in `core/telemetry/attribution_config.py`.

When fully_attributed coverage drops below this threshold, the route logs a warning:

```
attribution_coverage below threshold: NN.N% < 90% (project_id=... total_events=N)
```

No alert infrastructure is triggered in Phase 18.4. Automated alerting is Phase 19.

## What Orphan Events Are

An event becomes an orphan when it is emitted outside the context of an active
Dream Studio work order. Common causes:

1. **Session only** — event emitted in a free-form session with no active task.
2. **Project captured, no task** — `project_id` in trace but no `task_id` or
   `work_order_id` (partial, not orphan, unless project_id is also missing).
3. **Emitter misconfiguration** — hook running without the Dream Studio spool configured.

## How to Investigate Coverage Drops

1. Open the Attribution Coverage panel. Note the orphan count and trend.
2. Click "View recent orphans" and read the `probable_cause` column.
3. If most orphans say "session only": remind operators to start a WO before working.
4. If most orphans say "no attribution context captured": check the emitter hook
   installation (`ds doctor`).
5. Backfill of historical orphans is Phase 19 data hygiene work.

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/v1/insights/attribution-coverage` | Coverage breakdown (global or per-project) |
| `GET /api/v1/insights/attribution-coverage/orphans` | Recent orphan events (no PII) |

### Query parameters

- `project_id` (optional) — scope to a specific project UUID
- `limit` (orphans only, default 50, max 200) — number of orphan events to return

## Baseline (18.4.2a — 2026-05-28)

See `.planning/workstreams/18-4-2a/baseline-measurement.md` for the formal baseline
captured before the database skill (18.4.2) ships. Post-18.4.2 measurements will
determine whether the new skill's events land correctly in the attribution chain.
