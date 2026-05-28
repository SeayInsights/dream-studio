# Event Store Corruption Tolerance

## Status

ACTIVE — codifies existing pattern in `core/event_store/studio_db.py`

## Context

Dream Studio's event store (`canonical_events` table in studio.db) stores
event payloads as JSON. Over time, payloads may become malformed for various
reasons:

- Schema evolution where older events have different field shapes
- Manual data edits or imports
- Bugs in payload writers that emit invalid JSON
- Storage corruption (rare but possible)

When the event store reads these payloads during projection rebuilds,
migrations, or queries, malformed JSON would cause exceptions if not handled.

## Decision

The event store handles malformed JSON payloads via graceful degradation
rather than crash:

- Functions parsing event payloads catch `(json.JSONDecodeError, TypeError)`
  and return a fallback (empty dict, `None`, or sentinel value)
- The store continues processing remaining events
- Migration runners, projection builders, and query handlers do not crash
  due to one corrupted event

This pattern appears in 3 sites in `studio_db.py`, specifically in
projection/aggregation functions that iterate over `canonical_events` rows
and parse JSON column values:

```python
# Pattern — 3 occurrences in studio_db.py
if d.get(col):
    try:
        d[col] = json.loads(d[col])
    except (json.JSONDecodeError, TypeError):  # cq-006-suppress
        pass
```

## Rationale

The alternative — crashing on first corrupted event — has these failure modes:

- Migration runs become brittle; one bad row blocks all further migration
- Projection rebuilds fail entirely instead of rebuilding what they can
- Operator must manually clean up corrupted rows before any further work
- Recovery from corruption is harder when the recovery tooling also crashes

Graceful degradation accepts a tradeoff: corruption is silently tolerated
rather than loudly surfaced. This is acceptable at current Dream Studio scale
(single-user, local-first, operator has full system visibility).

## Tradeoffs — Honest Assessment

**What this decision does NOT have:**

- No metric tracking the malformed-payload rate. Suppressed exceptions are
  not counted, logged at WARN/ERROR level, or surfaced in any dashboard.
- No alerting on elevated malformed-payload rates.
- No periodic audit of `canonical_events` for malformed payloads.

**Implications:**

- A bug silently corrupting a significant fraction of new payloads would be
  invisible until downstream queries return obviously-wrong results.
- We have no baseline for "normal" corruption rate vs. "elevated."

This is a known gap. It is acceptable at current scale and operator context
(single-user, local-first) but would not be acceptable in a multi-tenant or
production-scale deployment.

## Future Work

If/when Dream Studio adds telemetry or moves to a less single-operator
context, this decision should be revisited:

- Add a counter for malformed-payload occurrences (increment on each catch)
- Log at `WARN` level with payload ID for forensic analysis
- Surface malformed-payload count in the Dream Studio dashboard
- Alert on rate exceeding a configurable baseline threshold

## Suppression Pattern

The `ds-quality:code-quality` rule `cq-006` (no silent failures) correctly
identifies these `except: pass` sites as code quality findings. The inline
suppression pattern applied at each site is:

```python
except (json.JSONDecodeError, TypeError):  # cq-006-suppress: intentional graceful degradation on malformed event payload. See: docs/architecture/event-store-corruption-tolerance.md
    pass
```

Each suppression site is reviewed individually rather than path-globbed,
requiring future developers copying the pattern to consciously include the
suppression comment and its rationale.

## Related

- `ds-quality:code-quality` rule `cq-006` (no silent failures)
- `core/event_store/studio_db.py` — 3 JSON parsing suppression sites
- `18.4.3-followup-3` — inline suppression application to studio_db.py
