# Canonical Event Contract

Phase: 7A - Canonical Event Contract

Dream Studio is a local-first, AI-agnostic, federated operational intelligence platform for AI-assisted work. The canonical event contract protects that identity by keeping local runtime events authoritative and by treating dashboards, telemetry, adapters, and future cloud layers as consumers or emitters through explicit contracts only.

## Authority

The canonical event stream is local runtime state. The authoritative persisted stream is the `canonical_events` table guarded by `core.validation.event_validator.EventValidator` and `docs/canonical/canonical_event_v1_schema.json`.

Current companion tables:

- `validation_failures`: diagnostic record for rejected canonical writes.
- `activity_log`: legacy operational activity stream that can dual-write through `core.event_store.legacy_bridge.LegacyBridge`.
- `execution_event_links`: execution graph relationship table that references event identifiers without becoming the event stream.

Current authoritative emit path:

- `core.events.emitter.emit_event(...)`
- `core.event_store.legacy_bridge.LegacyBridge.emit_from_legacy(...)`
- `core.event_store.event_store.EventStore.write_event(...)`

Current reader path:

- `EventStore.query_events(...)`
- projection consumers that read local canonical or legacy state and produce derived views.

Dashboards, API routes, telemetry views, memory indexes, adapter outputs, and future cloud or org/global layers do not own event truth.

## Event Envelope

The Phase 7A logical event envelope contains these semantic slots:

| Slot | Current v1 representation | Rule |
| --- | --- | --- |
| `event_id` | Root field | Stable UUID for one immutable event. |
| `event_type` | Root field | Registered taxonomy value in `domain.entity.action` form. |
| `schema_version` | Taxonomy/schema artifact version, not a root v1 field | Export manifests and future schema versions must state the version used. Root v1 events must not add this field without a schema migration. |
| `source` | Payload metadata, actor details, or export metadata. Current `source_type` is provenance confidence, not subsystem identity. | Identifies the emitting subsystem without granting authority to that subsystem. |
| adapter/tool/model metadata | Payload metadata, adapter `metadata`, or actor details | Execution details are evidence attached to the event. They do not make an adapter, model, or tool the source of architecture truth. |
| subject/resource | Payload fields and trace identifiers | Names the resource acted on. Future root promotion requires a versioned schema change. |
| `timestamp` | Root field | ISO-8601 UTC timestamp. The serialized UTC form may use `Z`. |
| correlation/session/workflow IDs | `trace` object | At least one trace ID is required. Trace is for correlation, not authorization. |
| `payload` | Root field | Event-specific JSON body. Payload content must be replayable without requiring dashboard, adapter, or telemetry ownership. |
| privacy/export classification | Payload or export metadata in v1 | Default classification is local runtime detail unless an export path explicitly classifies it. Root promotion requires a versioned schema change. |

The persisted v1 root fields are intentionally stricter than the logical envelope:

- Required: `event_id`, `event_type`, `timestamp`, `trace`, `severity`, `payload`.
- Optional: `actor`, `confidence_score`, `source_type`.
- Current `source_type` values are `confirmed`, `inferred`, and `weak_inference`.
- No additional root fields are allowed in v1.

## Versioning Rules

1. `event_type` values are governed by `docs/canonical/event_taxonomy_v1.json`.
2. Persisted root envelope shape is governed by `docs/canonical/canonical_event_v1_schema.json`.
3. Additive payload changes are allowed when existing readers can ignore unknown payload keys.
4. New root fields, renamed root fields, removed root fields, changed severity values, and changed trace constraints require a new schema version.
5. Breaking schema changes require dual-read compatibility during migration. Existing immutable events are never rewritten to appear newer than they are.
6. Legacy `activity_log` records may be bridged into canonical events, but legacy table shape is not the canonical event contract.

## Replay Expectations

Replay must read immutable canonical events in timestamp order with a deterministic tie-breaker on `event_id` when needed. Replay may rebuild projections, workflow views, memory indexes, graph links, or audit summaries. Replay must not require dashboards, API routes, telemetry streams, adapters, model providers, or cloud services to act as source of truth.

Validation failures are diagnostic evidence. They may be audited and counted, but the rejected attempted event is not a canonical event.

## Export Expectations

Exports must preserve:

- `event_id`
- `event_type`
- schema or taxonomy version used for interpretation
- timestamp
- trace/correlation identifiers
- payload
- source and execution metadata when present
- privacy/export classification supplied by the export path

Exported projections are snapshots derived from local canonical state. They must not become upstream authority when re-imported unless an explicit import contract is defined in a later phase.

## What Is Not An Event

These are not canonical events by themselves:

- Dashboard cards, charts, counters, and API response rows.
- Raw telemetry counters, spans, logs, or metrics that have not passed the event validator.
- Adapter return objects before normalization and validation.
- Memory search index rows.
- Projection rows and graph convenience tables.
- Configuration rows, registry rows, and cached discovery results.
- Validation failure records for rejected events.
- Cloud/org/global aggregate records unless a future local import contract validates them as events.

## Boundary Rules

1. Core owns validation and persistence for canonical events.
2. Adapters may normalize and emit through explicit interfaces; they must not directly own the event store.
3. Projections and dashboards read local state and may derive views; they must not mutate canonical event truth.
4. Telemetry may observe runtime behavior; it must not replace orchestration or event authority.
5. Future cloud/org/global layers may aggregate selected projections only. They must not become canonical architecture authority.
6. Phase 7A does not require schema churn. Any schema change discovered during contract testing must stop Phase 7A and become a targeted follow-up.
