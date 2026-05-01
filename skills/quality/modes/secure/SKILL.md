---
name: secure
model_tier: opus
description: "Security review — parallel OWASP+STRIDE analyst subagents produce severity-tagged findings with specific fixes. Trigger on secure:, /secure, check security, review architecture, or PRs touching auth/payments/user data/APIs."
user_invocable: true
args: mode
argument-hint: "[pr-review | architecture-review | dependency-audit] [--quick]"
pack: quality
chain_suggests:
  - condition: "critical_findings"
    next: "mitigate"
    prompt: "Critical findings — run mitigate?"
  - condition: "clean"
    next: "verify"
    prompt: "Security clean — verify?"
---

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

## Signal Scale

Security analysts use the standard 5-point scale mapped to severity:

| Signal | Severity | Meaning | Ship impact |
|--------|----------|---------|-------------|
| strong-accept | CLEAN | No issues found in this area | No impact |
| accept | LOW | Informational, non-blocking findings | No impact |
| neutral | MEDIUM | Notable concerns, worth reviewing | Flag for review |
| reject | HIGH | Serious vulnerability, blocks ship | **BLOCKED** |
| strong-reject | CRITICAL | Severe vulnerability, fix immediately | **BLOCKED** |

## Analyst Output Schema

Every analyst returns exactly this JSON:
```json
{
  "signal": "strong-accept|accept|neutral|reject|strong-reject",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentences on security posture in this area",
  "key_factors": [
    "SEVERITY: finding description @ location — specific fix",
    "SEVERITY: finding description @ location — specific fix",
    "SEVERITY: finding description @ location — specific fix"
  ]
}
```

`key_factors` format: `"CRITICAL: SQL injection in login @ api/auth.js:34 — use parameterized queries"`
- Severity prefix: CRITICAL, HIGH, MEDIUM, LOW, or CLEAN (if no findings)
- Location: file:line for code reviews, component name for architecture reviews
- Fix: specific, actionable remediation — never "needs improvement"

---

## Orchestration Steps

Follow in order. Do not skip. Do not proceed past a failed gate.

### Step 0: Parse Arguments

Extract from user input:
- `mode` — one of: `pr-review`, `architecture-review`, `dependency-audit`
- `--quick` flag — if present, use `quick_analysts` list
- `input` — the code diff, architecture description, or dependency file content

If mode is missing: default to `pr-review`. If input is absent: ask — "Paste the code diff, architecture description, or dependency file to review."

### Step 1: Validation Gate (BP1)

1. Read `skills/secure/modes.yml`. Confirm the requested mode exists.
2. Get the analyst list for this mode (or `quick_analysts` if `--quick`).
3. For each analyst, confirm `skills/secure/analysts/{name}.yml` exists.
4. Read each analyst YAML. Verify required fields: `name`, `perspective`, `weight`, `model`, `prompt_template`.
5. If ANY file is missing or field absent: **stop** with specific error.
6. If mode `status` is `experimental`: warn — "Mode `{mode}` is experimental." Continue without waiting.

### Step 2: Concurrency Guard (BP9)

Read `~/.dream-studio/secure/checkpoint.json`.

- If `status` is `"reviewing"`: ask — "Security review already in progress ({checkpoint.input_summary}). Resume, restart, or cancel?"
  - **Resume** → go to Step 4
  - **Restart** → reset checkpoint to `{"schema_version": 1, "status": "idle"}`, continue
  - **Cancel** → stop
- If `status` is `"idle"` or `"complete"`: continue

### Step 3: Input Summary (BP8)

Summarize the input for analyst dispatch:
- For `pr-review`: list changed files, key functions/routes modified, framework/language detected
- For `architecture-review`: list components, data flows, trust boundaries, external integrations
- For `dependency-audit`: list dependency manager, total packages, any already-flagged packages

Keep to 15 lines max. This summary + the raw input both go to analysts (security context requires full code).

Write initial checkpoint:
```json
{
  "schema_version": 1,
  "mode": "<mode>",
  "input_hash": "<12-char sha256>",
  "input_summary": "<summary>",
  "timestamp": "<ISO-8601>",
  "status": "reviewing",
  "completed_analysts": {},
  "pending_analysts": ["<analyst1>", ...],
  "findings_aggregate": null,
  "verdict": null,
  "report_path": null
}
```

Write via temp-file-then-rename. Update feed `~/.dream-studio/feeds/secure.json`: set `in_progress`.

### Step 4: Dispatch Analyst Subagents

Read `max_parallel` from mode config (default: 3).

For each wave of `max_parallel` analysts:

1. Read each analyst's YAML.
2. Build prompt by substituting `{{name}}`, `{{perspective}}`, `{{input}}` (full input + summary) in `prompt_template`.
3. Dispatch in parallel using Agent tool.
4. Wait for all in wave to complete.
5. **Validate each response (BP3):**
   - Parse as JSON. Check `signal` in enum. Check `confidence` 0.0-1.0. Check `reasoning` non-empty. Check `key_factors` is array.
   - If validation fails: retry once with "Return ONLY valid JSON with signal, confidence, reasoning, key_factors. key_factors must be an array of strings in format SEVERITY: description @ location — fix."
   - If retry fails: mark analyst failed, continue pipeline.
6. Save each signal to checkpoint `completed_analysts`. Remove from `pending_analysts`.
7. Write checkpoint after each wave (temp-file-then-rename).

