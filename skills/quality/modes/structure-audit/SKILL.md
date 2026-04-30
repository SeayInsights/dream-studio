---
pack: quality
chain_suggests:
  - condition: "findings_found"
    next: "plan"
    prompt: "Violations found — plan refactor?"
---

# Skill: /structure-audit

**Trigger**: `/structure-audit [path]`
**Purpose**: Audit a project's folder/file structure against FSC and architecture
conventions and produce a scored, path-specific report with actionable fixes.

---

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## When to Use

- Starting a new project (audit before writing any code)
- Before a major refactor
- When onboarding Claude to an unfamiliar codebase
- Periodic health check on large projects
- When adding a new contributor (human or AI)

---

## Execution Steps

### Step 1 — Map the structure

```
find {path} -not -path '*/.git/*' -not -path '*/node_modules/*' \
  -not -path '*/__pycache__/*' -not -path '*/build/*' -not -path '*/dist/*' \
  | sort
```

Also run:
```
find {path} -name "*.py" -o -name "*.ts" -o -name "*.js" | \
  xargs wc -l 2>/dev/null | sort -rn | head -20
```
to find the largest source files.

### Step 2 — Score each dimension (0–10)

Score every dimension. Zero means the principle is completely violated. Ten means
it is fully satisfied. No rounding — use 0, 2, 4, 6, 8, or 10.

| Dimension | Weight | Question |
|---|---|---|
| Screaming architecture | 15% | Do top-level dir names describe the domain? |
| Co-location | 15% | Do related files travel together? |
| Depth budget | 10% | Max 4 levels? |
| Directory contracts | 10% | README/contract per non-trivial dir? |
| File size discipline | 15% | No files > 400 lines? |
| Naming consistency | 10% | One schema per file category? |
| Dependency direction | 10% | Deps flow one way, no circular imports? |
| Single source of truth | 10% | No duplicated config/types? |
| Claude readability | 5% | Top-level communicates intent without opening files? |

Weighted score = Σ(score × weight). Report to one decimal.

### Step 3 — Find specific violations

For each dimension with score < 8, list **every specific violation** with:
- Exact file path or directory name
- What the rule says it should be
- Concrete fix

No vague findings. "The project has some large files" is not a finding.
"`src/auth/middleware.py` is 847 lines — extract token validation to `src/auth/token.py`" is a finding.

### Step 4 — Categorize violations by severity

**Critical** (fix before any new feature work):
- Files > 600 lines
- Circular imports
- Generated files committed to git
- Source files at repository root

**High** (fix in next sprint):
- Files 400–600 lines
- Depth > 4 levels
- God directories (> 20 files flat with no sub-grouping)
- No gitignore

**Medium** (fix opportunistically):
- Missing directory README/contract
- Naming schema inconsistencies
- Top-level dirs named `utils/`, `helpers/`, `misc/`
- Type/config duplication

**Low** (fix when touching that area):
- Minor naming inconsistencies
- Shallow co-location improvements

### Step 5 — Output the report

Format:

```
# Structure Audit: {project name}
Date: {date}
Path: {audited path}
Score: {weighted score}/10

## Summary
{2–3 sentences: overall health, biggest strengths, top priority to fix}

## Dimension Scores
| Dimension           | Score | Weight | Weighted |
|---------------------|-------|--------|---------|
| Screaming arch      | X/10  | 15%    | X.X     |
| Co-location         | X/10  | 15%    | X.X     |
| Depth budget        | X/10  | 10%    | X.X     |
| Directory contracts | X/10  | 10%    | X.X     |
| File size           | X/10  | 15%    | X.X     |
| Naming consistency  | X/10  | 10%    | X.X     |
| Dependency flow     | X/10  | 10%    | X.X     |
| Single source       | X/10  | 10%    | X.X     |
| Claude readability  | X/10  |  5%    | X.X     |
| **TOTAL**           |       |        | **X.X** |

## Critical Violations
{list with exact paths and fixes — or "None"}

## High Violations
{list with exact paths and fixes — or "None"}

## Medium Violations
{list}

## Low Violations
{list}

## Top 3 Fixes (highest ROI)
1. {specific action — file/dir, what to do, expected score gain}
2. {specific action}
3. {specific action}

## Rules Reference
- FSC: `packs/quality/rules/structure/fsc.md`
- Architecture: `packs/quality/rules/structure/architecture.md`
```

### Step 6 — Write the report

Write the report to `{path}/.audit/structure-{YYYY-MM-DD}.md`.
Print the Summary and Top 3 Fixes to stdout.
If score < 6.0, print a warning: "Structure health is below threshold — address Critical violations before adding features."

---

## NASA-Grade Standards

This skill enforces NASA-grade quality. That means:

- **No rounding violations up.** If a file is 601 lines, it is a Critical violation, not High.
- **Every violation gets a specific fix.** Never a vague recommendation.
- **Score must be defensible.** If challenged, you should be able to point to the exact evidence for each dimension score.
- **Fresh eyes.** Score what you see, not what you think the developer intended.
- **Self-audit counts.** dream-studio's own structure is subject to these same rules.

---

## Quick Mode

`/structure-audit --quick [path]`

Runs only the Critical and High checks. Outputs a 10-line summary with only
violations found. No scoring, no full report. Used for fast pre-commit checks.

---

## Self-Audit Mode

`/structure-audit --self`

Audits the dream-studio plugin directory itself against these rules. dream-studio
must eat its own cooking — if it cannot pass its own audit, the rules need fixing.
