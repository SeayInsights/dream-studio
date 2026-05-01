# dream-studio:quality — Code Quality & Learning

Code quality toolkit: debug, polish, harden, secure, learn

---

## Mode: debug

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`debug:`, `diagnose:`

## Purpose
Diagnose and fix bugs using disciplined hypothesis testing. One variable at a time.

## Pre-flight Intelligence
Before starting diagnosis, query the registry:
1. **Gotcha check** — `get_gotchas_for_skill('quality:debug')` from `hooks/lib/studio_db.py` (falls back to file-walk via `gotcha_scanner.py` if registry not populated). Show top 3 recent gotchas — debug sessions are the highest-value place for this.
2. **Approach history** — `get_best_approaches('quality:debug')` from `hooks/lib/studio_db.py`. Show top 3 approaches that worked for past debug sessions. Prior debug patterns often short-circuit new diagnosis.

## Steps

**Pre-flight Gotcha Briefing** — Before starting diagnosis, surface recent gotchas for the domain being debugged:
1. Run `hooks/lib/gotcha_scanner.py` → `search_gotchas(topic)` where topic is the bug description
2. Also run `get_recent_gotchas(limit=3)` for the debug skill
3. Display matches as: `[severity] gotcha-id — title`
4. If a gotcha directly matches the bug symptoms, highlight it: "⚡ This gotcha may explain the issue"
5. Debug sessions are the highest-value place for this — most gotchas originated from debug sessions

0. **Load project context** — If `.planning/GOTCHAS.md` exists, read it before forming any hypothesis. Known failure patterns there may short-circuit the entire debug loop.
1. **Reproduce** — Confirm the bug exists. Get exact steps, error messages, stack traces.
2. **Hypothesize** — Form 2-3 hypotheses ranked by likelihood based on the error.
3. **Test** — Test the most likely hypothesis first. One variable at a time.
4. **Narrow** — Eliminate hypotheses based on results. Add new ones if needed.
5. **Fix** — Apply the fix. Verify it resolves the issue without introducing new ones.
6. **Document** — Record what was tried and ruled out so the next session doesn't repeat.
7. **Capture** — After any debug session that required ≥3 hypothesis iterations OR revealed a reusable pattern, invoke `learn:` before closing. This is not optional — draft lessons are the input to dream-studio's self-improvement loop. After the fix is committed and the GitHub issue is created, invoke `learn:` with the debug log summary as input.

## Debug log format
Track in conversation to prevent retrying failed approaches:
```
## Debug: [symptom]

### Reproduce
[exact steps to reproduce]

### Hypothesis 1: [description] — LIKELY / RULED OUT
- Test: [what you did]
- Result: [what happened]
- Conclusion: [ruled out / confirmed / need more data]

### Hypothesis 2: [description]
...

### Fix
[what was changed and why]

### Verified
[evidence the fix works + no regressions]
```

## Next in pipeline
→ back to `build` or `verify` (wherever the failure originated)

## Anti-patterns

| ❌ Wrong | ✅ Correct |
|---|---|
| "Let me try this" without stating a hypothesis | State hypothesis before every test: "I think X because Y" |
| Changing multiple things between tests | One variable per test — isolate the change |
| Ignoring error messages and guessing | Read the full error message first; it usually names the cause |
| Repeating a failed approach from a previous session | Read the debug log before forming hypotheses |
| Shotgun debugging (changing 5 things at once) | Test the single most likely hypothesis first |
| Skipping reproduction ("I think I know what it is") | Always reproduce with exact steps before hypothesizing |
| Not tracking hypotheses | Log every hypothesis — even obvious ones — so the next session doesn't repeat |
| Using shell grep or findstr to search TMDL/UTF-8 files on Windows | Use Python with `open(path, encoding='utf-8')` — shell tools break on accented characters |
| Continuing past 5 failed hypotheses without escalating | After 5 failures, stop and escalate to Director with the full debug log |

---

## Mode: polish

# Polish — UI Quality Decision Tree

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`polish ui:`, `clean up ui:`, `polish site:`, `critique design:`, `audit design:`, `redesign:`, `upgrade ui:`, `make it premium:`, or auto-triggered after `build page:`/`build component:`

