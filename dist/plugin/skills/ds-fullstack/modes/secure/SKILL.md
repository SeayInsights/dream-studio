---
pack: domains
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
