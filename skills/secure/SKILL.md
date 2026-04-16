---
name: secure
description: Security review — OWASP Top 10 checklist (injection, auth, data exposure, access control, misconfig, vuln deps) and STRIDE threat model for architecture. Findings with severity + specific fixes. Trigger on `secure:`, `check security`, `review architecture`, or PRs touching auth/payments/user data/APIs.
---

# Secure — Security Review

## Trigger
`secure:`, `check security`, `review architecture`, or on any PR touching auth, payments, user data, API endpoints

## OWASP Top 10 Checklist

### 1. Injection
- [ ] SQL: parameterized queries only, no string concatenation
- [ ] Command: no shell exec with user input, use libraries instead
- [ ] XSS: output encoding, CSP headers, no dangerouslySetInnerHTML with user data

### 2. Broken Authentication
- [ ] Passwords hashed (bcrypt/argon2, not MD5/SHA)
- [ ] Session tokens: HttpOnly, Secure, SameSite=Strict
- [ ] Rate limiting on login endpoints
- [ ] No credentials in URLs, logs, or error messages

### 3. Sensitive Data Exposure
- [ ] HTTPS everywhere, HSTS header
- [ ] Secrets in environment variables, never in code
- [ ] PII: encrypted at rest, minimal collection
- [ ] API responses don't leak internal IDs or stack traces

### 4. Broken Access Control
- [ ] Server-side authorization on every endpoint (not just UI hiding)
- [ ] Resource-level checks (user can only access their data)
- [ ] CORS configured correctly (not `*` in production)
- [ ] File upload: validate type, size, scan for malicious content

### 5. Security Misconfiguration
- [ ] Default credentials removed
- [ ] Debug mode off in production
- [ ] Unnecessary HTTP methods disabled
- [ ] Security headers: X-Content-Type-Options, X-Frame-Options, CSP

### 6. Vulnerable Dependencies
- [ ] No known CVEs in dependency tree (npm audit / pip audit)
- [ ] Dependencies pinned to specific versions
- [ ] Unused dependencies removed

## STRIDE Threat Model (for architecture reviews)

| Threat | Question |
|---|---|
| **Spoofing** | Can someone impersonate a user or service? |
| **Tampering** | Can data be modified in transit or at rest? |
| **Repudiation** | Can actions be performed without logging? |
| **Information Disclosure** | Can sensitive data leak through errors, logs, or side channels? |
| **Denial of Service** | Can the service be overwhelmed or crashed? |
| **Elevation of Privilege** | Can a user gain access to resources they shouldn't have? |

## Output
```
## Security Review: [scope]
Date: YYYY-MM-DD

### OWASP findings
- [severity] [category]: [finding] — [file:line] — [fix]

### STRIDE findings (if architecture review)
- [threat]: [finding] — [mitigation]

### Summary
Critical: N | High: N | Medium: N | Low: N
Ship: YES / BLOCKED ([reason])
```

## Next in pipeline
- **YES** → proceed to `verify` (or `ship` if verify already passed)
- **BLOCKED** → return to `build` to apply fixes, then re-run `secure`

## Rules
- Critical or High findings block deployment
- Fast and sharp — not a ceremony. Focus on real risks.
- Every finding must include a specific fix, not just "needs improvement"
