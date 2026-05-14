# Skill Contract

Phase: 11Y - Portable Primitive Contracts

Dream Studio skills are portable instruction primitives. They describe how work should be performed across tool runtimes without owning canonical state.

## Required Fields

Each active skill or mode must define:

- `skill_id`: canonical identifier in `ds-<slug>` form.
- `purpose`: what the skill is for and when it should be invoked.
- `inputs`: required user intent, artifacts, context, or state.
- `required context`: files, contracts, reports, or project facts that must be read before acting.
- `allowed tools`: tool categories the skill may use.
- `forbidden actions`: actions the skill must not perform.
- `output contract`: the shape of the final response or artifact.
- `validation expectations`: commands, checks, or evidence needed before completion.
- `event/telemetry obligations`: what local evidence may be recorded and which owner records it.
- `security/governance constraints`: privacy, export, approval, and authority limits.
- `adapter/rendering expectations`: how the skill can be rendered for each target runtime.

## Authority

Skills may guide execution, choose workflows, request tools, and define output expectations. Skills do not own local canonical runtime state, canonical events, projections, dashboards, adapters, governance records, Docker state, cloud state, or org/global state.

If a skill needs persistence, the owning core/runtime interface must make the write. A skill may describe the intent and artifact, but it must not invent or call retired persistence helpers.

## Identifier Rules

- Active metadata, routing manifests, and tests must use `ds-<slug>` identifiers.
- Docs and examples may mention product names or historical command syntax when clearly labeled as documentation, but they must not redefine canonical skill identity.
- Do not change existing canonical skill IDs without a contract update and migration plan.

## Relationships

- Events: skill activity may emit or record events only through the event contract owner.
- State: skill output may become state only through the state contract owner.
- Projections: dashboards may summarize skill activity as derived data.
- Adapters: target-specific renderers may translate skill instructions, but adapter output is not skill authority.
- Governance: skill outputs must preserve privacy/export classification and approval requirements.

## Portable Rendering

Skill rendering must be target-specific but semantically equivalent:

| Target | Rendering expectation |
| --- | --- |
| Claude | Render as Claude-compatible skill or routing instructions. |
| Codex | Render as Codex-compatible local instructions and task routing. |
| ChatGPT | Render as custom instructions, project instructions, or tool-specific prompt blocks. |
| Cursor | Render as editor/project rules. |
| MCP tools/local models | Render as prompt/tool policy with explicit allowed and forbidden actions. |
| Docker validation/sandbox | Render only for isolated validation; do not mount or mutate real local state. |

Rendering must not make the target tool, adapter, dashboard, telemetry stream, Docker container, or provider canonical authority.

## Validation Expectations

Tests should verify:

- active skill IDs use `ds-<slug>`;
- active skill instructions do not reference retired hook helper paths;
- skills name their allowed/forbidden boundaries;
- target-specific renderers remain non-authoritative;
- validation evidence is fresh before completion claims.