## Purpose
Single decision tree replacing individual layout, typography, color, animation, copy, responsive, and edge case skills. One invocation, not fifteen.

## Checklists
Domain-specific validation checklists live in `checklists/`:
- `web-design.yml` — 8-dimension UI evaluation (typography, color, layout, spacing, images, shadows, accessibility, visual hierarchy)
- `fluent-design-compliance.yml` — 4px spacing, semantic colors, WCAG AA, focus indicators
- `material-design-compliance.yml` — 8dp grid, elevation, typography scale, 48x48dp touch targets
- `data-viz-accessibility.yml` — color contrast ≥4.5:1, alternatives to color, data table fallback

Load the relevant checklist(s) in Step 2 when fixing dimensions.

## Flow

### Step 1: Critique (score current state)
Open the app in a browser. Score each dimension 1-5:

| Dimension | What to check |
|---|---|
| Layout | Grid alignment, spacing consistency, visual rhythm, whitespace |
| Typography | Hierarchy (H1 > H2 > body clear?), line height, line length (45-75 chars), font pairing |
| Color | Contrast ratios (AA 4.5:1 min), consistent palette usage, dark/light mode, anti-slop check |
| Animation | Meaningful motion (not decoration), timing (200-400ms for UI, 600ms+ for emphasis), easing |
| Copy | Labels clear?, error messages actionable?, CTAs specific (not "Submit")?, empty state guidance? |
| Responsive | 320px, 768px, 1024px, 1440px — layout breaks? Touch targets 44px? Readable? |
| Edge cases | Error states, empty states, loading states, long text overflow, missing images |

Output format:
```
## Critique: [page/component]
Layout: 4/5 — [note]
Typography: 3/5 — [issue]
Color: 5/5
Animation: 2/5 — [issue]
Copy: 3/5 — [issue]
Responsive: 4/5 — [note]
Edge cases: 2/5 — [missing states]
Overall: 3.3/5
Priority fixes: [ranked list]
```

### Step 2: Fix (targeted by dimension)
Work through priority fixes from critique. For each dimension scoring 3 or below:

**Layout** — Fix grid alignment, normalize spacing to 4/8/16/24/32px scale, add whitespace between sections, fix visual rhythm.

**Typography** — Establish clear size scale (1.25 ratio), fix line heights (1.4-1.6 for body, 1.1-1.2 for headings), constrain line length, pair fonts (1 display + 1 body max).

**Color** — Replace failing contrast, apply 60/30/10 rule, check anti-slop list (no purple gradients, no uniform corners, no drop shadows everywhere). Also load `checklists/design-anti-patterns.yml` and run each check — flag any violations and add to the priority fix list.

**Animation** — Add entrance animations for content (fade + translate, 200-400ms), add hover/press feedback on interactive elements, remove gratuitous motion.

**Copy** — Rewrite vague labels, make error messages say what went wrong + what to do, make CTAs specific ("Create account" not "Submit"), add empty state messages.

**Responsive** — Fix breakpoint issues starting from smallest screen up, ensure touch targets, test overflow.

**Edge cases** — Add error state UI, empty state UI, loading skeletons, handle long text (truncate or wrap), handle missing images (fallback).

### Step 3: Final pass
After fixes, re-score. All dimensions should be 4+ or have a documented reason for exceptions.

## Output
Updated code with commits per dimension fixed. Final critique score.

## Next in pipeline
→ `verify` (prove the polish looks right in browser)

---

## Mode: harden

# Harden — Project Standards Audit & Fix

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Project memory system (always first)
Before any other hardening work, check for these four files:
- `CLAUDE.md` in the project root
- `.planning/CONSTITUTION.md`
- `.planning/GOTCHAS.md`
- `CONTEXT.md` in the project root

