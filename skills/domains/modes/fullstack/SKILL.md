---
ds:
  pack: domains
  mode: fullstack
  mode_type: build
  inputs: [feature_spec, api_contract, stack_context]
  outputs: [frontend_artifact, backend_artifact, api_contract, integration_report, security_report]
  capabilities_required: [Read, Write, Edit, Grep, Bash, LSP]
  model_preference: sonnet
  estimated_duration: 1-8hrs
---

# Fullstack — Orchestrator

## Mode Routing Table

| Argument | Sub-mode | SKILL.md |
|---|---|---|
| `frontend` | Frontend build | `modes/frontend/SKILL.md` |
| `backend` | Backend build | `modes/backend/SKILL.md` |
| `integrate` | Integration verify | `modes/integrate/SKILL.md` |
| `secure` | Security sweep | `modes/secure/SKILL.md` |
| `spec` | Spec first | Write API contract before any code |
| (none) | Auto-detect | Infer from project state (see below) |

## Before You Start

Read `gotchas.yml` in this directory before every invocation.

## Pipeline

```
spec ──→ api-contract ──┬── frontend ──┐
                        │              ├──→ integrate ──→ secure ──→ ship
                        └── backend ───┘
```

- **Sequential**: spec → frontend → backend → integrate → secure
- **Parallel**: spec → (frontend || backend) → integrate → secure

Use parallel when both sides are built fresh. Use sequential when one side exists.

## Mode Dispatch

1. Parse sub-mode from argument (first word).
2. If no argument, run auto-detection (below).
3. Read `modes/<sub-mode>/SKILL.md` completely.
4. If `gotchas.yml` exists in that mode dir, read it.
5. Follow the mode's instructions exactly.

## Auto-Detection

When invoked without an argument:

1. Check for `.planning/api-contract.json`
   - Missing → run `spec` first
   - Present but no frontend source → `frontend`
   - Present but no backend source → `backend`
   - Both present → `integrate`
2. Check for open integration failures → `integrate`
3. Otherwise prompt user to specify

## Spec Mode (inline — no separate file)

Write `.planning/api-contract.json` before any code. See `templates/api-contract.md` for format.

DO write the contract before touching code.
DON'T guess at endpoint shapes during build — stop and create the contract.

## Shared State: API Contract

`.planning/api-contract.json` is the single source of truth for the frontend-backend interface.

| Pipeline stage | Contract usage |
|---|---|
| spec | Writes it |
| frontend | Reads it (fetch call shapes) |
| backend | Reads it (route/response shapes) |
| integrate | Diffs it against actual implementation |
| secure | References it for auth type checks |

DON'T let frontend and backend diverge from it silently.
DON'T delete or overwrite without re-running spec first.

## Anti-Patterns

DON'T start coding before the api-contract exists.
DON'T run frontend and backend in parallel without a locked contract.
DON'T skip integrate and go straight to secure.
DON'T duplicate domains:website or domains:saas-build logic — delegate.
DON'T hardcode stack assumptions — auto-detect every invocation.
DON'T declare the pipeline complete without running secure.
