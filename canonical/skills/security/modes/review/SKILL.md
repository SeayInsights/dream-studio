# Review — Code-Level Security Review

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a sub-mode, apply the portable skill
   contract. If a current calibration interface is available in this checkout, use it;
   otherwise rely on the table below.

1. Parse the sub-mode from the argument (first word). Default to `diff` when the input looks
   like a PR/diff review request and no sub-mode is named explicitly.
2. If no sub-mode is given and the input doesn't obviously match one, list the three below and
   ask.
3. Read `<sub-mode>/SKILL.md` completely before executing.
4. If `gotchas.yml` in this directory exists, read it before executing (shared across all three
   sub-modes).
5. Follow the sub-mode's instructions exactly as written.

| Sub-mode | File | Keywords |
|---|---|---|
| diff | diff/SKILL.md | review:, security review:, review PR:, pre-commit security: |
| audit | audit/SKILL.md | audit:, security audit:, check security:, check codebase security: |
| build | build/SKILL.md | build:security, enforce security:, security check before generate: |

## Which sub-mode

These are three genuinely different mechanisms, not three names for the same check — pick
based on the question being asked, not habit:

- **`diff`** — "Is this PR's new code exploitable?" Freeform LLM judgment over a git diff only.
  High-confidence (≥8/10), new lines only, no tool execution, opus. Never comments on
  pre-existing code. Output: `# Vuln N` blocks with severity HIGH or MEDIUM only.
- **`audit`** — "Does the whole codebase meet the 22-rule security baseline?" Rule-based:
  static tools (gitleaks, bandit, semgrep, pip-audit) plus an LLM pass per rule, against a fixed
  `rules.yml`. May report gaps that have existed for a long time — that's the point. Sonnet,
  5-tier severity (critical/high/medium/low/info), 0.75 confidence, `--changed`/`--full-repo`/
  `--sample` scope flags.
- **`build`** — "Does this about-to-be-generated snippet violate a build-blocking rule?"
  Synchronous, static-pattern-only (no LLM, no subprocess), sonnet. Blocks generation on
  critical/high; warns on medium.

Each sub-mode's exclusions, precedents, and confidence policy apply ONLY to that sub-mode —
`diff`'s 18 hard-exclusions (rate limiting, audit logging, hardening measures, outdated
libraries, timing attacks, and 13 more) do not suppress `audit`'s rule-level suppressions or
vice versa. See `core-imports.md`'s "Maintenance Notes" for the full boundary rationale and why
these were kept as sub-modes of one skill rather than three separate skills.

## Applicable regulatory anchors

This skill (all three sub-modes) addresses requirements from the following sections of
[`regulatory-anchors.md`](../../references/regulatory-anchors.md) — `diff` primarily draws on
L/M/C/O, `audit`/`build` primarily on J/L/N; see each sub-mode's own SKILL.md for which specific
anchors drive which specific rules:

- 🟠 [J. Software supply chain & secure SDLC](../../references/regulatory-anchors.md#j-software-supply-chain--secure-sdlc)
- 🟠 [L. Application security standards](../../references/regulatory-anchors.md#l-application-security-standards)
- 🟠 [M. Vulnerability management & disclosure](../../references/regulatory-anchors.md#m-vulnerability-management--disclosure)
- 🔴 [N. Identity, access & cryptography](../../references/regulatory-anchors.md#n-identity-access--cryptography)
- 🔴 [C. US federal sector-specific privacy/security](../../references/regulatory-anchors.md#c-us-federal-sector-specific-privacysecurity)
- 🔴 [O. AI-specific](../../references/regulatory-anchors.md#o-ai-specific)

See the full anchor list for tier definitions and the complete catalog of applicable regimes.

## Source Authority

`audit` and `build` both read `rules.yml` in this directory (22 rules; rules with
`action.build_mode: null` are audit-only). `diff` has no rule file — its methodology lives
entirely in `diff/SKILL.md` and its three reference docs under `../references/`.

## Automated baseline (R4)

Credential scanning is **automatic**, not on-demand-only. The scheduled `security-baseline`
workflow (`.github/workflows/security-baseline.yml`) runs the native full-history secret
scanner (`core/gates/secret_scan.py`) on a weekly cron and uploads results — exposure is caught
without invoking this skill. Invoke `audit` for **on-demand deep scans** (broader static + LLM
semantic passes over a chosen scope), *not* for the baseline. See
`docs/operations/lint-format-baseline-policy.md`.

## Integration with Other Security Modes

**Workflow:** `scan → review (diff) → mitigate → comply`

**Before:** `security:scan` to establish a client CI/Semgrep baseline.
**After:** `security:mitigate` to fix, `security:comply` for audit, `security:dashboard` for
reporting.

`audit`/`build` are a separate, in-repo concern — not part of that client-facing pipeline.

See `references/examples.md` for mode interactions and handoff patterns.

## Custom Filtering & Scanning (diff only)

Users can customize `diff` reviews for their environment by creating project-level config
files — see `diff/SKILL.md` for the full mechanism:

- `.dream/security/false-positives.txt` — exclude findings that don't apply
- `.dream/security/custom-categories.txt` — add organization-specific vulnerability categories

These do not affect `audit`/`build`, which use rule-level `suppressions` in `rules.yml` instead.