If any are missing, create them now. These are the project memory system — without them, Claude has no persistent context between sessions. Use these stubs:
- `CLAUDE.md`: `# READ FIRST\n[project name] — [one line description]\n\nSee .planning/CONSTITUTION.md for architecture decisions.`
- `.planning/CONSTITUTION.md`: `# Constitution\n\n## SSOT Map\n[Fill in: key files and what they own]\n\n## Key Decisions\n[Fill in: architectural choices and why]\n\n## Forbidden Patterns\n[Fill in: anti-patterns to avoid]`
- `.planning/GOTCHAS.md`: `# Gotchas\n\n[Empty — update when something breaks]`
- `CONTEXT.md`: `# Context\n\n## Domain Terms\n[Fill in: project-specific vocabulary — what words mean in THIS codebase]\n\nSee \`skills/harden/templates/context-template.md\` for full template.`

CONTEXT.md is the shared domain vocabulary — it defines what project-specific terms mean and prevents AI verbosity and drift across sessions.

## Trigger
`/harden` — runs full audit by default
`/harden audit` — audit only, no changes
`/harden fix tier1` — fix structural gaps (Makefile, pyproject.toml, SECURITY.md, CONTRIBUTING.md, requirements files)
`/harden fix #N` — fix a specific item by number

---

## Phase 1: Audit

Spawn an Explore subagent (model: haiku) with this task:

> Scan the current working directory for the 20 harden checklist items listed below. For each item, report: ✓ present / ✗ missing / ⚠ partial. Include a one-line reason for partial. Return as a markdown table. Also note any language (Python, TypeScript, etc.) and any existing CI files.

**The 20 checklist items:**

| # | Item | What to check |
|---|------|---------------|
| 1 | Makefile | File exists with `test`, `lint`, `fmt` targets |
| 2 | pyproject.toml | `[tool.black]` and `[tool.flake8]` sections present |
| 3 | Coverage config | `.coveragerc` or `[tool.coverage.*]` in pyproject.toml |
| 4 | UTC enforcement | No bare `datetime.now()` (without timezone) in source files |
| 5 | Input validation | Pydantic or schema validation at stdin/API entry points |
| 6 | SECURITY.md | File exists with contact and disclosure process |
| 7 | CONTRIBUTING.md | File exists with branch naming and commit format |
| 8 | freezegun | `freezegun` in dev requirements |
| 9 | factory_boy | `factory-boy` or `factory_boy` in dev requirements |
| 10 | Audit log | Append-only event log (`.jsonl`) written by handlers |
| 11 | .pre-commit-config.yaml | File exists with black and flake8 hooks |
| 12 | pip-audit | `pip-audit` in dev requirements or Makefile `security` target |
| 13 | Requirements split | Separate `requirements.txt` (runtime) and `requirements-dev.txt` |
| 14 | Error tracking | Sentry stub or equivalent in codebase |
| 15 | Bill of Materials | `scripts/bom.py` or equivalent BOM script |
| 16 | Integration tests | `tests/integration/` directory with test files |
| 17 | Health/status reporter | Handler or script for health check / pulse |
| 18 | CHANGELOG | CHANGELOG.md in Keep a Changelog format |
| 19 | README | README.md with: title + badges, quick start, usage examples, project structure tree, contributing + license sections |
| 20 | Telemetry | Hook or handler usage telemetry (token log, audit.jsonl) |

After the Explore subagent returns:
1. Render the gap report as a scored table (✓/✗/⚠)
2. Count: X present, Y missing, Z partial
3. Ask: "Run `/harden fix tier1` to fill structural gaps, or `/harden fix #N` for a specific item?"

---

## Phase 2: Fix

### Tier 1 structural files (items 1, 2, 3, 6, 7, 11, 13, 19)

For each missing structural file, copy from `templates/project-standards/` in the dream-studio repo:
- `README.md` → project root (replace `{project-name}`, `{owner}`, `{repo}` placeholders; then fill sections from actual project)
- `Makefile` → project root (parameterize Python command if needed)
- `pyproject.toml` → project root
- `.coveragerc` → project root (or add to pyproject.toml)
- `SECURITY.md` → project root (replace `{{contact_email}}` and `{{project_name}}`)
- `CONTRIBUTING.md` → project root
- `.pre-commit-config.yaml` → project root
- `requirements.txt` → project root (stub)
- `requirements-dev.txt` → project root (stub, merge with existing)

**README.md audit — mark item 19 as ⚠ partial if the file exists but is missing any of:**
- Badges (CI, version, license)
- Quick start (≤5 copy-paste steps)
- Usage examples with code blocks
- Project structure tree (annotated folder/file listing)
- Contributing and License sections

