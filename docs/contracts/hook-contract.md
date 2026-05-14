# Hook Contract

Phase: 11Y - Portable Primitive Contracts

Dream Studio hooks are portable runtime trigger primitives. They react to canonical Dream Studio trigger events and may be rendered into target-specific hook systems.

## Required Fields

Each hook must define:

- `hook_id`: stable hook identity.
- `canonical Dream Studio trigger event`: tool-agnostic event name, such as prompt submitted, tool used, skill completed, edit completed, stop requested, or compact completed.
- `target adapter event mapping`: how the canonical trigger maps to Claude, Codex, ChatGPT, Cursor, MCP/local model, or Docker sandbox events.
- `conditions`: matcher, file pattern, skill, command, or payload conditions.
- `actions`: handler actions and side effects.
- `artifacts`: output files, reports, logs, or emitted records.
- `allowed state access`: read-only, diagnostic write, governance write, or no state access.
- `failure behavior`: whether failures block, warn, log, or silently skip.
- `event emissions`: approved event/decision emissions, if any.
- `adapter/tool-specific implementation mapping`: target-specific runner, manifest, or launcher entry.

## Canonical Location

Active Dream Studio hook implementations live under:

```text
runtime/hooks
```

The retired root hook library path remains absent and must not be recreated:

```text
hooks/lib
```

Launchers and target manifests may call handlers under `runtime/hooks`, but they do not become hook authority.

## Authority

Hooks may observe tool/runtime events, run local checks, write approved diagnostic/governance records, and emit approved events. Hooks do not own canonical state, event truth, workflow authority, projection truth, dashboard authority, adapter authority, Docker authority, cloud authority, or org/global state.

If a hook writes state, it must use the owner named by the event, state, projection, adapter, or governance contract.

## Portable Rendering

| Target | Rendering expectation |
| --- | --- |
| Claude | Map canonical trigger events to Claude hook manifest events. |
| Codex | Map canonical trigger events to Codex-supported local instructions or future hook surfaces. |
| ChatGPT | Map canonical trigger events to available project/tool automation points. |
| Cursor | Map canonical trigger events to editor rules or task hooks when available. |
| MCP tools/local models | Map canonical trigger events to explicit tool wrapper calls. |
| Docker validation/sandbox | Run handlers only against disposable state and synthetic payloads. |

Target event names are adapter mappings. Canonical hook identity is the Dream Studio `hook_id` and trigger event, not the target runtime name.

## Governance And Privacy

Hooks must not record secrets, raw prompts, raw sessions, credentials, or private payloads unless an owning contract explicitly classifies that record. Scanner/security hooks produce evidence only.

## Validation Expectations

Tests should verify:

- `runtime/hooks` remains the canonical active implementation location;
- the retired hook library path remains absent;
- hook contracts include trigger, mapping, state access, failure, and event rules;
- hooks do not import provider SDKs or adapter packages directly;
- hook validation does not mutate native DB/backups unless explicitly opted in.
