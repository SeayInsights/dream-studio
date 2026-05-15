# Dream Studio Product Requirements

Status: current public product authority
Last updated: 2026-05-14

## Product Identity

Dream Studio is a local-first AI orchestration and operational intelligence platform for high-trust, goal-oriented agentic work.

It is not primarily an adapter, prompt library, handoff generator, dashboard, task tracker, or single-project automation script. Claude Code is one adapter surface. Dream Studio's source of truth is its own local authority model: PRD, stage gates, Work Orders, SQLite state, evidence refs, validation results, route decisions, and operator approvals.

## Primary User

The primary user is a local operator who directs software, research, security, documentation, release, and operational work across AI tools without giving any single AI model private memory or prompt history authority.

## Problem

Agentic work becomes fragile when progress depends on prompt chaining, hidden chat memory, or stale handoff documents. Operators need a local control plane that can:

- understand the active product goal;
- select the next valid milestone;
- execute bounded Work Orders;
- validate changes;
- preserve evidence;
- surface approvals and blockers;
- resume through another AI adapter without losing authority;
- stop before material risk, live data mutation, cleanup, push, tag, merge, deploy, or release boundaries.

## Goals

- Route work through PRD-defined milestones and Work Orders.
- Keep SQLite and structured state as operational authority where safe.
- Treat files, reports, handoffs, and dashboards as evidence or rendered views unless explicitly promoted.
- Emit telemetry for decisions, hooks, tools, skills, tokens, validations, security findings, workflows, research, outcomes, and operator decisions.
- Provide dashboard attention queues for approvals, warnings, blockers, prompt-required items, and release gates.
- Track secure production readiness separately from project health so projects can move toward real users with evidence-backed security, API, database, caching, accessibility, observability, performance, dependency, privacy, code-quality, rollback, and release controls.
- Generate shared context packets so Claude Code, Codex, Cursor, Copilot, ChatGPT, MCP tools, shell tools, local models, and future adapters can resume from Dream Studio authority.
- Normalize adapter results into common records: decisions, changes, validation, evidence, risks, artifacts, and outcomes.
- Learn from failed assumptions, repeated fixes, validation failures, operator corrections, successful hardening, and component performance.
- Maintain a Contract Atlas that maps layers, modules, interfaces, runtime profiles, adapter projections, dependency evidence, maturity state, and source-change impact to the docs/contracts that must stay fresh.
- Keep private operator state, raw telemetry, local backups, Work Orders, handoffs, cutover records, and audit evidence out of the public repo by default.

## Non-Goals

- No fully autonomous black-box worker with no human approval gates.
- No cloud-first or SaaS-first authority model.
- No dashboard-as-primary-truth.
- No model-provider lock-in.
- No prompt-chain engine.
- No secret or sensitive-data harvesting.
- No unapproved database migration, cleanup, deletion, archive execution, push, tag, merge, deploy, or external project mutation.
- No publication of private operational history by default.

## Authority Model

1. PRD and product policies define goals, non-goals, constraints, success criteria, and human approval boundaries.
2. Stage gates define the valid sequence of maturity milestones.
3. Milestones represent meaningful product progress.
4. Work Orders execute bounded slices inside a milestone.
5. SQLite records operational state, route decisions, telemetry, learning events, adapters, evidence summaries, release gates, and shared-intelligence records where safe.
6. Files remain public source, docs, examples, templates, rendered reports, or local evidence exports depending on their classification.
7. Dashboards and APIs are derived views, never routing authority.

## Core Capabilities

### Route-First Milestones

Dream Studio chooses the next valid milestone from product authority and current evidence. It should continue internally for low-risk approved steps and stop only for real approval, blocker, validation, recovery, or release boundaries.

### Work Orders

Work Orders define scope, allowed files, forbidden actions, validation, rollback, evidence requirements, and route behavior. Large goals are decomposed into sequenced Work Orders instead of prompt-by-prompt babysitting.

### SQLite Authority

SQLite stores structured authority for telemetry, Work Orders, route decisions, artifacts, release gates, adapter outputs, learning records, shared context packets, and dashboard read models. Schema changes must be additive and migration-backed unless a separate approval explicitly allows otherwise.

### Telemetry Spine

Dream Studio records events and facts for route decisions, hooks, tools, skills, token usage, validation results, security findings, workflows, research, decisions, attention items, and outcomes. Read models aggregate this into dashboard-consumable derived views.

### Dashboard Attention

The dashboard surfaces release blockers, approvals, warnings, prompt-required items, validation status, module availability, component usage, project health, project readiness, and drilldown entry points. It must show empty states safely and must not claim primary authority.

### Secure Production Readiness

Dream Studio classifies readiness impact for goals, milestones, Work Orders,
code changes, release gates, project intake, external onboarding, and live
cutovers. It selects targeted checks for normal development and full applicable
security/readiness reviews at high-risk lifecycle gates. Readiness records are
SQLite-backed where safe, but legal/compliance status is only classified unless
evidence and operator/legal review support a stronger claim.

### Shared Intelligence

Adapters are projections over Dream Studio authority. Dream Studio generates context packets and adapter configs, detects stale projections, normalizes results, compares outcomes, and routes work based on capability, risk, cost, validation need, and prior success.

### Contract Atlas And Drift Gate

Dream Studio maintains a private-by-default Contract Atlas so operators and
adapters can understand the system's layers, module boundaries, interface
contracts, runtime profiles, adapter projection state, maturity scorecard, and
confirmed dependency graph. The release gate uses the atlas registry to block
meaningful source changes when the impacted contracts or public docs have not
been refreshed.

The maturity ledger must distinguish hardened, runtime-validated, tested-only,
designed-but-unproven, stale, blocked, not-started, and manual-review areas so
public claims and operational use do not exceed evidence.

### Learning And Hardening

Dream Studio captures learning events for skill gaps, workarounds, failed assumptions, validation failures, route mistakes, and successful hardening. Lessons can become rules, skill updates, workflow updates, adapter policies, dashboard attention items, or operator approval items through a promotion policy.

### Publication Boundary

The public repo should contain product source, public docs, examples, templates, tests, sanitized demos, and sanitized release notes. Private runtime state remains local: `.dream-studio`, SQLite DB files, backups, raw telemetry, local evidence, Work Orders, handoffs, cutover records, cleanup manifests, and operator decision logs are excluded by default.

## Human Approval Boundaries

Dream Studio must stop for explicit operator approval before:

- mutating live installed runtime state;
- mutating live SQLite authority;
- running database migrations against live state;
- deleting, archiving, compacting, deduplicating, or cleaning local state;
- pushing, tagging, merging, deploying, or rewriting Git history;
- accessing secrets or sensitive values;
- changing source scope beyond approved files;
- working on external projects outside the active registry scope.

## Success Criteria

Dream Studio is operating correctly when an operator can provide a goal and Dream Studio can:

- select and execute the next stage-gate-valid milestone;
- generate and sequence Work Orders;
- perform bounded source changes;
- validate with temp or injected runtime state where writes are needed;
- record structured evidence and telemetry;
- update dashboard-derived views;
- explain route decisions;
- stop at human approval boundaries;
- resume through another adapter using Dream Studio state rather than prior chat memory;
- keep private operational history out of the public repository.
