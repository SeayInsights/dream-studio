# Workflow Contract

Phase: 11Y - Portable Primitive Contracts

Dream Studio workflows are declarative execution plans. They coordinate skills, agents, gates, artifacts, and validation without becoming canonical state owners.

## Required Fields

Each workflow definition must provide or derive:

- `workflow_id`: stable workflow identity, usually matching the workflow filename/name.
- `states`: allowed lifecycle states such as pending, running, paused, blocked, failed, skipped, completed, and aborted.
- `transitions`: allowed state changes and the condition that permits each change.
- `gates`: pause, approval, evidence, or conditional gates.
- `required artifacts`: files, reports, screenshots, tests, or decisions needed to proceed.
- `stop conditions`: conditions that halt execution.
- `approval points`: explicit human/operator approvals.
- `rollback/recovery rules`: how to resume, abort, retry, or preserve state after failure.
- `validation commands`: commands or checks that prove the workflow result.
- `event emissions`: local events or decisions emitted by the owning runtime interface.
- `local state authority boundaries`: which owner may persist workflow state.
- `portable rendering expectations`: how nodes and gates map to each target runtime.

## Authority

Workflows may order work and require evidence. They do not own canonical runtime state, canonical events, execution graph state, decisions, governance records, projections, dashboards, adapters, Docker state, or cloud/org state.

Workflow state must be persisted only by the owner named in the state contract or by an explicitly contracted workflow runner. Workflow templates remain stateless.

## Relationships

- Events: workflow lifecycle events must be emitted through approved event interfaces.
- State: active and archived workflow state belongs to the state contract owners.
- Projections: workflow metrics and dashboards are derived.
- Adapters: tool-specific workflow runners translate nodes and gates but do not own workflow truth.
- Governance: approval gates, stop conditions, and evidence requirements are governance signals.

## Portable Rendering

| Target | Rendering expectation |
| --- | --- |
| Claude | Map nodes to skills, commands, and optional sub-agent dispatch. |
| Codex | Map nodes to local instructions, explicit tool calls, and validation gates. |
| ChatGPT | Map nodes to task instructions and artifact checkpoints. |
| Cursor | Map nodes to editor tasks and project rules. |
| MCP tools/local models | Map nodes to explicit tool invocations with allowed state access. |
| Docker validation/sandbox | Run only isolated validation workflows that do not mount real runtime state. |

Rendering must preserve gates and stop conditions. It must not convert workflow output into canonical state unless the owning runtime interface writes it.

## Validation Expectations

Tests should verify:

- workflow templates are declarative;
- retired helper paths are absent from active workflow instructions;
- gates and stop conditions are explicit;
- workflow runners are non-authoritative adapters;
- validation commands do not mutate real local runtime DB/backups.
