# Dream Studio Substrate Policy

The **substrate** is the canonical event layer: `business_canonical_events` is
the source of truth; `business_work_orders`, `business_milestones`, and the
other L3 tables are derived views built by projection runners.

Two policies govern every interaction with the substrate.  They are
load-bearing together: violating either one produces silent data inconsistency
or replay breakage.

---

## Policy 1 — Read-after-write convergence

**Problem:** Writers emit events to the spool.  The projection runner applies
those events to the L3 tables on a ~5 s poll cycle.  Any read against an L3
table within that window sees stale state.

**Rule:** Pattern C — optimistic return with named exclusion and
canonical-events fallback.

→ See [read-after-write-convergence.md](read-after-write-convergence.md)

---

## Policy 2 — Event schema evolution

**Problem:** Projection runners and future replay pipelines depend on specific
payload fields being present in canonical events.  A rename or removal of a
payload field breaks every projection and every historical replay silently.

**Rule:** Additive-only.  Payload fields may only be added; existing fields
must never be removed, renamed, or have their Python type changed.  Breaking
changes require a new event_type string.

→ See [event-schema-evolution.md](event-schema-evolution.md)

---

## Why both policies are required together

Policy 1 makes individual function chains correct under projection lag.
Policy 2 makes replay correct across the full event history.  A system that
satisfies only one policy is still broken: correct reads today do not
compensate for replay failures tomorrow, and stable schemas do not compensate
for stale reads in the CLI.
