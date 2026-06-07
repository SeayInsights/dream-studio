# Three-Store Model — Authoritative Reference

**Status:** CURRENT  
**Last reviewed:** 2026-06-07 (WO-P)

Dream Studio's data architecture is organized into three distinct stores with explicit boundaries between them.

---

## The Three Stores

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  STORE 1: Spool (Write Buffer)                                               │
│  ~/.dream-studio/spool/*.json                                                │
│  Role: asynchronous write buffer between emitters and the event store        │
│  Written by: emitters (CanonicalEventEnvelope → write_envelopes())           │
│  Read by: ingestor only                                                      │
│  Retention: consumed on ingest, purged                                       │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ ingestor picks up
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STORE 2: Canonical Event Store (Authority)                                  │
│  ~/.dream-studio/state/studio.db                                             │
│  Tables: business_canonical_events, ai_canonical_events                      │
│  View:   canonical_events (UNION compat view for existing readers)           │
│  Backup: canonical_events_legacy_backup (pre-WO-M rows, retired)            │
│                                                                              │
│  Role: single source of truth for all events                                 │
│  Written by: ingestor (dual-canonical write path, primary since WO-M)       │
│  Read by: projections, queries, CLI, dashboard API                           │
│  Retention: permanent (no TTL; rows are not deleted)                         │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │ projections read + compute
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  STORE 3: Business Authority (SQLite — same studio.db file)                  │
│  Tables: business_projects, business_milestones, business_work_orders,       │
│          business_tasks, token_usage_records, ds_eval_baselines,             │
│          ds_eval_runs, reg_gotchas, ds_eval_baselines, + 20 others          │
│                                                                              │
│  Role: operational state, project tracking, computed metrics                 │
│  Written by: DS CLI commands, work order lifecycle, event projections        │
│  Read by: dashboard API, projections, skills, hooks                          │
│  Retention: permanent operational record                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Boundary Rules

| From | To | Allowed? | Pattern |
|------|----|----------|---------|
| Emitter | Spool | ✓ | `write_envelopes([CanonicalEventEnvelope(...)])` |
| Emitter | Store 2/3 directly | ✗ | Never write directly; always go through spool |
| Ingestor | Spool (read) | ✓ | Reads and consumes spool files |
| Ingestor | Store 2 (write) | ✓ | Only the ingestor writes authority tables |
| Ingestor | Store 3 (write) | ✗ | No direct writes from ingestor |
| Dashboard API | Store 2/3 (read) | ✓ | Read-only via projection queries |
| CLI commands | Store 3 (write) | ✓ | DS CLI is the designated writer for business state |
| CLI commands | Store 2 (read) | ✓ | Read for token attribution, event queries |
| Hooks | Store 2/3 (read) | ✓ | Read-only intelligence |
| Hooks | Spool (write) | ✓ | May emit events via write_envelopes() |

---

## Data Flow Example: Skill Invocation

```
User invokes ds-quality:debug
    │
    ▼
Skill emits skill.invoked event
    │   CanonicalEventEnvelope(event_type="skill.invoked", trace={skill_specifier: "quality:debug"})
    │   write_envelopes([envelope])
    │
    ▼
Spool file created:  ~/.dream-studio/spool/<uuid>.json
    │
    ▼
Ingestor picks up file
    │   Routes to business_canonical_events (domain="sdlc")
    │
    ▼
business_canonical_events row inserted
    │
    ▼
canonical_events compat view reflects row immediately
    │
    ▼
Dashboard API reads /api/v1/skills/activity → queries canonical_events
```

---

## Table Vetting Rubric

When deciding whether a new table belongs in Store 2 (event substrate) or Store 3 (business authority):

| Question | Store 2 (Events) | Store 3 (Business) |
|----------|------------------|--------------------|
| Is it an immutable fact? | Yes | No — mutable state |
| Is it an audit trail? | Yes | No |
| Is it computed from events? | Derived only | Yes — operational state |
| Does it have a lifecycle (open/closed/pending)? | No | Yes |
| Is it written by the ingestor? | Yes | No — written by CLI |

---

## Related Docs

- [event-substrate.md](event-substrate.md) — Detailed four-table reference
- [event-store.md](event-store.md) — Event store implementation
- [event-schema-evolution.md](event-schema-evolution.md) — Schema evolution policies
- [DATABASE.md](../DATABASE.md) — Migration history and review markers
- [MIGRATION_AUTHORITY.md](../MIGRATION_AUTHORITY.md) — Migration authority rules
