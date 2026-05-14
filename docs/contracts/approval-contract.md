# Approval Contract

Phase: 16A - Work Order MVP Contract Foundation

Approvals are human/operator decisions that control whether a Work Order may move through sensitive gates. Approval records are local, file-backed evidence in Phase 16.

## Authority Principles

1. Human approval gates are governance evidence, not autonomous execution authority.
2. Phase 16 approval records are file-backed only.
3. Approval event names are future-compatible local record names, not real-runtime-DB event writes.
4. No mutation is allowed without explicit approval.
5. Approval records do not grant dashboards, telemetry, adapters, research, enterprise analytics, Docker, cloud, or org/global layers canonical authority.

## Approval Modes

| Mode | Meaning |
| --- | --- |
| `observe_only` | Work Order may inspect explicitly selected target context and produce evidence only. No target mutation. |
| `render_only` | Work Order may render execution packets only. No execution. |
| `manual_execute` | Human executes externally and records result evidence. |
| `approval_required` | Work Order is blocked until a human approves the next gate. |
| `blocked` | Work Order must not proceed. |

Phase 16 MVP starts with `observe_only`, `render_only`, and `manual_execute` semantics. Mutation-capable modes are out of scope.

## Approval States

- `not_required`
- `requested`
- `approved`
- `rejected`
- `expired`
- `revoked`
- `blocked`

State changes must be recorded as file-backed local approval records in Phase 16.

## Future/File-Backed Record Names

The following names may be used as local file-backed lifecycle records:

- `work_order.approval.requested`
- `work_order.approval.granted`
- `work_order.approval.rejected`
- `work_order.approval.revoked`
- `work_order.approval.expired`

These names do not imply writes to `canonical_events` or any real runtime DB table in Phase 16.

## Mandatory Approval Actions

Explicit human approval is mandatory before any future mode may:

- mutate a target repo;
- run a command that writes files outside the Work Order store;
- stage, commit, push, delete, move, or format target files;
- run schema migrations;
- write to the native runtime DB;
- execute against DreamySuite;
- export local/private evidence outside local state;
- elevate from observe-only to mutation-capable execution.

## Human Decision Semantics

Human decisions must record:

- decision identifier;
- linked Work Order ID;
- approver;
- decision type;
- approved scope;
- denied scope, if any;
- timestamp;
- evidence reviewed;
- expiration or revocation rule;
- privacy/export classification.

Approvals are scoped. Approval for one Work Order, target path, or command does not transfer to another.

Approved mutation evidence for `approval_required` Work Orders must be file-backed at `approvals/approval.json` and include:

- `approval_status: approved`
- `approved_by`
- `approved_at`
- `approval_mode: approval_required`
- `approved_files`
- `forbidden_files`
- `approval_scope`

Approved mutation compliance may pass only when explicit changed-file evidence stays wholly within `approved_files` and outside `forbidden_files`.

## Non-Delegable Decisions

The following cannot be delegated to an AI tool, dashboard, adapter, telemetry stream, Docker container, enterprise process, or research recommendation:

- approval to mutate a target repository;
- approval to run migrations;
- approval to write the native runtime DB;
- approval to restore or repair local runtime DB/backups;
- approval to execute against DreamySuite;
- approval to export private local evidence.

## Validation Expectations

Static tests must prove:

- approval modes and states are documented;
- future record names are file-backed only;
- mutation requires explicit human approval;
- approvals do not imply real-runtime-DB event writes;
- approvals cannot be delegated to non-authoritative surfaces.
