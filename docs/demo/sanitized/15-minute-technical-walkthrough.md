# Dream Studio 15-Minute Technical Walkthrough

Mode: public sanitized. Use synthetic screenshots and repo-owned docs only.

## 0:00-1:30 - Architecture Frame

- Dream Studio source lives in the repo.
- Installed runtime state lives in user-local state.
- SQLite is the current durable operational authority.
- Dashboard/API are derived views.
- Adapter projections and context packets are generated surfaces, not competing authority.

Speaker note:

> The first technical principle is authority separation: product source, local runtime state, adapter projections, and dashboard views each have different authority levels.

## 1:30-4:00 - Observe Mode

Show the Observe Mode screenshot.

Explain:

- All Projects and Project Details summarize current project authority.
- Contract Atlas tracks module, profile, API, dashboard, docs drift, sanitized export, and maturity contracts.
- Security/readiness gates classify applicable controls and missing evidence.
- Telemetry and validation records feed dashboard attention without becoming raw public logs.

Evidence to cite in the walkthrough:

- `ds status`
- `ds validate`
- `ds contract-atlas`
- Contract Atlas lifecycle gate
- release gate with live SQLite hash guard

## 4:00-7:00 - Assist Mode

Show the Assist Mode screenshot.

Explain:

- Supported adapters include CLI/app surfaces, MCP-capable clients, shell tools, and context-packet-only fallback.
- Context packets provide scoped authority for the task.
- Adapter result records, task attribution, skill/workflow invocation records, validation results, and evidence refs normalize back into SQLite authority.
- Token and cost reporting stays honest: unknown cost remains unknown, plan-based usage stays plan-based, and tokens are not converted into fake dollars.

Safe demo action:

1. Generate or preview a context packet.
2. Import a synthetic adapter result into a rehearsal or temp state only.
3. Show attribution summary with source refs.

## 7:00-10:30 - Operate Mode

Show the Operate Mode screenshot.

Explain:

- Policy decisions classify actor, action, target, scope, risk, approval requirements, evidence requirements, rollback requirements, state, reason, and dashboard attention impact.
- Work Orders scope the next safe action.
- Validation runs through isolated paths.
- Destructive actions, external mutation, push/tag/deploy, Docker execution, secret inspection, cleanup, and live SQLite mutation remain approval-gated.

Safe demo action:

1. Preview a denied or deferred policy decision.
2. Show the Work Order and route-decision pattern.
3. Show validation evidence and safe next action.

## 10:30-12:30 - Privacy And Publication Boundary

Explain:

- Career Ops is opt-in and private by default.
- GitHub repo intake evaluates license, security, maintenance, overlap, and adoption risk before use.
- Public exports use `public_sanitized`.
- Demo packets exclude raw Work Orders, handoffs, raw telemetry, local evidence, local paths, operator decisions, career/application data, compensation strategy, private external-project details, secrets, and unsanitized security findings.

## 12:30-14:00 - Failure And Fallback Story

Explain:

- If live dashboard is unavailable, use the screenshot packet and CLI outputs.
- If adapter status is unavailable, use context-packet-only mode.
- If evidence is missing, say it is missing.
- If a policy decision is denied or deferred, that is a successful guardrail demonstration.

## 14:00-15:00 - Close

Close with:

> Dream Studio does not try to make every AI tool authoritative. It gives AI work an operating system: authority, evidence, policy, privacy, validation, attribution, and safe continuation.

Verdict:

`public_demo_ready` for sanitized scripted demo. Live private demo remains private unless separately reviewed.
