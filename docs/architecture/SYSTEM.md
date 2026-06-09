# DREAM STUDIO — SYSTEM ARCHITECTURE

> **ASPIRATIONAL** — Some CONTROL layer ingestion items (AI chat logs → events, intent parsing → events) describe directions not yet fully implemented. Review against current canonical event substrate before acting on architecture details. (Flagged: WO-P 2026-06-07)

**Version:** 3.0 (Architecture-based)  
**Date:** 2026-05-07  
**Type:** Event-sourced engineering intelligence platform

---

## ARCHITECTURAL OVERVIEW

Dream Studio is an **event-sourced system** with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────────┐
│ CORE (Source of Truth)                                      │
│ - Events (canonical event definitions)                      │
│ - Validation (schema enforcement)                           │
│ - Event Store (append-only ledger)                          │
│ - Telemetry (execution tracking)                            │
│ - Identity (actor tracking, lightweight)                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
            [immutable events flow downward]
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ CONTROL (Event Producers)                                   │
│ - Ingestion (AI chat logs → events)                         │
│ - Research (multi-source fetch → events)                    │
│ - Business (intent parsing → events)                        │
│ - Execution (workflow orchestration → events)               │
│ - Contracts (PRD → OpenAPI → events)                        │
└─────────────────────────────────────────────────────────────┘
                              ↓
            [events stored in event ledger]
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ PROJECTIONS (Read Models)                                   │
│ - PRD (event-sourced PRD reconstruction)                    │
│ - Dashboards (SQL views, aggregations)                      │
│ - Analytics (metrics, insights)                             │
│ - Timeline (chronological event views)                      │
└─────────────────────────────────────────────────────────────┘
                              ↑
            [read-only queries]
                              ↑
┌─────────────────────────────────────────────────────────────┐
│ INTERFACES (External Interaction)                           │
│ - CLI (command-line interface)                              │
│ - API (FastAPI REST endpoints)                              │
│ - Web (future dashboard UI)                                 │
│ - Webhooks (event subscriptions)                            │
└─────────────────────────────────────────────────────────────┘
```

---

## DESIGN PRINCIPLES

### 1. **Event Sourcing**
- Events are immutable truth
- All state is derived from events
- Projections are disposable (can be rebuilt)

### 2. **Clear Responsibilities**
- **CORE:** Defines truth (events, validation)
- **CONTROL:** Produces events (write side)
- **PROJECTIONS:** Interprets events (read side)
- **INTERFACES:** Exposes system externally

### 3. **Separation of Concerns**
- Event production ≠ event interpretation
- Write model ≠ read model
- Internal logic ≠ external API

### 4. **Minimal by Default**
- No premature abstractions
- No speculative features
- Expand only when needed

---

## DIRECTORY STRUCTURE

```
dream-studio/
│
├── core/                       # Source of truth
│   ├── events/                 # Canonical event definitions
│   ├── validation/             # Event schema validation
│   ├── event_store/            # Append-only event ledger
│   ├── telemetry/              # Execution tracking
│   └── identity/               # Actor tracking (lightweight)
│
├── control/                    # Event producers (write side)
│   ├── ingestion/              # AI chat logs → events
│   ├── research/               # Multi-source research → events
│   ├── business/               # Business intent → events
│   ├── execution/              # Workflow orchestration
│   └── contracts/              # PRD → OpenAPI contracts
│
├── projections/                # Read models (event consumers)
│   ├── prd/                    # Event-sourced PRD reconstruction
│   ├── dashboards/             # SQL views, aggregations
│   ├── analytics/              # Metrics, insights
│   └── timeline/               # Chronological event views
│
├── interfaces/                 # External interaction layer
│   ├── cli/                    # Command-line interface
│   ├── api/                    # FastAPI REST endpoints
│   ├── web/                    # Dashboard UI (future)
│   └── webhooks/               # Event subscriptions
│
├── runtime/                    # Environment-specific configs
│   ├── home/                   # Personal use config
│   ├── work/                   # Work environment config
│   └── enterprise/             # Enterprise deployment config
│
└── docs/
    ├── architecture/           # System design docs
    ├── decisions/              # ADRs (Architecture Decision Records)
    ├── examples/               # Usage examples
    └── guides/                 # Implementation guides
