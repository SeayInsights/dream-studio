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

| Argument | Sub-mode | When to use |
|---|---|---|
| `frontend` | Frontend build | UI components, pages, fetch calls |
| `backend` | Backend build | API routes, DB, auth, workers |
| `integrate` | Integration verify | Connect frontend ↔ backend, verify contract |
| `secure` | Security sweep | OWASP frontend + backend checks |
| `spec` | Spec first | No prior contract — write spec + api-contract |
| (none) | Auto-detect | Infer from project state |

---

## Pipeline

```
spec ──→ api-contract ──┬── frontend ──┐
                        │              ├──→ integrate ──→ secure ──→ ship
                        └── backend ───┘
```

Sequential path: `spec → frontend → backend → integrate → secure`
Parallel path: `spec → (frontend || backend) → integrate → secure`

Use parallel when both sides are being built fresh in the same session.
Use sequential when one side already exists or is handed off.

---

## Auto-Detection Rules

When invoked without an argument:

1. Check for `.planning/api-contract.json`
   - Missing → run `spec` first
   - Present but no frontend source → run `frontend`
   - Present but no backend source → run `backend`
   - Both present → run `integrate`
2. Check for open integration failures (mismatched endpoints) → run `integrate`
3. Otherwise prompt user to specify a sub-mode

---

## Sub-Mode: spec

**Purpose:** Define feature requirements and write `.planning/api-contract.json` before any code is written.

DO write the contract before touching any code.
DON'T guess at endpoint shapes during build — if the contract is missing, stop and create it.

Output: `.planning/api-contract.json` with this schema:
```json
{
  "version": "1",
  "endpoints": [
    {
      "method": "POST",
      "path": "/api/resource",
      "request": { "field": "type" },
      "response": { "field": "type" },
      "auth": "bearer | none | session",
      "errors": ["400 validation", "401 unauthorized"]
    }
  ]
}
```

---

## Sub-Mode: frontend

**Purpose:** Build UI components, pages, and fetch calls aligned to `.planning/api-contract.json`.

Delegates to `domains:website` pipeline — DO NOT duplicate that logic here.
Read `.planning/api-contract.json` to know what endpoints to call.

DO use the exact path and method from the contract in every fetch call.
DON'T hardcode base URLs — read from env vars or config.
DON'T skip error state UI — every fetch needs loading, success, and error states.
DO match request body field names exactly to the contract — case-sensitive.

Stack routing:
- Astro / static → `domains:website` page mode
- React SPA → `domains:saas-build` (React 19 + React Router 7)
- Vanilla HTML → `domains:website` page mode

---

## Sub-Mode: backend

**Purpose:** Implement API routes, database models, and auth that fulfill `.planning/api-contract.json`.

Stack auto-detection (check in order):

| File present | Stack detected | Delegate to |
|---|---|---|
| `wrangler.toml` | Cloudflare Workers | `domains:saas-build` |
| `package.json` with `express` / `fastify` / `hono` | Node.js | inline Node patterns |
| `requirements.txt` or `pyproject.toml` | Python | inline Python patterns |
| `go.mod` | Go | inline Go patterns |
| None found | Unknown | ask user before proceeding |

DO validate every request body at the API boundary — trust nothing from the client.
DO return error shapes matching the contract's `errors` array.
DON'T implement endpoints not listed in the contract without updating the contract first.
DON'T store secrets in code — use env vars or secret managers.

Cloudflare Workers preset:
- Use `waitUntil()` for fire-and-forget logging and analytics
- CORS: handle in worker, not at DNS level
- Memory limit: 128MB; CPU: 50ms (bundled) / 30s (unbundled)

---

## Sub-Mode: integrate

**Purpose:** Verify frontend fetch calls match backend endpoint signatures. Fix mismatches.

Integration checklist — verify all of these:

| Check | Pass condition |
|---|---|
| Path match | Frontend `fetch('/api/...')` path equals backend route path |
| Method match | HTTP method matches in both |
| Request body fields | Frontend sends exactly the fields the backend expects |
| Response field consumption | Frontend reads only fields the backend returns |
| Auth header | Frontend sends the auth type the backend requires |
| Error handling | Frontend handles all error codes listed in contract |

DO run a grep for each endpoint path across both frontend and backend source before declaring done.
DON'T declare integration complete without checking every endpoint in the contract.
DON'T change the contract during integration — update it intentionally and re-run spec.

On mismatch: fix the implementation (never silently diverge from the contract).

---

## Sub-Mode: secure

**Purpose:** OWASP-aligned security sweep across frontend and backend.

### Frontend checks (OWASP)

| Risk | Check |
|---|---|
| XSS | No `innerHTML` / `dangerouslySetInnerHTML` with user data; CSP header present |
| CSRF | State-changing requests include CSRF token or use SameSite=Strict cookies |
| Sensitive data exposure | No tokens, secrets, or PII logged to console or stored in localStorage |
| Open redirect | No unvalidated `redirect` params used in navigation |

### Backend checks (OWASP)

| Risk | Check |
|---|---|
| Injection (SQLi) | Parameterized queries only — no string-concatenated SQL |
| Auth bypass | All protected routes check auth before processing request body |
| CORS misconfiguration | `Access-Control-Allow-Origin` is not `*` in production |
| Broken auth | Tokens are short-lived; refresh tokens are rotated on use |
| Security logging | Failed auth attempts are logged with IP (no PII in logs) |

DO file findings as a list with severity (high / medium / low) and remediation step.
DON'T block ship for low-severity findings — list them and continue.
DO block ship for any high-severity finding — fix it before proceeding.

---

## Shared State: API Contract

`.planning/api-contract.json` is the single source of truth for the frontend-backend interface.

DO commit this file to `.planning/` (which is gitignored — local only).
DON'T let frontend and backend diverge from it silently.
DON'T delete or overwrite the contract without re-running `spec` first.

The contract flows through the pipeline:
- `spec` writes it
- `frontend` reads it (fetch call shapes)
- `backend` reads it (route/response shapes)
- `integrate` diffs it against actual implementation
- `secure` references it for auth type and error handling checks

---

## Anti-Patterns

DON'T start coding before the api-contract exists — mismatched assumptions are the #1 integration failure.
DON'T run `frontend` and `backend` in parallel without a locked contract — they will diverge.
DON'T skip `integrate` and go straight to `secure` — security findings on unintegrated code are noise.
DON'T duplicate `domains:website` or `domains:saas-build` logic — delegate to them.
DON'T hardcode stack assumptions — auto-detect from project files every invocation.
DON'T declare the pipeline complete without running `secure` — it is not optional.
