---
pack: fullstack
mode: fullstack/secure
mode_type: review
model_preference: sonnet
---

# Fullstack Security Review

Reviews security across frontend and backend as a unified system — auth flows, data paths, and trust boundaries end-to-end.

---

## Security Check Matrix

| Category | Frontend Checks | Backend Checks |
|---|---|---|
| Injection | XSS (DOM, stored, reflected) | SQLi, NoSQLi, command injection |
| Auth | Token storage (no localStorage for JWTs), CSRF tokens | Auth middleware on protected routes, password hashing, session management |
| Transport | HTTPS enforcement, mixed content | TLS config, HSTS headers |
| Headers | CSP, X-Frame-Options, X-Content-Type | CORS policy, rate limiting headers |
| Data | Input sanitization, sensitive data in DOM | Input validation, parameterized queries, secrets in env vars |
| API | Auth tokens on requests, error message leakage | Auth on all endpoints, error sanitization, rate limiting |

---

## Review Steps

1. Read the API contract — identify which endpoints require authentication and what token format is expected.
2. Scan frontend for OWASP Top 10 web vulnerabilities — XSS, broken auth, sensitive data exposure, misconfigured headers.
3. Scan backend for OWASP Top 10 API vulnerabilities — broken object-level auth, excessive data exposure, lack of rate limiting.
4. Trace the full auth flow: login → token issuance → token storage → protected request → server-side validation.
5. Check CORS configuration — allowed origins must match actual frontend domains, not wildcards.
6. Check CSP headers — directives must restrict script/style/connect sources to required origins only.
7. Verify error responses — no stack traces, internal paths, or query strings in 4xx/5xx responses.
8. Compile findings table and verdict.

---

## DO / DON'T

DO check auth flow end-to-end, not just individual endpoints in isolation.
DON'T approve if JWTs are stored in `localStorage` — `httpOnly` cookies only.

DO verify CORS `Access-Control-Allow-Origin` specifies the frontend origin exactly, not `*`.
DON'T skip CSP header review — absent or overly permissive CSP is a finding, not a suggestion.

DO flag any endpoint missing auth middleware as critical if it handles user data.
DON'T mark an endpoint as secure based on frontend route guards alone — backend must enforce independently.

DO check that 4xx and 5xx responses return generic messages with no internal detail.
DON'T report code style issues, naming conventions, or non-security lint warnings as findings.

DO note when secrets appear in frontend bundles, `.env.local` committed to repo, or hardcoded in source.
DON'T treat HTTPS-only deployments as an excuse to skip CSP or CORS review.

---

## Output Format

### Findings Table

| Severity | Category | Location | Description | Fix |
|---|---|---|---|---|
| critical | Auth | `api/users.ts:42` | No auth middleware on `/api/users` | Add `requireAuth` middleware |
| high | Headers | `next.config.js` | CSP missing — no `Content-Security-Policy` header | Add restrictive CSP via headers config |
| medium | Transport | `app/login.tsx:18` | JWT written to `localStorage` | Migrate to `httpOnly` cookie |
| low | Data | `api/error.ts:9` | Stack trace returned on 500 | Return generic error message |

### Summary

X critical, Y high, Z medium, W low

### Verdict

**PASS** — 0 critical, 0 high findings.
**FAIL** — N critical and/or N high findings must be resolved before merge.

---

## Skill Boundary

**Fullstack `secure` owns:** cross-boundary checks specific to the frontend+backend pair this
pipeline just built — auth flow traced end-to-end against the `api-contract.json` docstore
artifact (login → token issuance → storage → protected request → server-side validation),
CORS between the actual frontend origin and the actual backend allowlist, and CSP headers for
the frontend that was just generated. It is a **mandatory pipeline stage gate**
(`spec → (frontend || backend) → integrate → secure → ship`) — `fullstack`'s own anti-patterns
say "DON'T declare the pipeline complete without running secure." It is not an on-demand
entry point the way the two skills below are; it only runs, and only makes sense, once both
sides of one contract exist.

**`ds-security:review` owns:** general-purpose code security review, invoked directly rather
than as a pipeline stage, over arbitrary code with no `api-contract.json` involved:
- `diff` — "is this PR's new code exploitable?" Freeform LLM judgment over a git diff only,
  high-confidence (≥8/10) findings, new lines only, no tool execution, opus.
- `audit` — "does the whole codebase meet the 22-rule security baseline?" Rule-based: static
  tools (gitleaks, bandit, semgrep, pip-audit) plus an LLM pass per rule, any repo, any time.
- `build` — "does this about-to-be-generated snippet violate a build-blocking rule?"
  Synchronous, static-pattern-only, blocks generation on critical/high findings.
- `panel` — a separate, general-purpose parallel-subagent review — one analyst per OWASP
  category or STRIDE threat — triggered on any PR touching auth, payments, user data, or API
  endpoints, codebase-agnostic and independent of any fullstack pipeline state. It produces its
  own SHIP/BLOCKED verdict from the diff and architecture description alone. (Formerly
  `ds-quality:pr-security-scan`, merged into `security:review` as this 4th sub-mode.)

**Why there's no overlap despite similar-sounding checks:** `security:review:audit` and
`security:review:panel` both cover CORS, CSP, and auth-enforcement categories in the
abstract — but neither reads `api-contract.json` or reasons about one specific frontend/backend
pair produced by one pipeline run. `secure` narrows the same categories (CORS, CSP, auth flow)
to that one contract's actual origin, actual token type, and actual protected-route list. A PR
touching auth mid-fullstack-pipeline can legitimately trigger both `secure` (because the
pipeline requires it before `ship`) and `panel` (because the diff matches its trigger) without
either being redundant: `secure` verifies the contract was honored; `panel` reviews the diff on
its own terms.

**Integration with Other Fullstack Modes:** `spec → (frontend || backend) → integrate →
secure → ship`. `secure` is the pipeline's final gate before ship — never skip it. See
`../../SKILL.md` for the orchestrator's full mode routing and auto-detection.