```

---

## MODULE RESPONSIBILITIES

### **core/events/**
- Canonical event schema (CanonicalEventV1)
- Event type registry (allowed event types)
- Event taxonomy (domain.entity.action naming)

### **core/validation/**
- Schema compliance checking
- Event type format validation
- Trace completeness validation
- Referential integrity checks

### **core/event_store/**
- Validation gateway (invalid events blocked)
- Append-only event persistence
- Event query interface

### **core/telemetry/**
- Execution logging (workflow runs)
- Token usage tracking (hierarchical)
- Performance metrics

### **core/identity/**
- Actor tracking (user, org, service account)
- Lightweight identity (RBAC-ready but not implemented)

---

### **control/ingestion/**
- Parse external AI chat logs (Claude, GPT)
- Extract events with confidence scores
- Emit ingestion.* events

### **control/research/**
- Multi-source research (web, GitHub, local)
- Source ranking
- Emit research.* events

### **control/business/**
- Parse business input → requirements
- Business intent extraction
- Emit business.* events

### **control/execution/**
- Workflow orchestration
- Retry logic (exponential backoff)
- Execution state tracking

### **control/contracts/**
- PRD → OpenAPI spec generation
- Contract generation events

---

### **projections/prd/**
- Event-sourced PRD reconstruction
- Technical vs Business projections
- Snapshot caching (non-authoritative)

### **projections/dashboards/**
- SQL views (aggregations, summaries)
- Pre-computed metrics

### **projections/analytics/**
- Token usage rollups
- Execution analytics
- Risk scoring

### **projections/timeline/**
- Chronological event views
- Audit trails

---

### **interfaces/cli/**
- Command-line interface
- Skill invocation
- Event emission commands

### **interfaces/api/**
- FastAPI REST endpoints
- Event query API
- Projection API (PRD, dashboards)

### **interfaces/web/**
- Dashboard UI (future)
- Visualization layer

### **interfaces/webhooks/**
- Event subscriptions
- External system notifications

---

## DATA FLOW

### Write Path (Event Production)
```
External Input
    ↓
Control Module (ingestion, research, business, etc.)
    ↓
Emit Event
    ↓
core/validation (validate event)
    ↓
core/event_store (append to ledger)
```

### Read Path (Projection)
```
Query Request
    ↓
interfaces/api (REST endpoint)
    ↓
projections/* (rebuild from events OR cache)
    ↓
Return result
```

---

## KEY INVARIANTS

1. **Events are immutable** — once written, never modified
2. **Projections are disposable** — can be rebuilt from events
3. **Control modules only produce events** — no direct state manipulation
4. **Validation is mandatory** — invalid events never reach event_store
5. **No cross-module writes** — only core/event_store writes events

---

## FUTURE EVOLUTION (Not Yet Implemented)

### Phase 2 Enhancements
- **core/identity:** Full RBAC (role-based access control)
- **core/validation:** Schema migration engine
- **interfaces/api:** SDKs (Python, TypeScript)
- **projections/temporal:** Point-in-time state reconstruction

### Phase 3 Enhancements
- **projections/semantic:** Vector search, embeddings
- **control/policy:** Declarative policy engine
- **projections/knowledge:** Pattern extraction

**These are deferred until real usage data informs design.**

---

## ANTI-PATTERNS (Avoid These)

❌ **Track-based organization** (TRACK-D, TRACK-E folders)  
❌ **Execution plan as structure** (phase-1/, week-1/ folders)  
❌ **Premature enterprise abstractions** (full RBAC, policy DSL before needed)  
❌ **Mixed responsibilities** (control module writing projections directly)  
❌ **Bypassing validation** (writing events without schema check)

---

## REFERENCES

- `docs/decisions/` — Architecture Decision Records (ADRs)
- `docs/guides/implementation-plan.md` — Project execution plan
- `docs/canonical/event_taxonomy_v1.json` — Event schema registry

---

**This is a stable architecture, not a project plan.**
