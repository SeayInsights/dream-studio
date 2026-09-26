# Security Mode — Core Imports

## Imported Modules

### ds-core/git.md
**Usage:** Scope determination for `--changed` mode. Get list of files changed vs. base branch.
**Where used:** `audit/SKILL.md` — Step 1 (scope determination)
**Pattern used:** `git diff --name-only main...HEAD` (or `origin/main...HEAD` in CI)
**Impact if changed:** `--changed` scope breaks; fall back to `--full-repo` required until fixed.

### ds-security/references/regulatory-anchors.md
**Usage:** Regulatory framework reference for rule source attribution and `anchor_ref` link targets.
**Where used:** `rules.yml` — each rule's `regulatory_anchors[*].anchor_ref` field
**Impact if changed:** Section anchor URLs in rules.yml may need updating. No runtime behavior change — `anchor_ref` is informational only.

### docs/architecture/launch-readiness-checklist.md
**Usage:** Primary source document for rule content (section 3 — Security baseline).
**Where used:** `rules.yml` — `source.list: LIST-2` + `source.item` text
**Impact if changed:** `source.item` text in rules.yml may need updating. No runtime behavior change — source attribution is informational only.

## Impact Analysis

**If `ds-core/git.md` changes:**
- Re-test `--changed` scope in audit mode
- Verify `git diff --name-only` command format still produces file list in expected format

**If `ds-security/references/regulatory-anchors.md` changes (section headers renamed):**
- Update `anchor_ref` URLs in all 22 rules in `rules.yml`
- No rule behavior changes — `anchor_ref` is a human-readable link, not a logic dependency

**If `docs/architecture/launch-readiness-checklist.md` changes (rule source text updated):**
- Update `source.item` fields in `rules.yml` if the canonical item text changed
- Review whether any new 🔴 items should become new rules

## Maintenance Notes

`audit`/`build` (this rule engine) and `diff` (the freeform PR/pre-commit review methodology)
were merged into one mode, `ds-security:review`, in the pack-split campaign's security merge
(2026-09-26) — they had previously been kept in separate skills (`ds-quality:security` and
`ds-security:review`) specifically to avoid conflating them. That separation is preserved as a
sub-mode boundary rather than a skill boundary, because the two remain genuinely different
mechanisms answering different questions:

- **`diff`** = "is this PR's new code exploitable?" High-confidence only (≥8/10), new lines only,
  no tool execution, opus, HIGH/MEDIUM severity only.
- **`audit`** = "does the whole codebase meet the 22-rule security baseline?" May report
  pre-existing gaps, runs static tools (gitleaks/bandit/semgrep/pip-audit), sonnet, 5-tier
  severity, 0.75 confidence.
- **`build`** = "does this about-to-be-generated snippet violate a build-blocking rule?"
  Synchronous, static-pattern-only, no LLM call, sonnet.

Each sub-mode keeps its own thresholds, model tier, and output format (see `config.yml`'s
`diff:` section and `../SKILL.md`'s "Which sub-mode" table) — do not average or unify them; a
reviewer choosing the wrong sub-mode for the question being asked is the actual failure mode
this boundary exists to prevent, not "the modes disagree".
