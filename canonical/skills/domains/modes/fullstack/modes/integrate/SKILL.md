---
pack: domains
mode: fullstack/integrate
mode_type: build
model_preference: sonnet
---

# Integrate Mode

Wires frontend to backend after both are built. The API contract (`.planning/api-contract.json`) is the single source of truth. All mismatches are reported before any fix is applied.

## Verification Checklist

| Check | Source | Target | Pass Criteria |
|---|---|---|---|
| Endpoint coverage | API contract | Frontend fetch calls | Every contract endpoint has a matching fetch |
| Method match | API contract | Frontend fetch calls | GET/POST/PUT/DELETE matches exactly |
| Payload shape | API contract request schema | Frontend request body | Fields match type and required status |
| Response handling | API contract response schema | Frontend response parsing | Frontend destructures all expected fields |
| Auth headers | API contract auth requirements | Frontend auth implementation | Auth tokens sent on protected routes |
| CORS config | Frontend origin | Backend CORS settings | Frontend origin is in allowed origins |

## Integration Steps

1. Read `.planning/api-contract.json` — establish ground truth for all endpoints, methods, schemas, and auth requirements
2. Scan frontend HTML/JS for all `fetch`, `axios`, and API call patterns — collect URL, method, request body, and response destructuring per call
3. Scan backend for all route definitions — collect path, method, handler signature, and middleware
4. Run verification checklist — compare each check against both sides
5. Report all mismatches with `file:line` references before suggesting any fix
6. Generate targeted fix suggestions for each mismatch
7. Wire environment config — create or update `.env` template with `API_BASE_URL` and auth endpoint vars

## Drift Detection

Flag these three gap types explicitly in output:

- **Backend gap** — contract has endpoint, backend does not implement it
- **Undocumented endpoint** — frontend calls endpoint not in contract
- **Contract gap** — backend implements endpoint not in contract

Each flag includes the specific endpoint, file, and line number.

## DO / DON'T

DO read the API contract as the single source of truth before touching any code.
DON'T assume frontend and backend are in sync — verify every endpoint.

DO report all mismatches first, in a structured list, before suggesting fixes.
DON'T auto-apply fixes without showing the user exactly what changes.

DO check CORS configuration explicitly against the frontend origin.
DON'T skip auth header verification on any route marked protected in the contract.

DO generate a `.env.template` file with `API_BASE_URL` and all auth endpoint variables.
DON'T hardcode `localhost` URLs — flag any hardcoded host as a mismatch requiring an env var.

DO include `file:line` references for every mismatch and every fix suggestion.
DON'T merge frontend and backend changes in a single step — verify after each wire.

---

## Partial Integration Failure Modes

When integration verification finds mismatches, the nature of the failure determines the response:

**Frontend compiles but backend contract changed:**
- Re-read the API contract and diff it against the version the frontend was built against
- Generate a diff report showing: added endpoints, removed endpoints, changed schemas
- Do not auto-apply fixes — show the delta list first, then ask which side to reconcile
- Prefer updating the frontend to match the current contract over mutating a live backend route

**Auth token format differs between services:**
- Identify the token format on each side: Bearer JWT, session cookie, API key, or service token
- If both sides use JWT: compare claims (`sub`, `exp`, `aud`, `iss`) against the auth section of the API contract
- Flag any `aud` mismatch as HIGH severity — wrong audience on a JWT is a security boundary failure
- Recommended fix: add an auth adapter or middleware layer; never strip claims to force a match

**CORS blocks the integration test:**
- CORS failures in integration are always configuration, not code — do not change request code to work around them
- Verify: the frontend origin matches exactly what the backend CORS allowlist expects (scheme + host + port)
- Check for wildcard origins in production config — flag as a security finding if present
- If the test environment differs from production origins, document both in `.env.template`

---

## Schema Migration Guidance During Integration

Integration may reveal that the API contract has evolved since the last backend build. Schema changes require explicit decisions before wiring can proceed.

**When to run migrations vs defer:**
- If the schema change is additive (new columns, new tables, non-breaking renames): run the migration first, then wire
- If the schema change is destructive (removed columns, type changes, breaking renames): do NOT run during integration — flag it and open a dedicated task for safe migration with backfill strategy
- Never run destructive migrations as part of a wire-and-integrate step

**Backwards-incompatible schema changes during active integration:**
- Check whether the frontend consumes the affected fields
- If yes: frontend and backend must coordinate the change atomically — deploy backend with a compatibility shim first, then update frontend, then remove the shim
- If no: backend schema change can proceed independently without frontend impact
- Document the decision and rationale in `.planning/api-contract.json` as a migration note

**Rollback protocol if integration test fails after migration:**
- Write a rollback migration before applying the forward migration — commit both in the same PR, rollback clearly labeled `rollback_<version>`
- If integration test fails: run the rollback migration immediately before investigating root cause
- Never leave a half-migrated database in the test environment for more than one work session
- A failed integration after migration is always investigated against the rollback, not patched forward

---

## Auth Token Propagation Across the Service Boundary

**Passing tokens from frontend to backend securely:**
- Use `Authorization: Bearer <token>` header for REST APIs; never pass tokens as query parameters
- For cookie-based auth: set `HttpOnly`, `Secure`, and `SameSite=Strict` on all session cookies
- Never embed auth tokens in the URL — they are logged by every proxy and load balancer in the path
- The frontend must source tokens from a single canonical location (memory, HttpOnly cookie, or sessionStorage) — document which in `.env.template`

**Validating tokens at the API boundary:**
- Every protected route must validate signature, expiry (`exp`), audience (`aud`), and issuer (`iss`)
- Partial validation (signature only, or no expiry check) is a CRITICAL security finding — flag it and BLOCKED shipment
- Use the auth section of the API contract to establish which routes are protected and what claims are required
- In integration tests, verify that unauthenticated requests to protected routes return 401, not 200 or 500

**Session token vs service token distinction:**
- Session tokens: scoped to a user, short-lived (≤24h), created on login, invalidated on logout
- Service tokens: scoped to a service identity, longer-lived, used for backend-to-backend calls only
- Service tokens MUST NOT appear in frontend code — flag credential leakage as CRITICAL if found in JS bundles
- Verify at integration time that the frontend holds only session tokens, never service tokens
