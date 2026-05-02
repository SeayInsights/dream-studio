# Secure — Parallel Security Review

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`secure:`, `/secure`, `check security`, `review architecture`, or on any PR touching auth, payments, user data, API endpoints

## Purpose
Spawn specialized security analyst subagents in parallel, each evaluating the input through one OWASP category or STRIDE threat. Collect severity-tagged findings, detect any blocking vulnerabilities, and produce a structured security report with a SHIP / BLOCKED verdict.

One HIGH or CRITICAL finding from any analyst = BLOCKED. The ship gate is binary.

## Modes
- `pr-review` — OWASP Top 10 code scan (injection, auth, data exposure, access control, misconfig, deps). Input: code diff or file contents.
- `architecture-review` — STRIDE threat model (Spoofing, Tampering, Repudiation, Disclosure, DoS, Elevation). Input: architecture description, data flow, or API design.
- `dependency-audit` — CVE scan, version pinning, unused packages. Input: requirements.txt / package.json / lockfile.
- `--quick` flag — Run only the highest-priority analysts per mode.

## Anti-patterns

- **Treating security as a vote** — do not average signals. One HIGH = BLOCKED. Period.
- **Generic fixes** — every finding must name the exact file, line, and fix. "Validate input" is not a finding.
- **Skipping dependency-audit on dependency changes** — any PR touching requirements.txt/package.json triggers dependency-audit automatically.
- **Running on untrusted input** — security review prompt templates are not hardened against prompt injection. Only review trusted code.
- **Flagging without confidence** — if an analyst can't determine whether a pattern is vulnerable without more context, it must return `neutral` with a specific question, not `reject`.
- **Acting on stale findings (L1)** — before fixing any finding from this report, grep or read
  the actual file to confirm the issue still exists in the current codebase. Reports go stale
  within hours. Wasted remediation effort is the cost of skipping this check.
- **Leaving findings unannotated after fixing (L5)** — after each finding is fixed, update
  this report with the commit SHA: `[FIXED: abc1234]`. A report with no resolution markers
  misleads every future session that reads it.

## Response Contract {#response-contract}

Every security review MUST include these 5 sections. Use this as a validation checklist:

- [ ] **Threat Model**: What could an attacker exploit?
  - Attack vectors and entry points
  - Assumptions about attacker capabilities
  - Assets at risk and potential impact
  
- [ ] **Findings**: Vulnerabilities found (severity, location, proof)
  - Severity level (CRITICAL/HIGH/MEDIUM/LOW/INFO)
  - Exact file path and line number
  - Code snippet demonstrating the vulnerability
  - Proof of concept or exploitation scenario
  
- [ ] **Remediation**: How to fix each finding
  - Specific code changes required
  - Implementation guidance with examples
  - Alternative approaches if applicable
  - Dependencies or prerequisites for the fix
  
- [ ] **Verification**: How to verify fixes work
  - Manual testing steps
  - Automated test cases to add
  - Expected behavior after remediation
  - Regression testing guidance
  
- [ ] **False Positive Check**: Did we rule out false positives?
  - Context that might make flagged code safe
  - Compensating controls in place
  - Framework/library protections active
  - Explicit confirmation: "Verified this is a true positive" or "Flagged as false positive because..."

**Ship gate verdict**: SHIP or BLOCKED (based on severity threshold)

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
