# Adapter Contract

Phase: 7D - Adapter Contract

Dream Studio is a local-first, AI-agnostic, federated operational intelligence platform for AI-assisted work. The adapter contract lets Claude, ChatGPT, Codex, Cursor, MCP tools, local models, GitHub operations, and future tools participate without making any vendor, tool runtime, dashboard, telemetry stream, or cloud surface canonical.

## Authority Principles

1. Local canonical runtime state remains authoritative.
2. Adapters translate external or tool-specific shapes into Dream Studio contract shapes. They do not own persistence.
3. Core modules may call adapter interfaces only through explicit boundaries that preserve local event, state, projection, and governance authority.
4. Vendor or tool metadata is evidence. It is not architecture truth.
5. Optional provider support must degrade through a documented fallback, not through hidden required imports.
6. Adding a provider package, remote tool requirement, or direct state write to an adapter path is a contract change.

## Adapter Responsibilities

Adapters may:

- Connect external AI, tool, model, runtime, repository, or framework surfaces to Dream Studio.
- Normalize external output into event-compatible and state-compatible shapes.
- Attach adapter, tool, model, version, performance, and health metadata.
- Emit through approved event/state interfaces owned by core modules.
- Consume approved orchestration, context, and workflow state through read contracts.
- Report health/status as projection, diagnostic, or adapter metadata.
- Remain replaceable by providing the same contract shape with no canonical state migration.

Adapters must:

- Be deterministic for the same input when they are normalizers.
- Avoid external API calls during synchronous normalization.
- Avoid direct database writes unless the adapter is an explicitly classified execution/governance path and writes through an owning core interface.
- Preserve enough metadata for audit while avoiding credentials, secrets, and unnecessary PII in payloads.
- Treat `source_type` according to the event contract: provenance confidence, not emitter identity.

## Adapter Prohibitions

Adapters must not:

- Own canonical event, operational state, projection authority, or dashboard truth.
- Insert, update, or delete canonical runtime tables directly.
- Open the Dream Studio state database from `interfaces/adapters`.
- Require a vendor SDK in core import paths.
- Make a dashboard, telemetry stream, cloud service, MCP server, model, or company deployment authoritative.
- Rewrite canonical event root fields without a versioned event contract.
- Promote telemetry, provider billing data, tool output, or model confidence into execution, decision, governance, or memory state without the owning core module making the transition.
- Recreate `hooks/lib`.

## Current Adapter Status

| Surface | Status | Class | Boundary |
| --- | --- | --- | --- |
| `interfaces/adapters/base.py` | required interface | normalizer contract | Defines `BaseAdapter.normalize`; no persistence, network, subprocess, or provider SDK imports. |
| `interfaces/adapters/models.py` | required DTO layer | adapter event DTO | Provides `CanonicalEvent` and `TraceContext` for legacy normalization. It is not the persisted event v1 root schema authority; the Phase 7A event contract and validator remain authoritative. |
| `interfaces/adapters/normalizer.py` | required dispatcher | bootstrap-loaded normalizer | Routes raw output to registered adapters and default fallback. It returns normalized objects only. |
| `interfaces/adapters/default_adapter.py` | optional fallback implementation | adapter implementation | Local fallback for unknown model output. No provider package or persistence authority. |
| `interfaces/adapters/claude_adapter.py` | optional provider normalizer | adapter implementation | Parses Claude-shaped dictionaries and objects. Does not import Anthropic SDK or call Claude APIs. |
| `interfaces/adapters/gpt_adapter.py` | optional provider normalizer | proof-of-concept adapter implementation | Parses OpenAI-shaped dictionaries. Does not import OpenAI SDK or call OpenAI APIs. |
| `core.event_store.studio_db` adapter bootstrap | required by legacy skill/activity logging | explicit core integration exception | Core owns the database write. The adapter normalizer supplies shape and metadata only. |
| `runtime/hooks/meta/on-skill-complete.py` | hook consumer | runtime caller of core logging | Calls `studio_db.log_skill_execution`; it does not import adapters or write state directly. |
| `core/event_store/migrations/030_adapter_metadata.sql` | diagnostic schema | adapter metadata table | `adapter_executions` is metadata linked to `activity_log`, not canonical execution or event authority. |
| `control.analysis.stacks.*` | local framework analyzers | stack adapters, not AI/model adapters | Detect and summarize repository frameworks. They do not represent provider authority. |
| `core.execution.github_adapter` | explicit execution tool adapter | core execution adapter | Uses local `git`/`gh` operations and emits decisions/events through core interfaces. It does not own canonical architecture or state. |
| `control.analysis.engine` normalizer import | optional legacy enrichment | canonical adapter import | Canonical events are emitted through `core.events.emit_event`; optional activity-log normalization uses `interfaces.adapters` and remains an enrichment path, not event authority. |
| `interfaces/cli/benchmark_normalizer.py` and `examples/adapter_usage_example.py` | non-runtime tooling/examples | canonical adapter imports | Tooling and examples import `interfaces.adapters` directly. They must not introduce a top-level `adapters` package dependency. |

## Boundary Checklist

Before adding or changing an adapter, verify:

