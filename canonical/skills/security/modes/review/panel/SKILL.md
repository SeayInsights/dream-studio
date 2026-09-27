# Security Panel — Parallel OWASP + STRIDE Analyst Review

## Applicable regulatory anchors

This skill addresses requirements from the following sections of
[`regulatory-anchors.md`](../../../references/regulatory-anchors.md):

- 🟠 [J. Software supply chain & secure SDLC](../../../references/regulatory-anchors.md#j-software-supply-chain--secure-sdlc): the `dependency-audit` argument mode's CVE, version-pinning, and unused-package scan.
- 🟠 [L. Application security standards](../../../references/regulatory-anchors.md#l-application-security-standards): OWASP Top 10 defines the categories the `pr-review` argument mode's analysts each own one seat of.
- 🟠 [M. Vulnerability management & disclosure](../../../references/regulatory-anchors.md#m-vulnerability-management--disclosure): CVE/CVSS provides the severity baseline synthesis maps analyst signals onto.
- 🔴 [C. US federal sector-specific privacy/security](../../../references/regulatory-anchors.md#c-us-federal-sector-specific-privacysecurity): HIPAA/HITECH, FTC Act §5, and VPPA apply when the reviewed diff or architecture handles user data, health records, or tracking pixels.
- 🔴 [O. AI-specific](../../../references/regulatory-anchors.md#o-ai-specific): EU AI Act and NIST AI RMF apply when the `architecture-review` argument mode's STRIDE analysts evaluate an AI feature's design.

See the full anchor list for tier definitions and the complete catalog of applicable regimes.

## Metadata
- **Pack:** security
- **Mode:** review:panel
- **Type:** analysis
- **Model:** opus (synthesis); analyst subagents run haiku/sonnet per `analysts/*.yml` — see `modes.yml`
- **Inputs:** code_diff, file_contents, architecture_description, dependency_manifest
- **Outputs:** threat_model, findings, remediation_steps, ship_verdict

## Before you start
Read `gotchas.yml` in this directory before every invocation — it is populated (not the
JIT-pending placeholder shared by the other three sub-modes) and carries real lessons from
this mechanism's own history.

## Trigger
`secure:`, `/secure`, `review architecture:`, `threat model:`, or on any PR touching auth,
payments, user data, or API endpoints.

## Purpose
Spawn specialized security analyst subagents in parallel, each evaluating the input through
one OWASP category or STRIDE threat. Collect severity-tagged findings, detect any blocking
vulnerabilities, and produce a structured security report with a SHIP / BLOCKED verdict.

One HIGH or CRITICAL finding from any analyst = BLOCKED. The ship gate is binary.

This is the mechanism that distinguishes `panel` from its siblings: `diff` is a single freeform
opus pass over a diff with no subagent fan-out; `audit`/`build` run a fixed 22-rule engine with
static tools plus one LLM pass per rule. `panel` dispatches fresh, independent analyst
subagents — one per OWASP category or STRIDE threat — and synthesizes their signals with an
any-reject rule (never a weighted average). See `../core-imports.md` for the full boundary
rationale between all four sub-modes.

**NOT for:**
- A single-pass freeform read of a diff's new lines only (use `review:diff`).
- Whole-codebase compliance against the 22-rule baseline (use `review:audit`).
- A synchronous pre-generation enforcement gate (use `review:build`).

## Argument modes
- `pr-review` — OWASP Top 10 code scan (injection, auth, data exposure, access control, misconfig, deps, exceptional conditions). Input: code diff or file contents.
- `architecture-review` — STRIDE threat model (Spoofing, Tampering, Repudiation, Disclosure, DoS, Elevation) plus insecure-design. Input: architecture description, data flow, or API design.
- `dependency-audit` — CVE scan, version pinning, unused packages. Input: requirements.txt / package.json / lockfile.
- `--quick` flag — Run only the highest-priority analysts per argument mode.

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
