# Work Order Contract

Phase: 16A - Work Order MVP Contract Foundation

Work Orders are local, file-backed planning and evidence records for bounded AI-assisted work. They describe what may be attempted, which skills/workflows/agents may participate, what is forbidden, what evidence is required, and when a human must approve.

Work Orders do not execute work by themselves. They do not own canonical runtime state.

## Authority Principles

1. Local canonical runtime state remains authoritative.
2. A Work Order is a portable instruction and evidence primitive, not a database owner.
3. Phase 16 Work Orders are `file_backed` only.
4. Work Orders must not add DB tables, run schema migrations, or write events to the real runtime DB by default.
5. Work Orders must not mutate target repositories during `create`, `validate`, `render`, `status`, `record-result`, or `report`.
6. Renderers produce target-specific execution packets. Renderers do not execute packets.
7. Dashboards, telemetry, adapters, research, enterprise analytics, Docker, cloud, and org/global layers do not become Work Order authority.

## Required Fields

Every Work Order definition must include:

| Field | Rule |
| --- | --- |
| `work_order_id` | Stable local identifier, unique within the file-backed Work Order store. |
| `project_name` | Human-readable project or target context name. |
| `target_path` | Explicit operator-selected path. It must not be inferred from the native runtime DB. |
| `objective` | Plain-language goal. |
| `approval_mode` | One of the modes named by the approval contract. |
| `risk_level` | `low`, `medium`, `high`, or `critical`. |
| `scope.include` | Explicit paths, modules, docs, or surfaces in scope. |
| `scope.exclude` | Explicit paths, modules, docs, or actions out of scope. |
| `allowed_skills` | Canonical skill identifiers only, using `ds-<slug>` form. |
| `allowed_agents` | Agent identifiers allowed to support the Work Order. |
| `workflow` | Workflow identifier or inline workflow reference. |
| `forbidden_actions` | Actions that must not be taken. |
| `validation_commands` | Commands that may be rendered as validation expectations. |
| `expected_outputs` | Expected final artifacts or evidence. |
| `stop_conditions` | Conditions requiring immediate stop and report. |
| `created_by` | Operator, tool, or local actor creating the definition. |
| `created_at` | ISO-8601 timestamp. |
| `status` | Current lifecycle state. |
| `storage_class` | Must be `file_backed` in Phase 16. |
| `privacy_export_classification` | `local_only`, `exportable_with_redaction`, `aggregate_only`, or `non_exportable`. |

## Lifecycle States

Phase 16 definitions may use:

- `draft`
- `validated`
- `rendered`
- `observed`
- `result_recorded`
- `reported`
- `blocked`
- `cancelled`

Lifecycle records are file-backed local artifacts. Future event names may be documented by the ledger contract, but they do not imply real-runtime-DB event writes in Phase 16.

## Storage

Phase 16 storage is file-backed under Dream Studio-controlled state/meta paths such as:

- `~/.dream-studio/meta/work-orders/`
- `~/.dream-studio/projects/<project>/work-orders/`

Tests must use fake HOME or temp directories. Tests must not write to the real runtime DB or native backup files.

## Identifier Rules

`allowed_skills` must use canonical `ds-<slug>` identifiers.

Legacy product-name-prefixed skill identifiers and colon-delimited `ds` skill forms are rejected in Work Order definitions, rendered packets, result records, and eval artifacts.

## Relationship To Other Contracts

- Approval contract: owns approval modes, approval states, and mutation gates.
- Execution packet contract: owns target-specific render-only packet shape.
- Work result contract: owns result and report evidence shape.
- Work ledger contract: owns file-backed lifecycle records.
- Eval artifact contract: owns deterministic eval evidence.
- Human-in-the-loop contract: owns decisions that cannot be delegated.
- Governance contract: owns privacy/export classes and scanner evidence boundaries.
- Research-source contract: research remains advisory evidence.
- Portable execution contract: target runtimes are renderings, not authority.

## Prohibitions

Phase 16 Work Orders must not:

- create, alter, or require DB tables;
- add schema migrations;
- run migrations against the native runtime DB;
- repair, restore, downgrade, overwrite, or mutate native DB/backups;
- write Work Order events to the real runtime DB by default;
- mutate target repositories during create, validate, render, status, record-result, or report commands;
- stage, commit, push, patch, delete, move, or format target repo files;
- execute DreamySuite work before Phase 17;
- recreate the retired `hooks/lib` path;
- grant dashboards, telemetry, adapters, research, enterprise analytics, Docker, cloud, or org/global layers canonical authority.

## Validation Expectations

Static tests must prove:

- required fields are documented;
- storage class is `file_backed`;
- forbidden identifier forms are rejected;
- DB/schema/event integration is deferred;
- target repo mutation is prohibited for non-execution commands;
- authority limits remain explicit.
