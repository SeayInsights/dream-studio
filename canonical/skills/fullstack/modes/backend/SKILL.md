---
dream_studio:
  skill_id: ds-fullstack
  pack: fullstack
  mode: backend
  mode_type: build
  inputs: [api_contract, stack_context, feature_spec]
  outputs: [api_routes, db_schema, auth_config, env_template, api_contract]
  capabilities_required: [Read, Write, Edit, Grep, Bash]
  model_preference: sonnet
  estimated_duration: 1-4hrs
  write_posture: independent
  lifecycle: published
---

# Backend — Stack-Agnostic API Builder + Quality Audit

## Mode dispatch

1. Parse the mode from the argument (first word). Default to `build` when the input looks
   like a build/scaffold request and no mode is named explicitly.
2. If no mode is given and the input doesn't obviously match one, list the two below and ask.
3. Read `<mode>/SKILL.md` completely before executing.
4. If `gotchas.yml` exists in this directory, read it before executing (shared across both
   modes).
5. Follow the mode's instructions exactly.

| Mode | File | Keywords |
|------|------|---------|
| build | build/SKILL.md | (default — invoked as `fullstack backend`) |
| audit | audit/SKILL.md | audit:, api audit:, check api:, backend audit: |

## Which mode

Two different questions, not two names for the same thing:

- **`build`** — "Generate the backend for this API contract." Stack-agnostic scaffolder:
  routes, DB schema, auth config, env template, for whatever framework the project detects
  (Node/Express/Fastify/Hono, Python/FastAPI/Flask/Django, AWS Serverless, or Cloudflare
  Workers via `apps:saas-build`).
- **`audit`** — "Does this codebase's existing API meet the 12-rule HTTP endpoint quality
  baseline?" Retrospective scan: input validation, error handling, auth/authz enforcement,
  rate limiting, CORS, idempotency, pagination, versioning, status codes, response shape.
  Static detection where possible, LLM confirmation for judgment-dependent rules.
  Classifies and reports only — never fixes.

## Source Authority

`audit` reads `rules.yml` in this directory (12 rules). `build` has no rule file — its
patterns live in `build/SKILL.md` and `../../references/stack-presets.md`.

## Supported Frameworks (audit)

**Python:** FastAPI, Flask, Django REST Framework
**TypeScript/JavaScript:** Next.js API routes, Express, Fastify, Hono
**Go:** Gin, Echo, Chi, net/http
**Rust:** Axum, Actix-web

**Unsupported frameworks:** LLM-only fallback applies (no static detection). Rules still
fire via semantic analysis.

## Skill Boundary (audit)

**Backend audit owns:** HTTP endpoint quality — validation, error handling, authentication
patterns, rate limiting, CORS, idempotency, status codes, response shape.

**Security (`ds-security:review`) owns:** Attack-surface risk analysis — injection risk
(sec-003), credential exposure (sec-001), CSRF attack surface (sec-004), session identity
risk (sec-015).

**Cross-references:**
- `api-001` (HTTP input validation) ↔ `sec-003` (injection risk): api-001 fires on missing
  schema validators; sec-003 fires on injection risk from unvalidated input.
- `api-002` (error shape) ↔ `sec-013` (PII in runtime output): api-002 fires on leaked stack
  traces; sec-013 fires on PII in logs/errors.
- `api-003` (CSRF on state-changing routes) ↔ `sec-004` (CSRF protection): api-003 detects
  missing CSRF at HTTP layer; sec-004 owns attack-surface analysis.
- `api-004` (auth enforcement) ↔ `sec-015` (session/identity risk): api-004 detects
  unprotected routes; sec-015 owns auth bypass exploitability.
- `api-006` (authorization checks) ↔ `sec-015` (authorization): api-006 detects missing
  AuthZ; sec-015 owns privilege escalation risk.

## Integration with Other Fullstack Modes

**Pipeline:** `spec → (frontend || backend) → integrate → secure`. `build` is the pipeline's
backend stage. `audit` is a standalone, on-demand check — not part of that pipeline; run it
against an existing backend at any time.

See `../../SKILL.md` for the orchestrator's full mode routing and auto-detection.
