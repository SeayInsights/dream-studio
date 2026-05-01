---
name: mitigate
model_tier: sonnet
description: "Per-finding fix recommendations with code before/after, verification tests, effort estimates. Trigger on mitigate:, how to fix, generate mitigations."
user_invocable: true
args: mode
argument-hint: "[findings | single | export] [--client <name>]"
pack: quality
chain_suggests:
  - condition: "always"
    next: "build"
    prompt: "Mitigations ready — apply fixes?"
---

# Mitigate — Per-Finding Fix Recommendations

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`mitigate:`, `how to fix`, `generate mitigations`, `/mitigate`

## Purpose
For every security finding produced by `dream-studio:secure` or `dream-studio:scan`, generate an actionable mitigation: exact code before/after, a verification test, an effort estimate, and compliance impact. Match each finding to a template by rule ID, CWE, or OWASP category. Spawn sonnet subagents for complex, code-context-aware fixes. Write results to structured storage for sprint planning and `dream-studio:comply`.

This skill never modifies client code directly. It outputs recommendations the user applies and commits.

## Modes
- `findings` — Process ALL findings for a client. Reads from `~/.dream-studio/security/scans/{client}/`. Writes mitigations to `~/.dream-studio/security/datasets/{client}/mitigations.csv`.
- `single` — Generate a mitigation for one specific finding by ID. Takes `--finding <id>`.
- `export` — Export mitigations as CSV and markdown for sprint planning. Takes optional `--severity <level>` to filter.

---

## Storage
See `docs/security-storage-layout.md`. Uses: `scans/{client}/` (read), `datasets/{client}/mitigations.*` (write)

## Templates
See `templates/security/README.md`. Uses: `mitigations/*.yaml` (fix templates by CWE/OWASP)

## Client Profile
See `docs/client-profile-schema.md`. Required: `client.name`. Optional: `data.classification`, `isolation.model`, `network.proxy.*`, `compliance.frameworks`

---

## Anti-patterns

- **Modifying client code** — this skill generates recommendations only. Never write to client repo files. Output goes to `~/.dream-studio/security/datasets/` only.
- **Generating mitigations from stale findings** — always check `scan-meta.json` ingestion date. Warn if >7 days. A finding fixed last week wastes sprint capacity.
- **Template-only for ZSC-* findings** — Zscaler-network findings are highly environment-specific. Always spawn a subagent for ZSC-* rule IDs even if a template match exists, to verify proxy context is correct.
- **Generic long_term_fix** — "use better security practices" is not a long-term fix. Every `long_term_fix` must name a specific pattern, library, or architectural change.
- **Missing verification_test** — a mitigation without a runnable verification test cannot be marked done in sprint. Reject placeholder verifications like "test manually."
- **Effort inflation** — effort estimates cover the fix only, not discovery, review, or deploy. Cap single-instance fixes at 4h max. Flag anything estimated >4h as needing a spike ticket instead.
- **Overwriting live CSV without temp-rename** — always write to a temp file, then rename. A partial CSV write corrupts downstream sprint exports.
- **Skipping compliance_impact** — every finding with a CWE or OWASP category has a compliance mapping. Look it up. An empty `compliance_impact` signals incomplete analysis.

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.
