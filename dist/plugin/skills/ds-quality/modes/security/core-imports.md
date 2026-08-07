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

This skill intentionally does NOT call `ds-security:review`. They serve different roles:
- `ds-security:review` = PR diff review (what changed in this PR, high-confidence only)
- `ds-quality:security:audit` = codebase compliance scan (what's missing, full rules.yml pass)

Do not merge these skills. They have different callers, different inputs, different outputs.
