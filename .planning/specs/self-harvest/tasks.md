# Tasks: Self-Harvest

**Plan**: `.planning/specs/self-harvest/plan.md`
**Total tasks**: 9 | **Waves**: 3

---

## Wave 1 — Skill File Updates [All Parallel — different files]

### T001 [P] — Populate learn/gotchas.yml anti-bloat rules
**File**: `skills/learn/gotchas.yml`
**User story**: P1 (harvest mode foundation)
**Implements**: FR-002, FR-004, FR-005

Add 3 `avoid` entries to `skills/learn/gotchas.yml`:
1. `no-auto-promote` — Never write to skills/*/gotchas.yml or memory files directly from harvest. Output must go to meta/draft-lessons/ first and require Director approval.
2. `dedup-before-draft` — Before writing a draft lesson, check all existing gotchas.yml entries for the same insight. If already captured, log "already captured" — do not re-draft.
3. `cap-at-five` — Never produce more than 5 new draft lessons in a single harvest run. If more patterns are found, rank by evidence strength and draft the top 5 only.

**Acceptance**: `learn/gotchas.yml` has 3 non-empty avoid entries covering the rules above. File is valid YAML.

---

### T002 [P] — Extend learn/SKILL.md with harvest mode
**File**: `skills/learn/SKILL.md`
**User story**: P1 (batch harvest), P2 (backlog promotion)
**Implements**: FR-001, FR-002, FR-003, FR-004, FR-005, FR-007

Add a `## Harvest Mode` section to `skills/learn/SKILL.md` after the existing `## Promotion flow` section. The new section must include:

**Trigger**: `learn: harvest`

**Scan sources** (in order):
1. `meta/draft-lessons/` — present backlog first; walk Director through promote/reject for each
2. `.sessions/**/*.md` — all handoff and recap files; extract "what broke" and "Director correction" patterns
3. `skills/*/gotchas.yml` — dedup reference; skip any pattern already captured here
4. `~/.claude/projects/C--Users-Dannis-Seay/memory/feedback_*.md` — cross-reference feedback memories

**Anti-bloat rules**:
- Dedup check: before drafting, grep all gotchas.yml for the same insight. If found → log "already captured in skills/X/gotchas.yml", skip.
- Source confirmation: only draft if pattern appears in ≥2 distinct sources (session files, memory entries, or other gotchas).
- Cap: ≤5 new draft lessons per run. If more found, rank by evidence strength, draft top 5 only.
- Domain tagging: domain-specific lessons (Kroger, Power BI, etc.) are tagged with the target skill and only proposed for that skill's gotchas — never for core skills.

**Draft format addition**:
Auto-harvested lessons must include `Source: auto-harvest` and a `Confidence:` field (low/medium/high based on source count).

**Backlog promotion flow**:
When harvest finds drafts in `meta/draft-lessons/`, present each one inline:
```
Draft: [title]
File: meta/draft-lessons/[filename]
Lesson: [one-line summary]
Target: skills/[skill]/gotchas.yml → [avoid|best_practices|edge_cases]
Action? [promote / reject / defer]
```
Wait for Director response before writing. On "promote" → write entry to target gotchas.yml. On "reject" → move to `meta/lessons/` with status: REJECTED. On "defer" → leave as-is.

**Acceptance**: `learn/SKILL.md` has a `## Harvest Mode` section containing all 4 scan sources, dedup rule, ≥2-source rule, ≤5 cap, domain-tagging rule, auto-harvest draft format, and backlog promotion flow with inline approval gate.

---

### T003 [P] — Add auto-draft hook to recap/SKILL.md
**File**: `skills/recap/SKILL.md`
**User story**: P1 (auto-draft at session end)
**Implements**: FR-006, FR-007

After the existing `## Steps` section in `skills/recap/SKILL.md`, add a new step:

```
7. **Auto-draft** — After writing the recap file, scan what was captured for:
   - Any "Director correction" or "approach override"
   - Any "what broke" entry with an identified root cause
   If found: call `learn:` internally and write a draft lesson to `meta/draft-lessons/YYYY-MM-DD-<topic>.md` with:
   - `Source: auto-harvest (recap)`
   - `Confidence: high` (session context is available)
   - Pre-filled "What happened", "Lesson", "Evidence", "Applies to" from the recap content
   If nothing found: skip silently — do not create an empty draft.
```

Also add to the `## Rules` section:
- Auto-drafts must be flagged `Source: auto-harvest` to distinguish from manually triggered `learn:` captures.

**Acceptance**: `recap/SKILL.md` has a Step 7 that describes the auto-draft scan, specifies the trigger conditions (correction or blocker with root cause), the output format with `Source: auto-harvest`, and the silent-skip rule.

---

### T004 [P] — Add auto-draft hook to handoff/SKILL.md
**File**: `skills/handoff/SKILL.md`
**User story**: P1 (auto-draft at session end)
**Implements**: FR-006, FR-007

After Step 6 (Write both files) in `skills/handoff/SKILL.md`, add:

```
7. **Auto-draft** — After writing the handoff files, scan the "What's broken / blocked" section for items with identified root causes (not just "blocked on X" but "blocked because Y"). If a root cause is non-obvious and reusable, call `learn:` to draft a lesson:
   - `Source: auto-harvest (handoff)`
   - `Confidence: medium` (root cause is identified but may not be validated yet)
   If no root causes with non-obvious explanations: skip silently.
```

**Acceptance**: `handoff/SKILL.md` has a Step 7 that scans "What's broken" for root causes, drafts if non-obvious, marks `Source: auto-harvest (handoff)`, and skips silently if nothing qualifies.

---

## Wave 2 — Draft Lesson Promotion [All Parallel — different target files]

> **Director approval required before each write.** Present content + target file. Wait for explicit "promote this" before editing any gotchas.yml.

---

### T005 [P] — Promote to secure/gotchas.yml
**File**: `skills/secure/gotchas.yml`
**User story**: P2 (promote backlog)
**Implements**: FR-008
**Depends on**: Wave 1 complete

**Content to promote** — 2 new `avoid` entries:

Entry 1 (from `verify-before-fixing-audit`):
```yaml
- id: fix-stale-audit-findings
  severity: high
  discovered: 2026-04-19
  title: "Always verify a finding still exists before attempting to fix it"
  context: "Audit reports go stale within hours. Findings already resolved in code will still appear as open if the report has no resolution markers — causing wasted re-fix work."
  fix: "Before touching any file listed in a finding, grep or read the file to confirm the issue is still present in current code."
```

Entry 2 (from `audit-reports-need-resolution-tracking`):
```yaml
- id: annotate-findings-when-fixed
  severity: medium
  discovered: 2026-04-19
  title: "Annotate audit report findings with fix commit SHA when resolved"
  context: "A finding with no resolution marker is a liability — it will mislead the next session into re-fixing already-committed work."
  fix: "Immediately after a finding is fixed, add [FIXED: <commit-sha>] to the finding in the source report before continuing."
```

**Acceptance**: `skills/secure/gotchas.yml` contains both entries under `avoid`. File is valid YAML. Director approval confirmed before write.

---

### T006 [P] — Promote to review/gotchas.yml
**File**: `skills/review/gotchas.yml`
**User story**: P2 (promote backlog)
**Implements**: FR-008
**Depends on**: Wave 1 complete

**Content to promote** — 1 new `avoid` entry (from `audit-reports-need-resolution-tracking`):

```yaml
- id: consume-unresolved-audit-reports
  severity: high
  discovered: 2026-04-19
  title: "Never consume an audit report that has no resolution tracking"
  context: "Resuming a review from a report with no [FIXED] annotations leads to re-reviewing already-resolved findings and missing net-new issues."
  fix: "When given an audit report to act on, check for [FIXED: sha] markers. If missing, either request an annotated version or scan current file state before acting."
```

**Acceptance**: `skills/review/gotchas.yml` has 1 new avoid entry. Director approval confirmed before write.

---

### T007 [P] — Populate ship/gotchas.yml
**File**: `skills/ship/gotchas.yml`
**User story**: P2 (promote backlog)
**Implements**: FR-008
**Depends on**: Wave 1 complete

**Content to promote** — 3 new `avoid` entries (ship/gotchas.yml is currently empty):

Entry 1 (from `never-downgrade-lint-rules`):
```yaml
- id: downgrade-lint-to-pass-ci
  severity: critical
  discovered: 2026-04-19
  title: "Never lower lint/TS rules from error to warn to get CI green"
  context: "Downgrading rules hides real violations — 89 `no-explicit-any` warnings were hidden after a downgrade in dreamysuite, masking real type-safety bugs. CI green ≠ code healthy."
  fix: "Fix the errors. If a rule must be relaxed, scope it narrowly with an inline comment and create a follow-up task immediately."
```

Entry 2 (from `validate-locally-before-push`):
```yaml
- id: push-before-local-validation
  severity: critical
  discovered: 2026-04-19
  title: "Never push CI-touching code without running the full local validation chain first"
  context: "6 consecutive CI failures in a dreamysuite session were all catchable locally in seconds. Every push-and-wait cycle wastes minutes."
  fix: "Before any push touching build/lint/deps: run `npm run lint && npx tsc --noEmit && npm run build` (or equivalent). Only push after local validation passes."
```

Entry 3 (from `verify-ci-steps-exist`):
```yaml
- id: add-ci-step-before-verifying-it-works
  severity: high
  discovered: 2026-04-19
  title: "Never add a CI step without first running that command locally"
  context: "Adding a vitest step before any test files existed caused every CI run to fail immediately. A step that can never pass is worse than no step."
  fix: "Run the CI command locally first. If it exits non-zero or finds nothing to run, create the prerequisite before adding the step — or omit it entirely."
```

**Acceptance**: `skills/ship/gotchas.yml` has 3 non-empty avoid entries. Director approval confirmed before write.

---

### T008 [P] — Add to build/gotchas.yml
**File**: `skills/build/gotchas.yml`
**User story**: P2 (promote backlog)
**Implements**: FR-008
**Depends on**: Wave 1 complete

**Content to promote** — 1 new `avoid` entry (from `never-downgrade-lint-rules`):

```yaml
- id: downgrade-lint-during-build
  severity: high
  discovered: 2026-04-19
  title: "Never downgrade lint/TS rules to unblock a build task"
  context: "Lowering rules mid-build passes the task check but poisons the codebase. Later tasks inherit the false-green state."
  fix: "If lint errors block a build task, stop and fix the errors in a separate sub-task. Never trade rule integrity for task completion speed."
```

**Acceptance**: `skills/build/gotchas.yml` has 1 new avoid entry appended. Director approval confirmed before write.

---

## Wave 3 — Archive [Sequential — after all Wave 2 promotions confirmed]

### T009 — Archive promoted draft lessons
**Files**: `meta/draft-lessons/*.md` → `meta/lessons/*.md`
**User story**: P2 (clear backlog)
**Depends on**: T005, T006, T007, T008 all approved and written

1. Create `meta/lessons/` directory if it doesn't exist.
2. For each of the 5 draft files in `meta/draft-lessons/`:
   - Open the file
   - Change `Status: DRAFT` to `Status: PROMOTED`
   - Add `Promoted: 2026-04-29` and `Promoted-to: skills/[target]/gotchas.yml`
   - Move (copy + delete original) to `meta/lessons/`
3. Confirm `meta/draft-lessons/` is now empty.

**Acceptance**: `meta/draft-lessons/` is empty. `meta/lessons/` contains 5 files each with `Status: PROMOTED` and `Promoted:` date. No draft files remain.

---

## Summary Table

| Task | File | Wave | Deps | Est. |
|---|---|---|---|---|
| T001 | `skills/learn/gotchas.yml` | 1 [P] | none | small |
| T002 | `skills/learn/SKILL.md` | 1 [P] | none | medium |
| T003 | `skills/recap/SKILL.md` | 1 [P] | none | small |
| T004 | `skills/handoff/SKILL.md` | 1 [P] | none | small |
| T005 | `skills/secure/gotchas.yml` | 2 [P] | Wave 1 | small |
| T006 | `skills/review/gotchas.yml` | 2 [P] | Wave 1 | small |
| T007 | `skills/ship/gotchas.yml` | 2 [P] | Wave 1 | small |
| T008 | `skills/build/gotchas.yml` | 2 [P] | Wave 1 | small |
| T009 | `meta/draft-lessons/ → meta/lessons/` | 3 | T005-T008 | small |

**Total files touched**: 9 skill/gotcha files + spec.md update + 5 draft lesson files = 15
**No code changes** — Markdown and YAML only.
