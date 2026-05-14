# Work Ledger Contract

Phase: 16A - Work Order MVP Contract Foundation

The Work Ledger is the local file-backed record of Work Order lifecycle artifacts in Phase 16. It is not a database ledger in Phase 16.

## Authority Principles

1. Phase 16 ledger is file-backed only.
2. DB/event integration is deferred to a later explicit compatibility/ledger phase.
3. Lifecycle records may be represented as local files.
4. Future event names may be documented but must not imply real-runtime-DB writes.
5. Ledger files do not override local canonical runtime state.

## File-Backed Ledger Records

Phase 16 may define local files for:

- Work Order definitions;
- validation records;
- execution packets;
- approval records;
- Work Results;
- eval artifacts;
- reports.

Recommended storage roots:

- `~/.dream-studio/meta/work-orders/`
- `~/.dream-studio/projects/<project>/work-orders/`

Tests must use fake HOME or temp equivalents.

## Future Event Names

The following names may be used as future-compatible local record names:

- `work_order.created`
- `work_order.validated`
- `work_order.rendered`
- `work_order.result_recorded`
- `work_order.reported`
- `work_order.blocked`
- `work_order.cancelled`
- `work_order.eval_recorded`

In Phase 16, these names are file-backed record names only. They must not write to `canonical_events` or any real runtime DB table by default.

## Deferred DB/Event Integration

DB/event integration requires a later explicit compatibility/ledger phase after:

- native DB schema compatibility is resolved;
- execution graph foreign key health is reconciled;
- table ownership is contracted;
- migration strategy is approved;
- hash-guarded validation proves no unintended native DB mutation.

## Prohibitions

The Work Ledger must not:

- add Work Order DB tables in Phase 16;
- add schema migrations in Phase 16;
- write real-runtime-DB events by default;
- write `canonical_events`, `execution_nodes`, `execution_dependencies`, `execution_outputs`, `decision_log`, `memory_entries`, or other canonical authority tables;
- repair, restore, downgrade, overwrite, or mutate native DB/backups;
- become dashboard, telemetry, adapter, research, enterprise, Docker, cloud, or org/global authority.

## Validation Expectations

Static tests must prove:

- ledger is file-backed only;
- lifecycle records are local files;
- future event names are documented as non-DB records;
- DB/event integration is deferred;
- schema migrations are prohibited in Phase 16.
