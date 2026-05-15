# Dream Studio Product Requirements

Status: current public product authority
Last updated: 2026-05-15

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
- Maintain a Contract Atlas lifecycle manifest that regenerates private/internal atlas views, sanitized public exports, maturity status, docs/PRD/README impact detection, dashboard/API freshness, and public-export leakage checks from authority rather than hand-maintained files.
- Use GitHub Actions as a lightweight remote confidence layer: PR smoke by default, manual full CI for remote parity evidence, manual or tag-triggered release validation for release evidence, and local Dream Studio release gates as the heavy validation authority.
- Validate repo publication readiness with source-owned checks for tracked files, ignored/local boundaries, Git history path privacy, Apache-2.0 references, README/PRD alignment, and sanitized Contract Atlas exports.
- Formalize expert workflow contracts for intentional implementation, code
  quality, debugging, performance, frontend design, SEO/content,
  documentation, data modeling, API integration, demo/case-study creation, and
  private-by-default career/portfolio operations without duplicating existing
  skills.
- Support installed modular productization so a user can run `ds` from outside
  the repo, select profiles, inspect adapter/router health, use context-packet
  fallback, run analytics-only/security-only/full modes, and perform
  backup/restore/update/uninstall checks without understanding internals.
- Keep external projects paused by default with explicit target selection for
  read-only intake, scoped approval for mutation, validation and commit policy
  before commit, and separate approval before push or deploy.
- Keep Docker optional and non-authoritative through profile contracts for
  scanner, sandbox, worker, ingestion, and dashboard/API use without making
  containers required for local-first operation.
- Run long-run multisession validation before closeout decisions so route-first
  behavior, docs drift, security/readiness gates, adapter honesty, dashboard
  derived views, profile independence, and live SQLite hash guards do not
  regress.
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
5. SQLite records operational state, route decisions, telemetry, learning events, adapters, evidence summaries, release gates, PRD versions, project intake, change orders, milestone/Work Order authority, route reconciliation, and shared-intelligence records where safe.
6. Files remain public source, docs, examples, templates, rendered reports, or local evidence exports depending on their classification.
7. Dashboards and APIs are derived views, never routing authority.

## Core Capabilities

### Route-First Milestones

Dream Studio chooses the next valid milestone from product authority and current evidence. It should continue internally for low-risk approved steps and stop only for real approval, blocker, validation, recovery, or release boundaries.

### Work Orders

Work Orders define scope, allowed files, forbidden actions, validation, rollback, evidence requirements, and route behavior. Large goals are decomposed into sequenced Work Orders instead of prompt-by-prompt babysitting.

### PRD Lifecycle

Project intake creates or formalizes PRD authority before implementation. New
projects use adaptive question modes, explicit assumptions, known unknowns,
initial milestones, Work Order authority, and readiness/security
classification. In-flight projects can be formalized from current evidence
without relying on prior chat memory. Material product changes create Project
Change Orders instead of silently overwriting the PRD, milestones, Work Orders,
security/readiness scope, architecture assumptions, or release criteria. At
milestone, release, or project closeout, route reconciliation records planned
vs actual progress and accepted or unresolved deviations.

### SQLite Authority

SQLite stores structured authority for telemetry, PRD versions, Work Orders, route decisions, artifacts, release gates, adapter outputs, learning records, shared context packets, and dashboard read models. Schema changes must be additive and migration-backed unless a separate approval explicitly allows otherwise.

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

### Installed Modular Platform

Dream Studio installs as a local platform with selected module profiles and a
global `ds` command surface. Core, analytics-only, security-only,
telemetry-only, dashboard-only, adapter-router-only, shared-intelligence-only,
and full profiles must expose honest enabled/disabled behavior and empty states.
Normal use should not require manually opening the source repo.

### External Project Pipeline

External targets are reusable but paused by default. The pipeline can plan
read-only intake, PRD/status detection, stack/dependency discovery,
security/readiness classification, validation profile selection, Work Order
generation, commit policy, and dashboard visibility without inspecting or
mutating target repos. Any real external access requires current target
selection and scope.

### Optional Docker Boundary

Docker can provide optional scanner, sandbox, worker, ingestion, or dashboard/API
runtime isolation. It must not become canonical authority, create a competing
SQLite database, mount host state by default, or block core local-first
operation when unavailable.

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

### Expert Workflow System

Dream Studio maps existing skills and workflows into reusable expert workflow
contracts. The system strengthens existing owners instead of creating duplicate
skills, records an overlap decision matrix, requires evidence-backed scoring,
and routes structured outputs into Work Orders, dashboard attention, Project
Details, Contract Atlas maturity, project health/readiness, release readiness,
and private portfolio/career surfaces where relevant.

Career and application automation remain private by default. Dream Studio must
not invent career claims, metrics, titles, compensation, employer details,
deployment outcomes, business impact, or adoption claims. Application
automation must not create accounts, bypass CAPTCHAs, misrepresent the
operator, or submit applications without explicit approval or an approved
per-application policy.

### Career Ops, Capability Center, And Scoped Agents

Career Ops is an optional private module. If enabled, it stores career profile,
resume, application, portfolio, case-study, interview, browser-automation,
evidence, and scorecard records in local SQLite authority. It must stay out of
public exports, team rollups, demo packets, and sanitized portfolio outputs
unless the operator explicitly approves a redacted artifact.

Capability Center makes skills, workflows, scoped agents, controls,
evaluations, and hardening candidates visible and measurable through derived
dashboard/API read models. Agents are scoped workers, not authority, and must
receive only task-required context.

### GitHub Repo Intake

Before Dream Studio adopts ideas, code, dependencies, prompts, skills,
workflows, hooks, adapters, docs, or architecture patterns from a GitHub repo,
it must run an evidence-backed intake evaluation. Unclear license status routes
to legal review, unclear security/supply-chain status routes to security
review, and overlap with existing Dream Studio capabilities routes to manual
overlap review. The preferred outcome is pattern learning plus original
implementation unless dependency/fork/vendor/code-copy approval is explicit.

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
