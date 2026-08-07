# Backend API — HTTP/REST Endpoint Quality Audit

## Mode dispatch

0. **Progressive disclosure check:** Apply the portable skill contract before dispatching.

1. Parse the mode from the argument (first word).
2. If no mode given, default to `audit`.
3. Read `modes/<mode>/SKILL.md` completely before executing.
4. If `gotchas.yml` exists in this directory, read it before executing.
5. Follow the mode's instructions exactly.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, api audit:, check api:, backend audit: |

## What This Skill Does

`audit` — retrospective API quality scan. Reviews HTTP route handlers for production-readiness: input validation, error handling, authentication enforcement, rate limiting, CORS policy, status code correctness, and more. Static analysis where possible; LLM confirmation for judgment-dependent rules. Produces a classified report.

## Source Authority

Rules are defined in `rules.yml` in this directory.

## Supported Frameworks

**Python:** FastAPI, Flask, Django REST Framework  
**TypeScript/JavaScript:** Next.js API routes, Express, Fastify, Hono  
**Go:** Gin, Echo, Chi, net/http  
**Rust:** Axum, Actix-web  

**Unsupported frameworks:** LLM-only fallback applies (no static detection). Rules still fire via semantic analysis.

## Skill Boundary

**Backend-API owns:** HTTP endpoint quality — validation, error handling, authentication patterns, rate limiting, CORS, idempotency, status codes, response shape.

**Security (ds-quality:security) owns:** Attack-surface risk analysis — injection risk (sec-003), credential exposure (sec-001), CSRF attack surface (sec-004), session identity risk (sec-015).

**Cross-references:**
- `api-001` (HTTP input validation) ↔ `sec-003` (injection risk): api-001 fires on missing schema validators; sec-003 fires on injection risk from unvalidated input.
- `api-002` (error shape) ↔ `sec-013` (PII in runtime output): api-002 fires on leaked stack traces; sec-013 fires on PII in logs/errors.
- `api-003` (CSRF on state-changing routes) ↔ `sec-004` (CSRF protection): api-003 detects missing CSRF at HTTP layer; sec-004 owns attack-surface analysis.
- `api-004` (auth enforcement) ↔ `sec-015` (session/identity risk): api-004 detects unprotected routes; sec-015 owns auth bypass exploitability.
- `api-006` (authorization checks) ↔ `sec-015` (authorization): api-006 detects missing AuthZ; sec-015 owns privilege escalation risk.
