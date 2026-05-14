# Dream Studio Codex Adapter Projection

Dream Studio is a local-first AI orchestration and operational intelligence
platform. Codex is one adapter surface. It does not own Dream Studio authority.

This file is a Codex-facing projection generated from Dream Studio authority.
Canonical state lives in the repo source, the operator-local SQLite authority
database, and evidence records. Dashboard output is derived, private model
memory is not authority, and adapter-specific configuration must stay thin.

Projection source:
- `sqlite:adapter_authority_profiles`
- `sqlite:shared_context_packets`
- `repo:skills/`, `repo:workflows/`, `repo:hooks/`
- file-backed evidence under the operator-local Dream Studio meta store

## Routing

Use Dream Studio skills before built-in behavior when the user asks to think,
plan, build, review, verify, ship, hand off, recap, explain, debug, harden, or
secure Dream Studio work.

| User intent | Dream Studio skill | Mode |
| --- | --- | --- |
| think, spec, research, "how should we" | `ds-core` | `think` |
| plan, break down, task list | `ds-core` | `plan` |
| build, implement, execute | `ds-core` | `build` |
| review, check code, PR review | `ds-core` | `review` |
| verify, test, prove it works | `ds-core` | `verify` |
| ship, release, release gate | `ds-core` | `ship` |
| handoff, pass context | `ds-core` | `handoff` |
| recap, summarize session | `ds-core` | `recap` |
| explain, walk through | `ds-core` | `explain` |
| debug, diagnose, fix broken behavior | `ds-quality` | `debug` |
| harden, setup, best practices | `ds-quality` | `harden` |
| security review, vulnerabilities | `ds-quality` | `secure` |
| capture lesson, learn from build | `ds-quality` | `learn` |

## Authority Rules

- Treat SQLite authority, repo source, and evidence refs as the source of truth.
- Treat adapter files as projections that can be regenerated or validated.
- Do not treat Codex memory, Claude memory, dashboard cards, or private model
  state as canonical Dream Studio authority.
- Do not push, deploy, mutate external projects, or execute cleanup unless the
  current Dream Studio Work Order and operator approval explicitly authorize it.
- Keep Dream Studio local-first: the operator-local DB and state remain local
  unless a future explicit export/release boundary approves otherwise.

## Code History And Impact Guardrail

Before source edits, inspect relevant git history, module purpose, architecture
boundaries, tests, validation expectations, and related routes, read models,
SQLite boundaries, telemetry, dashboard surfaces, hooks, skills, workflows, and
adapter projections. Classify touched files as product source, generated
artifact, test fixture, local state, external target, or private evidence.

After code or cleanup changes, validate imports, public API/route contracts,
read-model and dashboard response shapes, temp/injected DB behavior, live-state
boundaries, external-project boundaries, and release-gate impact. Mechanical
formatting belongs in its own commit and must not include semantic refactors.