**Never overwrite an existing file** — only fill gaps.

### Code stubs (items 4, 5, 8, 9, 10, 12, 14, 15)

For missing code-level items, create stub files with `# TODO: implement` comments:
- UTC enforcement: create `hooks/lib/time_utils.py` stub → replace bare `datetime.now()` manually
- Pydantic models: create `hooks/lib/models.py` stub
- Audit log: create `hooks/lib/audit.py` stub
- Sentry telemetry: create `hooks/lib/telemetry.py` stub
- BOM script: create `scripts/bom.py`

Copy from `templates/project-standards/hooks/lib/` where templates exist.

### Single-item fix (`/harden fix #N`)

Fix only the item with that number. Use templates where available, generate stubs otherwise.

---

---

## Phase 3: Enforcement Audit (gap analysis)

After the Phase 1 file audit, always append this enforcement status table to the report:

> Scan `hooks/hooks.json` to verify which handlers are registered, then report:

| Standard | Status | How |
|---|---|---|
| Context budget + handoff | Auto / Missing | `on-context-threshold` in UserPromptSubmit hooks |
| Project health check | Auto / Missing | `on-pulse` in UserPromptSubmit hooks |
| Security pattern scan | Auto / Missing | `on-security-scan` in PostToolUse Edit\|Write hooks |
| CHANGELOG reminder | Auto / Missing | `on-changelog-nudge` in Stop hooks |
| Hardening nudge | Auto / Missing | `on-tool-activity` in PostToolUse hooks |
| Code format/lint | Auto / Missing | `.pre-commit-config.yaml` with black + flake8 |
| Test coverage threshold | Auto / Missing | `pyproject.toml [tool.coverage.report] fail_under` |
| Full security review | **Manual** | `/secure` must be invoked |
| Folder structure audit | **Manual** | `/structure-audit` must be invoked |
| Workflow gating | **Manual** | `/workflow run <name>` must be invoked |

Mark each Auto row ✓ if the handler is registered in hooks.json, ✗ if missing.

---

## Rules

- Always confirm before overwriting any existing file
- Always run tests after making changes: `make test`
- Report what was changed and what still needs manual work

---

## Mode: secure

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

## Detailed Reference

See `examples.md` in this directory for detailed steps, schemas, templates, and integration points.

---

## Mode: structure-audit

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

---

## Mode: learn

# Learn — Pattern Capture and Promotion

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`learn:`, `capture lesson:`, or when something notably works or breaks during a build. Use `learn: harvest` for cross-project batch extraction from session history.

## Purpose
Extract lessons from builds and promote them to studio knowledge.

## Draft lesson format
Write to `meta/draft-lessons/YYYY-MM-DD-<topic>.md`:
```markdown
# Draft Lesson: [topic]
Date: YYYY-MM-DD
Source: [what build/session this came from]
Status: COMPLETE

## What happened
[Concrete description — what worked or what broke]

## Lesson
[The reusable insight — stated as a rule or pattern]

## Evidence
[Specific files, commits, errors, or outcomes that support this]

## Applies to
[When should this lesson be applied? Which domains/tools/patterns?]
```