**Analyst set is mode-specific.** `pr-review` dispatches only OWASP analysts (injection, auth, exposure, access-control, misconfig, dependencies). `architecture-review` dispatches only STRIDE analysts (stride-spoofing, stride-tampering, stride-repudiation, stride-disclosure, stride-dos, stride-elevation). `dependency-audit` dispatches only the dependencies analyst. Never mix analyst sets across modes.

### Step 5: Quorum Check (BP2)

- Read `min_quorum` from mode config.
- If successful analysts >= `min_quorum`: proceed.
- If not: **verdict = BLOCKED, reason = `INCOMPLETE_REVIEW`**. An incomplete security review never defaults to pass. Save checkpoint. Report: "Security review incomplete: {n}/{total} analysts returned valid signals (need {min_quorum}). Verdict: BLOCKED — fix analyst failures and resume before shipping."

### Step 6: Severity Aggregation

For each completed analyst:
- Parse `key_factors` for severity prefix (CRITICAL, HIGH, MEDIUM, LOW, CLEAN).
- Build a flat findings list across all analysts.
- Count: critical=N, high=N, medium=N, low=N, clean=N.

**Determine verdict:**
- If any analyst returned `reject` or `strong-reject` → **BLOCKED**
- If all analysts returned `strong-accept` or `accept` → **SHIP**
- If any analyst returned `neutral` → **SHIP WITH FLAGS** (review mediums before next sprint)

**Synthesis strategy: `any-reject`**
One HIGH or CRITICAL = BLOCKED. No weighted averaging. Security is not a vote.

Save aggregate:
```json
{
  "findings_aggregate": {
    "critical": N, "high": N, "medium": N, "low": N, "clean": N,
    "blocking_analysts": ["analyst-name"],
    "verdict": "SHIP|BLOCKED|SHIP_WITH_FLAGS"
  }
}
```

### Step 7: Synthesis (architecture-review only, or if always_synthesize: true)

For `pr-review` and `dependency-audit` with no contested findings: skip synthesis — use mechanical verdict.

For `architecture-review`: dispatch synthesis subagent (model: sonnet):

```
You are a security architect reviewing a STRIDE threat model analysis.

## Analyst Findings
{For each STRIDE analyst: name, signal, reasoning, key_factors}

## Verdict
{Mechanical verdict: SHIP/BLOCKED/SHIP_WITH_FLAGS}
{Blocking analysts if any}

## Your Task
Produce a threat model summary with:

### Threat Surface
2-3 sentences on the overall attack surface.

### Critical Paths
Which threat vectors are most exploitable and in what order of priority.

### Mitigations
For each HIGH/CRITICAL finding: specific architectural mitigation, not generic advice.

### Accepted Risks
LOW/MEDIUM findings that are acceptable in the current threat model with justification.

Output as clean markdown. No preamble.
```

Post-check: verify all 4 sections present. Retry once if missing.

### Step 8: Write Report

```markdown
# Security Review: {mode} — {input_summary}
**Date:** {ISO-8601}
**Mode:** {mode}
**Analysts:** {N} ({list})
**Verdict:** {SHIP ✓ | BLOCKED ✗ | SHIP WITH FLAGS ⚠}

---

## Findings Summary

| Severity | Count |
|----------|-------|
| CRITICAL | {N} |
| HIGH | {N} |
| MEDIUM | {N} |
| LOW | {N} |
| CLEAN | {N} |

---

## Findings by Analyst

{For each analyst:}
### {analyst-name} ({signal})
{reasoning}

**Findings:**
{each key_factor on its own line, prefixed with severity badge}

---

{If architecture-review: include synthesis threat model here}

## Methodology
- Signal: strong-accept (CLEAN) → strong-reject (CRITICAL)
- Verdict: any reject/strong-reject = BLOCKED regardless of other signals
- Analysts: {list with model assignments}
```

Write to: `~/.dream-studio/secure/reports/{mode}-{slug}-{YYYY-MM-DD}.md`

### Step 9: Update State

Update checkpoint: `status: "complete"`, `verdict`, `report_path`.
Update feed `~/.dream-studio/feeds/secure.json`:
- Increment `reviews_completed`
- Set `last_review`: mode, scope, verdict, critical/high counts, report_path, timestamp
- Set `in_progress: null`

Write feed via temp-file-then-rename.

### Step 10: Present Results

Show:
1. **Verdict:** `SHIP ✓` / `BLOCKED ✗` / `SHIP WITH FLAGS ⚠` — one line, prominent
2. **Severity counts:** Critical: N | High: N | Medium: N | Low: N
3. **Blocking findings** (if BLOCKED): one line per HIGH/CRITICAL with location and fix
4. **Report path:** "Full report: {path}"

For BLOCKED:
- List exactly what needs to be fixed before ship
- Return to `build` with the specific finding as the task

For SHIP WITH FLAGS:
- List mediums as backlog items
- Proceed to `verify` or `ship`

---

## Resume Logic (BP5)

Same as analyze skill: read checkpoint, verify input hash, resume from pending_analysts or synthesis.

---

## Ship Gate Integration

When invoked from `dream-studio:ship`:
- Run `pr-review` mode by default
- BLOCKED verdict prevents ship completion
- SHIP and SHIP_WITH_FLAGS allow ship to continue
- Mediums are appended to the ship checklist as post-ship backlog

---

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
