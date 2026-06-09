# Event Schema Evolution Policy

Part of the [Substrate Policy](substrate-policy.md).

## The problem

Dream Studio has ~85 registered event types.  Payload schemas are enforced
implicitly — each emitter constructs the payload as a plain dict.  Projection
runners access payload fields via `event["payload"].get("field_name")`.

A field rename or removal breaks every projection and historical replay
silently: the old events are still in `business_canonical_events` with the old
field name, but the updated projection reads the new name and gets `None`.

## Additive-only rule

> Event payload fields may only be **added** (optional, accessed via
> `.get(key, default)` in projections).  Existing payload fields must **never**
> be removed, renamed, or have their Python type changed.
>
> If a change of this kind is necessary, register a new `event_type` string.
> The new event type carries the updated schema.  Old projections continue to
> handle the old type; new projections handle the new type.  Historical events
> replay correctly because each event's type is immutable.

## Breaking-change naming convention

When additive-only cannot accommodate a change, register a new event type
using the dot-v suffix convention:

```
work_order.created    → original
work_order.created.v2 → first breaking change
work_order.created.v3 → second breaking change
```

**Required format:** `<original_event_type>.v<N>` where N is an integer ≥ 2.

**Never use:** `work_order.created_v2`, `work_order_created_v2`,
`work_order.created.2`.

This convention is enforced by `tests/unit/config/test_event_schema_evolution_policy.py::TestRegistryIntegrity::test_versioned_naming_convention`.

## Registry enforcement: payload_required_keys

`config.event_type_registry.RegistryEntry` carries an optional
`payload_required_keys: frozenset[str]` field.  This is populated for every
event type consumed by at least one projection.

```python
RegistryEntry(
    "work_order.closed",
    _BUSINESS,
    "meaningful-unit",
    "Work order closed after gate checks passed",
    payload_required_keys=frozenset({"work_order_id", "title", "project_id", "forced"}),
)
```

Current entries with required keys (as of Phase 18.1.11):

| Event type | Required payload keys |
|------------|-----------------------|
| `work_order.created` | `title`, `status`, `type` |
| `work_order.started` | `work_order_id`, `title`, `type`, `project_id` |
| `work_order.blocked` | `work_order_id`, `title`, `project_id`, `reason` |
| `work_order.unblocked` | `work_order_id`, `title`, `project_id` |
| `work_order.closed` | `work_order_id`, `title`, `project_id`, `forced` |

When 18.2.3 adds `task.*` and `milestone.*` projections, those event types
must have their `payload_required_keys` populated at the time their projections
are written.

## Enforcement layers

### Layer 1 — Runtime validation at write_event()

`spool.writer.write_event()` looks up the event type's `payload_required_keys`
and validates the payload before writing to the spool file.  Raises
`ValueError` immediately with a clear message if a required key is absent.

This catches emitter bugs before the event reaches the canonical store.  The
overhead is one dict lookup plus one set comparison per emit.

### Layer 2 — Fixture-based CI test

`tests/unit/config/test_event_schema_evolution_policy.py` maintains a
known-good payload fixture for every registered event type with
`payload_required_keys`.  The test verifies:

1. The fixture payload contains all required keys (catches registry drift).
2. `write_event()` raises `ValueError` when any required key is absent.
3. `write_event()` succeeds when all required keys are present.
4. Registry naming convention is valid for all versioned event types.

When adding `payload_required_keys` to a new event type, add the
corresponding fixture payload to `_GOOD_PAYLOADS` in the test file.

## Backward compatibility: projection access pattern

All projections must access payload fields via `.get(key, default)`, not
direct subscript `payload["key"]`.  This ensures historical events that
pre-date the populated registry entry replay without modification.

**Verified for current projections (Phase 18.1.11):** `WorkOrderProjection`
accesses all required keys via `payload.get(key, default)`.  Historical events
in `business_canonical_events` that pre-date the populated registry entries
replay without modification.

## Known gap: type-change detection

The `payload_required_keys` enforcement catches key presence.  It does NOT
catch type changes: if `work_order_id` changes from `str` to `int`, the key
is still present and enforcement passes.

Type-change detection (`payload_required_types`) is a follow-up enhancement
filed for a future phase.  Until implemented, type changes are policy
violations detectable only by code review.

## When to add payload_required_keys

Add `payload_required_keys` to a registry entry when:
1. The event type is consumed by at least one projection.
2. The required keys are stable and have been validated against the current
   emitter source (see backward compatibility section above).

Do NOT add required keys for event types consumed only by hooks or skills;
those consumers are not replay-sensitive.