## Promotion flow
1. **Capture** — Write to DB via `insert_lesson()` from `hooks/lib/studio_db.py` as primary store, then write draft lesson to `meta/draft-lessons/`
2. **Accumulate** — Drafts sit until Director reviews (via `on-meta-review` or manual check)
3. **Review** — Director approves, edits, or rejects each draft
4. **Promote** — Approved lessons become:
   - Memory entries (if long-term knowledge)
   - Skill updates (if pattern should change a skill's instructions)
   - Agent updates (if behavior should change an agent's config)
5. **Archive** — Promoted drafts move to `meta/lessons/` with status: PROMOTED

## Harvest Mode

### Trigger
`learn: harvest`

### Purpose
Batch-scan all historical sources for reusable patterns. Surface the draft backlog for promotion. No skill files are modified until Director explicitly approves each change.

### Config check
Before running any scan, verify `~/.dream-studio/config.json` exists and `harvest.projects_root` is non-empty.
If missing or empty: stop and output — "Harvest not configured. Run `workflow: run studio-onboard` to set your projects root, then retry."

### Scan protocol (run in this order)

**Step 1 — Backlog first**
Scan `meta/draft-lessons/`. For each file, present inline:
```
Draft: [title]
File: meta/draft-lessons/[filename]
Lesson: [one-line summary]
Target: skills/[skill]/gotchas.yml → [avoid|best_practices|edge_cases]
Action? [promote / reject / defer]
```
Wait for Director response before writing anything. On "promote" → write entry to target gotchas.yml. On "reject" → move file to `meta/lessons/` with `Status: REJECTED`. On "defer" → leave as-is.

**Step 2 — Session history**
Determine scan scope from `config.yml`:
1. **Auto-discover**: scan every subdirectory of `harvest.projects_root` that contains a `.sessions/` folder — each qualifies as a harvest target automatically. No registration needed; new projects are picked up the moment they have a `.sessions/` dir.
2. **Extra paths**: also scan any paths listed in `harvest.extra_paths` for one-offs outside `projects_root`.
3. **Local**: always include the dream-studio repo's own `.sessions/` regardless of config.

For each discovered project, scan `<project>/.sessions/**/*.md` (handoffs and recaps). Extract:
- "What's broken / blocked" sections with identified root causes
- "Director correction" mentions
- Patterns that appear in 2+ different session files (across any projects)

Tag each extracted pattern with its source project path so domain-specific lessons stay scoped correctly.

**Step 3 — Dedup check**
Scan `skills/*/gotchas.yml`. For each candidate pattern from Step 2, grep existing entries. If the insight already exists → log "already captured in skills/[skill]/gotchas.yml" and skip.

**Step 4 — Memory cross-reference**
Read `claude_memory_path` from `~/.dream-studio/config.json`. Scan `<claude_memory_path>/feedback_*.md` for feedback entries that have no corresponding gotchas.yml entry and could be generalized into a reusable skill rule.
If `claude_memory_path` is not set in config.json, skip this step and note "memory scan skipped — run `workflow: run studio-onboard` to configure."

### Anti-bloat rules (enforced — see gotchas.yml)
- **Dedup first**: never draft a lesson that already exists in any gotchas.yml
- **≥2 sources**: only draft lessons with evidence from ≥2 distinct sources
- **≤5 cap**: draft at most 5 new lessons per run — rank by evidence count, take top 5
- **Domain tagging**: domain-specific lessons (Kroger, Power BI client-specific, etc.) must be tagged with the target skill and never promoted to core skill gotchas

### Auto-harvest draft format
Auto-harvested drafts use an extended format with two additional fields:
```
Source: auto-harvest
Confidence: [low|medium|high]  # based on number of distinct sources found
```
- high = 3+ distinct source confirmations
- medium = 2 distinct sources
- low = 1 source (these should rarely be drafted — requires strong evidence)

### No-harvest conditions
If harvest finds nothing new: output "No new patterns found. [N] drafts reviewed." Do not create empty draft files. Do not re-draft lessons already in a gotchas.yml.

## Daily Harvest Mode

### Trigger
`learn: daily` — auto-triggered by daily-close workflow or manual invocation

### Purpose
Lightweight end-of-day learning capture. Scoped to today only — no cross-project scanning.

### Sources (in order)
1. **Micro-captures** — read `~/.dream-studio/meta/today.md` (written by `hooks/lib/micro_capture.py` throughout the day)
2. **Today's sessions** — scan `.sessions/YYYY-MM-DD/` for today's date only (handoffs and recaps)
3. **Git log** — `git log --since="today" --oneline` for commits made today

### Protocol
1. Read all three sources above
2. Extract candidate patterns:
   - Any micro-capture with `outcome:correction` — something went wrong and was fixed
   - Any handoff `lessons_this_session` entry
   - Any recap `Risk flags` with identified root causes
   - Any commit that was a fix for something that broke during the build
3. Apply anti-bloat rules from Harvest Mode:
   - Dedup against existing `meta/draft-lessons/` and `skills/*/gotchas.yml`
   - Only draft lessons with evidence from the day's work
   - ≤5 new drafts per daily run — rank by significance
4. Write drafts to `meta/draft-lessons/YYYY-MM-DD-<topic>.md` with:
   - `Source: daily-harvest`
   - `Confidence: medium` (single-day evidence)
5. Output summary: "Daily harvest: N candidates found, M drafts written, K skipped (already captured)"

### No-harvest conditions
If no corrections, risk flags, or notable patterns found today: output "Clean day — no new patterns." Do not create empty drafts.

## When to capture
- A debugging session reveals a non-obvious root cause
- A build approach succeeds that contradicts initial expectations
- A tool/MCP behaves differently than documented
- A pattern from one domain transfers to another
- Director explicitly corrects an approach (capture why)

## Rules
- Draft lessons are proposals — Director decides what gets promoted
- One lesson per file — don't combine unrelated insights
- Be specific: "D1 doesn't enforce foreign keys" not "databases are tricky"
- Include evidence — lessons without evidence are opinions
- Create `meta/draft-lessons/` directory if it doesn't exist

---

## Mode: coach

# Coach — Claude Code Workflow Advisor

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`/coach <mode>`, `coach:`, or invoked when you want meta-feedback on your Claude Code usage patterns

## Purpose
This skill does not build things. It evaluates the process by which you build things. Spawn parallel analyst subagents that each look at one dimension of your Claude Code workflow and return a grade with specific improvements.

Use coach when:
- A session felt inefficient but you're not sure why
- You want to know if you're using the right skill for a task
- Context is getting heavy and you want to know when to rewind
- You want to audit your PR patterns or agent dispatch habits

## Modes
- `workflow-fit` — Is this task matched to the right dream-studio skill?
- `context-health` — Is context being managed well? When should you start a new session?
- `pr-hygiene` — Are PRs sized correctly? Commit message quality? Branch hygiene?
- `agent-dispatch` — Are subagents being used at the right times? Model assignments correct?
- `route-classify` — Classify ambiguous intent against all known dream-studio triggers. Decision tree:
  1. **Match against dream-studio skill triggers.**
     - Confidence ≥ 0.8 → invoke the matched skill immediately via the Skill tool (do not just name it).
     - Confidence < 0.8 → present top 3 matches with scores and ask the Director to confirm before invoking.
  2. **No dream-studio skill match → check `skills/domains/ingest-log.yml`.**
     - Find the plugin root (two directories up from `skills/coach/`).
     - Read `<plugin-root>/skills/domains/ingest-log.yml`.
     - For each entry where `persona_md_path` is not null: check if any keyword in `keywords[]` matches the user's intent.
     - **Match found:** (a) check if `<plugin-root>/<persona_md_path>` exists locally; (b) if yes, output: `cp <plugin-root>/<persona_md_path> ~/.claude/agents/<filename>`; (c) tell the user "Once installed, Claude Code will auto-invoke this agent for matching tasks." Do NOT dispatch the agent yourself.
     - **No match:** fall through to generic coach guidance and offer: "Run `workflow: domain-ingest domain: <detected-domain>` to synthesize a specialist for this domain."
  3. **`ingest-log.yml` missing or malformed** → skip the check, fall through to generic guidance.
  Invoked automatically by the CLAUDE.md routing fallback when no trigger keyword matched.
- `zoom-out` — Scope health check: are we still solving the right problem? Detects scope creep, goal drift, and solution-problem mismatch. Run when a build feels larger than the original spec, or when you suspect the original goal has shifted. Dispatches the `analysts/zoom-out.yml` analyst.
- `--quick` flag — Run the single most relevant analyst based on context

## Signal Scale

| Signal | Workflow quality meaning |
|--------|--------------------------|
| strong-accept | Excellent practice — doing this well |
| accept | Good, with minor improvements available |
| neutral | Mixed — doing some things well, others not |
| reject | Needs improvement — this pattern is costing efficiency |
| strong-reject | Anti-pattern detected — fix this before continuing |

## Analyst Output Schema

Every analyst returns exactly this JSON:
```json
{
  "signal": "strong-accept|accept|neutral|reject|strong-reject",
  "confidence": 0.0-1.0,
  "reasoning": "2-3 sentences on what's working and what isn't",
  "key_factors": [
    "specific improvement or confirmation",
    "specific improvement or confirmation",
    "specific improvement or confirmation"
  ]
}
```

`key_factors` must be actionable: not "context is high" but "Session is at ~280k tokens — rewind before the next complex build task to preserve synthesis quality."

---

## Usage Examples

```
/coach workflow-fit
About to fix a bug in the payment flow — should I use debug, build, or just edit inline?

/coach context-health
This session is 2 hours in, built the full auth module. Should I start a new session?

/coach pr-hygiene
Just opened a PR with 340 lines touching 8 files across auth and payment. Too large?

/coach agent-dispatch
I ran 3 agents sequentially when they could have been parallel. How often am I doing this?

/coach full-audit
Three builds today, all inline without think or plan first. Session at ~250k tokens.
```

## Orchestration Steps

### Step 0: Parse Arguments

- `mode` — if absent: run `workflow-fit` by default (most useful starting point)
- `--quick` — single-analyst mode
- `input` — description of the current session, task, or workflow you want evaluated. If no input: use the current conversation context as the subject.

### Step 1: Validation Gate (BP1)

Read `skills/coach/modes.yml`. Validate analyst YAMLs exist and have required fields.

### Step 2: Concurrency Guard (BP9)

Read `~/.dream-studio/coach/checkpoint.json`. If `status: "reviewing"`: offer Resume/Restart/Cancel.

### Step 3: Input Summary (BP8)

Summarize what's being evaluated:
- Current session state (approximate token count if known, what has been done)
- The specific workflow or decision being reviewed
- Any context about recent patterns or recurring issues

### Step 4: Dispatch Analyst Subagents

Standard dispatch pattern. Each analyst evaluates one dimension of workflow quality.

All analysts use the same 5-point signal scale. A `reject` from any analyst is a flag to address before continuing.

Validate responses (BP3). Write checkpoint after each wave.

For `zoom-out` mode: dispatch `analysts/zoom-out.yml`. It asks 5 scope-health questions against the current session context and returns a signal (strong-accept = scope clean, strong-reject = fundamental misalignment, stop and re-align with Director).

### Step 5: Quorum Check (BP2)

Coach uses low quorum (1-2) since modes are narrow. Short-circuit if single-analyst mode.

### Step 6: Scoring and Synthesis

Coach does not use the "any-reject" strategy — a reject on pr-hygiene doesn't block workflow-fit.

Instead: present each analyst's grade independently. Synthesize only if multiple analysts return contested signals on the same dimension.

### Step 7: Write Report

```markdown
# Coach Session: {mode} — {session_summary}
**Date:** {ISO-8601}

## Workflow Grades

| Dimension | Signal | Confidence |
|-----------|--------|------------|
| {analyst} | {signal} | {confidence} |

## Findings

{For each analyst:}
### {analyst-name}: {signal}
{reasoning}

**Actions:**
{key_factors as bulleted list}
```

Write to: `~/.dream-studio/coach/reports/coach-{mode}-{YYYY-MM-DD}.md`

### Step 8: Update State

Checkpoint: `status: "complete"`, `report_path`.
Feed `~/.dream-studio/feeds/coach.json`: increment `sessions_completed`, set `last_session`.

### Step 9: Present Results

1. **Grades table:** analyst → signal → one-line summary
2. **Top 3 actions:** the highest-priority improvements across all analysts
3. **Report path** for full detail

Keep presentation tight. Coach is meta — it shouldn't take longer than the work it's reviewing.

---

## Anti-patterns

- **Running coach instead of fixing** — coach identifies problems, it doesn't fix them. After running coach, go implement the changes.
- **Using coach for every session** — run it when something felt off, not as a ritual. If everything is green, that's information too — you're doing well.
- **Ignoring strong-reject signals** — a strong-reject from any analyst means stop and fix that pattern before continuing. Don't carry technical debt in your workflow.
- **Stale workflow-fit analyst** — after adding a new dream-studio skill, update `coach/analysts/workflow-fit.yml` skill list or the routing guidance will be wrong. See the comment at the top of that file.

---