- The adapter's canonical role is named: normalizer, execution adapter, discovery adapter, governance ingestion adapter, or projection/service adapter.
- The owning core interface is named for every persistence side effect.
- Direct writes to `canonical_events`, `activity_log`, `execution_nodes`, `decision_log`, `memory_entries`, `risk_register`, or other canonical tables are absent from `interfaces/adapters`.
- Vendor SDK imports are absent from core import paths unless a future contract explicitly makes the package optional and lazy.
- The adapter can be replaced without migrating canonical local state.
- Metadata says which tool/model/provider produced evidence without claiming architecture authority.
- Health/status output is diagnostic or projection state, not orchestration truth.
- Tests use temp files or static inspection and do not touch the real runtime DB.

## Import And Dependency Audit

Production vendor package imports:

- No direct `openai`, `anthropic`, `litellm`, `ollama`, `mistralai`, `cohere`, `groq`, `cursor`, `mcp`, or `claude` package imports were found under `core`, `control`, `runtime`, `projections`, or `interfaces`.
- Claude and GPT identifiers appear as data shapes, tests, telemetry examples, or adapter metadata. They are not vendor package dependencies.

Runtime imports into `interfaces.adapters`:

- `core/event_store/studio_db.py` imports `EventNormalizer`, `ClaudeAdapter`, `CanonicalEvent`, and `TraceContext`. This is an explicit bootstrap integration because core owns the `activity_log`/legacy bridge writes.
- `control/analysis/engine.py` imports `EventNormalizer` and `TraceContext` from `interfaces.adapters`. Because canonical events are emitted through `core.events.emit_event`, this is classified as optional activity-log enrichment rather than canonical authority.
- `runtime/hooks` do not import adapter interfaces directly.
- `projections` do not import adapter interfaces directly.
- Top-level `from adapters import ...` residue was removed in Phase 10C. New runtime, tooling, and example code should import `interfaces.adapters` explicitly.

Tool and execution adapter dependencies:

- `core.execution` exposes GitHub, CI, and feedback tool classes through lazy package attributes. `core.execution.github_adapter` requires local `git` and `gh` commands when that adapter is explicitly instantiated. Those commands are execution tooling, not core import requirements for event/state/projection contracts.
- Stack adapters under `control.analysis.stacks` inspect local files and produce analysis context. They are not AI/provider adapters.
- MCP and API tool records in discovery tests and registries are catalog entries. Tool registry rows do not install providers or make them authoritative.
- Runtime skill hooks and skill logging keep provider/model labels as metadata. `DREAM_STUDIO_MODEL` and compatibility `CLAUDE_MODEL` values may be recorded when present; provider-neutral fallback metadata is `unspecified`.

## Event And State Interactions

Adapter-normalized objects may feed:

- `core.event_store.studio_db` legacy `activity_log` writes.
- Canonical event emission through `core.events.emit_event` or `core.event_store.legacy_bridge.LegacyBridge`.
- Diagnostic adapter metadata such as `adapter_executions`.

The persisted canonical event contract remains stricter than adapter DTOs. Adapter DTO fields such as `entity_type`, `entity_id`, and `metadata` must be mapped into v1 payload, trace, actor, or export metadata unless a future versioned schema promotes them.

Operational state transitions remain owned by the state contract. An adapter may recommend, normalize, or report evidence, but workflow, execution, decision, governance, telemetry, and memory ownership stays with the modules listed in `docs/contracts/state-contract.md`.

Projection and dashboard surfaces consume adapter metadata as derived or diagnostic data. They must not use adapter health, model status, or provider telemetry as canonical state.

## Existing Exceptions And Risks

- `core.event_store.studio_db` imports adapter interfaces at module load so skill execution logging can normalize legacy activity records. This is required bootstrap behavior today, but it must remain free of vendor SDK imports and direct adapter-owned persistence.
- `control.analysis.engine` contains optional activity-log enrichment through `interfaces.adapters`. It is not canonical event authority because `emit_event` remains the authoritative event path.
- `interfaces/adapters/normalizer.py` and `interfaces/adapters/default_adapter.py` both define a `DefaultAdapter`. This is a compatibility duplication, not a state authority split.
- `adapter_executions` exists as diagnostic metadata but currently has no authoritative writer. A future writer must be owned by core and tested as diagnostic metadata.
- `core.execution.github_adapter` can perform external repository operations after explicit lazy access and instantiation. It must stay opt-in, local-first, and contract-bound; it must not imply GitHub is canonical architecture authority.

## Replay, Export, And Health Expectations

- Replay must not require a provider, model, SDK, dashboard, or adapter process.
- Exported adapter metadata must be labeled as evidence or diagnostic context.
- Adapter health reports may explain degraded capability, missing local tools, or unavailable provider credentials. Health reports do not block canonical replay unless a caller explicitly chooses that adapter for execution.
- Imports of exported adapter metadata must not promote provider state to canonical state without a future import contract.

## Schema Posture

Phase 7D does not require schema changes. The existing `adapter_executions` metadata table is sufficient for diagnostic adapter tracking. Any future schema change for adapter health, provider capability, model registry, or execution metadata must include a targeted migration, ownership matrix update, and boundary tests.
