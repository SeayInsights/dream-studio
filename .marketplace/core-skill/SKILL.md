# dream-studio:core — Build Lifecycle

Complete build lifecycle: think → plan → build → review → verify → ship

---

## Mode: think

# Think — Design Before Building

## Before you start
Read `gotchas.yml` in this directory before every invocation.
If the project has `.planning/GOTCHAS.md` — read it before starting.
If the project has `.planning/CONSTITUTION.md` — read it before starting.

## Trigger
`think:`, `spec:`, `shape ux:`, `design brief:`, `research:`

## Purpose
Clarify the idea, explore approaches with trade-offs, write a spec, get Director approval. No code until approved.

## Scaling
- Config change → 1 paragraph summary
- Bug fix → problem statement + approach
- Feature → full spec with alternatives
- New system → architecture spec with diagrams

## Template

**Location**: `skills/think/templates/spec-template.md`

Use the spec template to structure your thinking. The template provides:
- **User Stories** — Prioritized scenarios (P1, P2, P3) that are independently testable
- **Functional Requirements** — FR-001, FR-002 format with "MUST" statements
- **Success Criteria** — Measurable outcomes (SC-001, SC-002)
- **Edge Cases** — Boundary conditions and error scenarios
- **Assumptions** — Explicit defaults when requirements are unclear

## Steps
1. **Clarify** — Restate what's being built and why. Surface assumptions. Ask Director if anything is unclear. If `.planning/CONSTITUTION.md` exists, read it before writing any spec — surface any conflicts with existing architectural decisions.

   **Clarify Questions** — Before writing the spec, ask 3-5 targeted questions to surface hidden constraints. Examples:
   - "Who is the primary user and what's their context when they hit this?"
   - "What's the definition of done — what does success look like in 30 days?"
   - "Are there constraints I should know about (performance, platform, existing patterns)?"
   - "What's explicitly out of scope for this?"
   - "Is there existing code/design I should read before speccing this?"
   Only ask questions where the answer would change the spec. Don't ask for its own sake.

1b. **Research Cache Check** — Before starting new research, check the persistent research cache:
   - Run `py scripts/research_cache.py get <topic>` (or call `hooks/lib/research_store.get_research(topic)`)
   - If cached AND not stale: display prior findings to Director. Ask: "Prior research exists (saved [date], confidence: [level]). Re-research or use existing?"
   - If cached AND stale: note "Prior research exists but is stale (refresh due [date]). Will re-research with prior findings as starting point."
   - If not cached: proceed normally — no prior research exists for this topic
   - This prevents re-researching the same topics across sessions

2. **Explore** — 2-3 approaches with trade-offs. Pros, cons, complexity, risk for each.

2b. **Source Quality Check** — After collecting research sources, validate quality:
   - Run `py scripts/source_ranker.py` on collected sources (or apply the scoring logic from `skills/domains/research/analysis.yml`)
   - Check: triangulation (3+ independent sources?), source tier distribution (any Tier 1?), counter-argument present?
   - If confidence < medium: flag gaps to Director before writing spec. "Research confidence is LOW — [specific gaps]. Collect more sources before speccing?"
   - If confidence >= medium: note confidence level in spec and proceed

3. **Recommend** — Pick one approach with rationale.

3b. **Risk Pre-population** — Before writing the Edge Cases section of the spec:
   - Run `py scripts/spec_risk_check.py <topic>` to scan gotchas.yml and prior session history
   - Incorporate relevant gotchas as suggested edge cases in the spec
   - If prior sessions encountered issues with this topic, note them in the spec's Assumptions section
   - This ensures specs learn from past mistakes instead of repeating them

4. **Spec** — Use `spec-template.md` to write to `.planning/specs/<topic>/spec.md` with:
   - User stories prioritized by value (P1 = MVP)
   - Functional requirements with FR-IDs
   - Success criteria with measurable metrics
   - Edge cases and assumptions
   - Chosen approach + why (can add Research section if needed)
5. **Approve** — Present spec to Director. Wait for explicit "go" before any code.

## Example Usage

```
Input: "think: Add user authentication"

Output: .planning/specs/user-auth/spec.md
- User Story 1 (P1): Email/password login
- User Story 2 (P2): Password reset
- User Story 3 (P3): OAuth integration
- FR-001: System MUST hash passwords with bcrypt
- SC-001: 95% of users complete login in <30 seconds
```

## Output
Spec document at `.planning/specs/<topic>/spec.md`. Director approval in conversation.

For complex features (new systems, cross-cutting changes, or anything requiring architecture decisions), also output a design document:
- Use `templates/design-template.md`
- Write to `.planning/specs/<topic>/design.md`
- The design doc covers architecture decisions, component breakdown, and integration points — separate from the requirements in spec.md

## Next in pipeline
→ `plan` (break spec into executable steps)

## Anti-patterns
- Writing code before spec is approved
- Spec with only one approach (always explore alternatives)
- Spec longer than the implementation would be
- Asking Director to make every technical decision (recommend, let them override)

---

## Mode: plan

# Plan — Break Spec Into Steps

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Imports
- core/git.md — branch operations
- core/traceability.md — traceability file structure, when to activate
- core/format.md — task list format, requirements matrix, summary table

## Trigger
`plan:`, or after `think` spec is approved

## Purpose
Break an approved spec into executable steps with dependencies, order, and acceptance criteria.

## Templates

**Locations**: 
- `skills/plan/templates/plan-template.md` — Implementation strategy and architecture
- `skills/plan/templates/tasks-template.md` — Atomic task breakdown with dependencies

Use these templates to structure your plan:
- **Plan template** provides: Technical context, project structure, complexity tracking, requirements traceability
- **Tasks template** provides: Phase-based organization, [P] parallel markers, user story grouping, dependency chains

## Steps
1. **Read spec** — Reference the approved spec from `think`. Confirm scope, user stories, and requirements.
2. **Plan architecture** — Use `plan-template.md` to document technical decisions, structure, and approach.
3. **Decompose** — Use `tasks-template.md` to break into atomic tasks. Each task = one logical commit.
4. **Organize by user story** — Group tasks so each user story (P1, P2, P3) can be implemented and tested independently.
5. **Order** — Dependencies first. Mark [P] for tasks that can run in parallel (different files, no dependencies).
6. **Acceptance** — Each task gets acceptance criteria that can be verified without judgment.
7. **Assess traceability need** — See Traceability section below.
8. **Write plan** — Output to `.planning/specs/<topic>/plan.md`
9. **Write tasks** — Output to `.planning/specs/<topic>/tasks.md`
9b. **Persist to DB** — Call `upsert_spec()` and `upsert_task()` from `hooks/lib/studio_db.py` for each spec and task. This enables cross-project task queries and blocked-task tracking.
10. **Write traceability registry** — If traceability is active, output to `.planning/traceability.yaml`
11. **Auto-issues (optional)** — If Director approves, generate GitHub issues from the task list:
    - Run `gh issue create --title "<task description>" --body "**Acceptance:** <acceptance criteria>\n\n**Spec:** .planning/specs/<topic>/spec.md"` for each task in tasks.md
    - After creation, update tasks.md to add the issue number as a tag: `[#42]` after the task ID
    - This links plan tasks to trackable GitHub issues for visibility outside the session
    - Skip if: prototype work, personal project without a GitHub remote, or Director declines

## Traceability

**See:** core/traceability.md — Traceability file structure, status lifecycle, when to activate

**Decision criteria:**
- Activate if: 4+ tasks, distinct requirements, user request, or audit trail needed
- Skip if: 3 or fewer tasks, prototype work, or single-file bug fix

**When active:** Create `.planning/traceability.yaml` and include Requirements table in plan
**When inactive:** Use simplified plan format, do NOT create traceability.yaml

## Plan format — Full (traceability active)

**See:** core/format.md — Requirements matrix, numbered task list, summary table

Include: Requirements table with TR-IDs, task list with "Implements" field, summary table with TR-ID column

## Plan format — Lite (traceability inactive)

**See:** core/format.md — Numbered task list, summary table

Include: Task list without "Implements" field, summary table without TR-ID column
| 2 | ... | 1 | medium |
```

## Example Usage

```
Input: "plan: user-auth" (after approved spec)

Output: .planning/specs/user-auth/
├── plan.md — Technical context, React 19 + Cloudflare Workers + D1
├── tasks.md — 16 tasks organized by user story
│   Phase 2: Foundational (T001-T003)
│   Phase 3: User Story 1 - Email/Password (T004-T008) ðŸŽ¯ MVP
│   Phase 4: User Story 2 - Password Reset (T009-T012)
│   Phase 5: User Story 3 - OAuth (T013-T016)

Tasks use [P] markers for parallelization:
- T004 [P] [US1] Create User model in src/models/user.ts
- T005 [P] [US1] Create Session model in src/models/session.ts
- T006 [US1] Implement AuthService (depends on T004, T005)
```

## Output
- Plan document at `.planning/specs/<topic>/plan.md` (always)
- Tasks document at `.planning/specs/<topic>/tasks.md` (always)
- Traceability registry at `.planning/traceability.yaml` (only when traceability active)

## Next in pipeline
→ `build` (execute the plan)

## Anti-patterns
- Tasks too large (multiple unrelated changes in one task)
- Missing acceptance criteria
- No dependency ordering
- Plan that doesn't cover the full spec
- Traceability active but requirements lack TR-IDs (breaks the chain)
- Traceability active but tasks not tagged with TR-IDs (orphaned work)
- Activating traceability for a 2-task bug fix (overhead without value)

---

## Mode: build

# Build — Execute With Discipline

## Before you start
Read `gotchas.yml` in this directory before every invocation.
If the project has `.planning/GOTCHAS.md` — read it before starting.
If the project has `.planning/CONSTITUTION.md` — read it before starting.

## Pre-flight Intelligence
Before dispatching any task, query the registry for relevant context:
1. **Gotcha check** — `get_gotchas_for_skill('core:build')` from `hooks/lib/studio_db.py` (falls back to file-walk via `gotcha_scanner.py` if registry not populated). Show top 3 most recent gotchas as "Pre-flight: 3 recent gotchas for [skill]" — informational only, doesn't block.
2. **Approach history** — `get_best_approaches('core:build')` from `hooks/lib/studio_db.py`. Surface proven approaches: "Prior sessions show [approach] worked [N]% of the time." Use this to inform dispatch strategy (parallel vs sequential, model choice).

## Imports
- core/git.md — commit formatting, diff reading, branch operations
- core/traceability.md — TR-ID validation and updates
- core/quality.md — build commands, test execution
- core/orchestration.md — subagent spawning, model selection, review loops
- core/format.md — checkpoint format, task progress

## Trigger
`build:`, `execute plan:`, or after `plan` is complete

## Core Principles
- Fresh subagent per task — never inherit session history
- Controller stays lean — delegates heavy lifting, preserves own context
- Two-stage review after each task (spec then quality)
- Pre-inline context — don't make agents Read files, provide full text

## Execution Modes

### Simple mode (≤3 tasks, tightly coupled)
Execute directly in the current session. One task at a time, commit after each.

### Subagent mode (≥4 tasks or independent tasks)
Dispatch fresh subagent per task with isolated context.

**Why subagents:** They get only task-specific state — no session history, no conversation baggage. This preserves your own context for coordination while ensuring each agent stays focused.

## The Process

### Step 0: Load plan and project context

**Pre-flight Gotcha Briefing** — Before loading the plan, surface the 3 most recently added gotchas relevant to this build:
1. Run `hooks/lib/gotcha_scanner.py` → `get_recent_gotchas(limit=3)` for the skills involved in this plan
2. Display each gotcha as: `[severity] gotcha-id — title`
3. This is informational only — does not block the build
4. Purpose: recently-added gotchas reflect the latest lessons learned; surfacing them here prevents repeating recent mistakes

If `.planning/GOTCHAS.md` exists, read it now. If `.planning/CONSTITUTION.md` exists, read it now. These contain known failure patterns and architectural decisions that must constrain every task in the build.
Read the plan file ONCE. Extract ALL tasks with full text. Don't re-read the plan per task.

**⛔ STOP gate:** If the project has 5+ files AND `.planning/CONSTITUTION.md` or `.planning/GOTCHAS.md` are missing — STOP. Run `dream-studio:harden` first to scaffold these files. A build without a constitution is building blind.

### Step 1: Dependency analysis
**See:** core/orchestration.md — Dependency analysis for parallel execution

Group tasks into waves based on dependencies. Independent tasks within a wave MAY run as parallel subagents IF they touch different files.

### Step 2: Execute each task

**For each task (subagent mode):**

1. **Dispatch implementer** — Use prompt template below. Provide:
   - Full task text (pasted, not a file path)
   - Scene-setting context (where task fits, dependencies, architecture)
   - Working directory
   - Any decisions made so far

2. **Handle implementer response** — See: core/orchestration.md — Handling agent responses
   - `DONE` → proceed to review
   - `DONE_WITH_CONCERNS` → read concerns, address if correctness/scope, then review
   - `NEEDS_CONTEXT` → provide missing info, re-dispatch
   - `BLOCKED` → assess and re-dispatch or escalate

3. **Spec compliance review** — See: core/orchestration.md — Review loop pattern
   - Dispatch reviewer with task spec + implementer report
   - Must pass before code quality review
   - If issues: implementer fixes → re-review → repeat until ✅

4. **Code quality review** — See: core/orchestration.md — Review loop pattern
   - Dispatch reviewer with diff (base..head SHA) + task summary
   - Only after spec compliance passes
   - If issues: implementer fixes → re-review → repeat until ✅

5. **Commit** — See: core/git.md — Commit referencing plan task
   - With TR-IDs: `feat(task-3): implement login form [TR-001, TR-002]`
   - Without TR-IDs: `feat(task-3): implement login form`

6. **Update traceability** (conditional) — See: core/traceability.md — Update TR-ID with commit
   - Check if `.planning/traceability.yaml` exists
   - If exists: validate → update commits + status → re-validate
   - If doesn't exist or invalid: skip

7. **Mark complete** — Write proof to disk (task status in plan file or state file). Call `update_task_status()` from `hooks/lib/studio_db.py` with the commit SHA to track completion in the DB.

### Step 3: Checkpoint
**See:** core/format.md — Checkpoint format

After every 3 tasks or 30 minutes (whichever first), output checkpoint with:
- Tasks completed / total
- Any drift from plan
- Blockers or concerns
- Context usage (if growing, consider handoff)

## Model Selection for Subagents

**See:** core/orchestration.md — Model Selection

Use Haiku for mechanical tasks, Sonnet for integration, Opus for architecture/design/review.

## Compiled Prompt Pattern (preferred when available)

Before spawning implementer agents, use the compiled prompt pipeline if scripts exist:

1. **Generate static context:** `py hooks/lib/context_compiler.py --skill=build --pack=core [--repo-context=<path>]`
2. **Assemble prompt:** `py hooks/lib/prompt_assembler.py --template=implementer --static-context=<compiled.md> --task-text="<task>"`
3. Use the assembled output as the agent's prompt

The compiled prompt produces a byte-identical static prefix across all tasks in a wave, enabling Claude prompt cache hits. If either script is unavailable or errors, fall back to the standard template below.

For reviewers: use `--template=reviewer`. For exploration: use `--template=explorer`.

## Implementer Prompt Template

**See:** core/orchestration.md — Implementer prompt template

Use the standard template with:
- Full task text (pasted, never a file path)
- Scene-setting context
- Expected output format (DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT)

## Drift detection
- **Minor drift** (variable name, slight approach change) → note it, continue
- **Major drift** (new dependency, scope change, architecture change) → STOP. "Drift detected: [what and why]. Adjust plan or revert?"

## Phase-locked transitions
Each task only advances after writing proof to disk. If context fills mid-task, the handler can checkpoint state and the next session resumes from the last proven task.

## Next in pipeline
→ `review` (quality check the completed work)

## Anti-patterns

| ❌ Wrong | ✅ Correct |
|---|---|
| Skipping spec compliance ("it compiles, ship it") | Always run spec compliance review before code quality review |
| Committing multiple tasks in one commit | One task = one commit with task ID in message |
| Continuing past major drift without approval | STOP and surface drift: "Drift detected: [what/why]. Adjust or revert?" |
| Giving subagents a file path to read | Paste full text inline in the dispatch prompt |
| Dispatching parallel agents that touch the same file | Check file ownership — shared files require sequential tasks |
| Ignoring subagent escalations or concerns | Read every `done_with_concerns` — address correctness issues before review |
| Skipping spec compliance and jumping to code quality | Spec compliance must pass first — in that order, always |
| Accepting "close enough" on spec compliance | Either it meets the acceptance criterion or it doesn't — no partial credit |
| Starting a build without CONSTITUTION.md on a 5+ file project | Run dream-studio:harden first to scaffold project constitution |

---

## Mode: review

# Review — Two-Stage Quality Check

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Imports
- core/git.md — read git diff, get commit SHA
- core/quality.md — OWASP security checks, test coverage
- core/orchestration.md — subagent review pattern, reviewer prompt template
- core/format.md — severity-tagged findings, review findings format, verdict statement

## Trigger
`review:`, `review commits`, `review code`, `review PR:`, or after `build` completes

## Core Principle
Spec compliance BEFORE code quality. Always. Catching "built the wrong thing" matters more than "code smells."

## Stage 1: Spec Compliance Review

**Purpose:** Did we build what was requested — nothing more, nothing less?

1. Re-read the plan/spec
2. Compare implementation to requirements line by line
3. Check for:
   - **Missing requirements** — things requested but not built
   - **Extra work** — things built but not requested (over-engineering)
   - **Misunderstandings** — right feature, wrong interpretation

**Do NOT trust self-reports.** Read the actual code. Compare to the actual spec.

```
✅ Spec compliant — all requirements met, nothing extra
❌ Issues: [list what's missing/extra with file:line references]
```

**Stage 1 must pass before moving to Stage 2.** If spec issues exist, fix them first.

## Stage 2: Code Quality Review

**Purpose:** Is the implementation well-built?

1. **Scope check** — Does the code match the plan/spec? Flag anything extra.
2. **Correctness** — Logic errors, edge cases, race conditions, null handling.
3. **Security** — OWASP Top 10 scan:
   - Injection (SQL, command, XSS)
   - Broken auth / session management
   - Sensitive data exposure
   - Missing access control
   - Security misconfiguration
   - Vulnerable dependencies
4. **Test coverage** — Are critical paths tested? Edge cases covered?
5. **Code quality** — Readability, naming, duplication, complexity.
6. **File responsibility** — Each file has one clear job with a well-defined interface?

## Fast scan mode
When invoked with Haiku for fast scan:
1. Scan for: secrets, debug leftovers, obvious bugs, missing error handling
2. Output: `FAST SCAN: CLEAN` or `FAST SCAN: FINDINGS` with bullet list

## Subagent review (for larger changes)

**See:** core/orchestration.md — Review loop pattern, reviewer prompt template

Dispatch spec reviewer first, then code quality reviewer after spec passes. Review loops continue until all issues resolved.

Each reviewer returns a JSON object matching the schema in core/orchestration.md:
```json
{
  "signal": "compliant | non_compliant",
  "confidence": 0.0-1.0,
  "summary": "One sentence verdict",
  "issues": [
    {
      "requirement": "the requirement from spec",
      "issue": "what is wrong",
      "location": "file:line",
      "fix": "specific, actionable fix"
    }
  ]
}
```
Parse `result.signal`: `compliant` → next stage. `non_compliant` → re-dispatch implementer with `result.issues`.

## Findings format

**See:** core/format.md — Review findings format

Use two-stage format: Stage 1 (spec compliance) → Stage 2 (code quality with severity tags) → Summary with verdict
```

## Next in pipeline
→ `verify` (if clean) or back to `build` (if findings need fixing)

## Anti-patterns
- Reviewing without reading the spec/plan first
- Skipping Stage 1 (spec compliance) and jumping to code quality
- "Looks good" with no specific findings listed
- Flagging style preferences as High severity
- Skipping security checks because "it's internal"
- Trusting self-reports instead of reading the code
- **Acting on stale findings (L1)** — before fixing any finding from a review report, verify
  it still exists: grep or read the file. Reports go stale within hours of being written.
- **Leaving findings unannotated after fixing (L5)** — after each finding is resolved, add
  `[FIXED: <commit-sha>]` inline in the review report. An unmarked report misleads the next
  session into re-fixing already-resolved issues.

---

## Mode: verify

# Verify — Prove It Works

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Imports
- core/git.md — get commit SHA
- core/traceability.md — update TR-ID with test, coverage reporting
- core/quality.md — run build, run tests, evidence patterns
- core/format.md — evidence statement, coverage report, checkbox list

## Trigger
`verify:`, `prove it:`, or after `review` passes clean

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE
```

If you haven't run the verification command in THIS message, you cannot claim it passes.

## The Gate (run this every time)

```
BEFORE claiming any status:
1. IDENTIFY — What command proves this claim?
2. RUN — Execute the FULL command (fresh, complete)
3. READ — Full output, check exit code, count failures
4. VERIFY — Does output confirm the claim?
   - NO → State actual status with evidence
   - YES → State claim WITH evidence
5. ONLY THEN — Make the claim
```

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| Tests pass | Test command output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check, extrapolation |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Bug fixed | Reproduce original symptom: passes | Code changed, assumed fixed |
| Regression test works | Red-green cycle verified | Test passes once |
| Agent completed task | VCS diff shows changes | Agent reports "success" |
| Requirements met | Line-by-line checklist | Tests passing |

## Red Flags — STOP immediately

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Done!")
- About to commit/push/PR without running verification
- Trusting agent success reports without independent check
- Relying on partial verification
- Thinking "just this once"

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the verification |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "Linter passed" | Linter ≠ compiler ≠ runtime |
| "Agent said success" | Verify independently |
| "Partial check is enough" | Partial proves nothing |

## Steps
1. **Identify targets** — See: core/traceability.md — Use TR-IDs if exists, else plan acceptance criteria
2. **Run the app** — See: core/quality.md — Run build, start dev server
3. **Golden path** — Test primary user flow end-to-end
4. **Edge cases** — Test boundaries, empty states, error states, invalid input
5. **Evidence** — See: core/format.md — Evidence statement format
   - Capture: screenshots (UI), logs (API), terminal output (CLI)
6. **Regression** — Does existing functionality still work?
7. **Update traceability** — See: core/traceability.md — Update TR-ID with test

## Evidence patterns

**See:** core/quality.md — Evidence patterns

Must follow format: `[Action] → [Observation] → [Conclusion]`

✅ Re-read plan → Create checklist → Verify each → Report gaps or completion
❌ "Tests pass, phase complete"

✅ Agent reports success → Check VCS diff → Verify changes → Report actual state
❌ Trust agent report
```

## Verification by domain
- **Web/SaaS** — Run `npm run test:e2e` if Playwright exists. Otherwise open browser, test forms, responsive, a11y.
   - **Design quality scan:** Run `npx impeccable detect` against the project to check for anti-pattern violations. Reports 24 design issues without requiring AI. Fix any violations before claiming UI is clean.
   - **React/Next.js deep verification** (when project uses React/Next.js and app is running):
     - `next-browser snapshot` — confirm key components rendered, no missing nodes
     - `next-browser accessibility` — surface ARIA violations, missing labels, contrast failures
     - `next-browser profile` — check Core Web Vitals: LCP < 2.5s, CLS < 0.1, INP < 200ms
     - `next-browser click <selector>` / `next-browser fill <selector> <value>` — exercise key user paths interactively
     Start the daemon first if not running: `next-browser start`
- **API** — Hit endpoints, verify response shape and status codes.
- **Game** — Run scene via godot-mcp, check QA stdout events.
- **Power Platform** — Test in preview mode, verify data connections.
- **MCP server** — Call each tool, verify response format and error handling.

## Output
```
## Verification: [feature]
Date: YYYY-MM-DD

### Golden path
- [step]: PASS / FAIL — [evidence: command output or screenshot]

### Edge cases
- [case]: PASS / FAIL — [evidence]

### Regression
- [area]: PASS / FAIL — [evidence]

### Verdict: VERIFIED / FAILED ([details])
```

## Bug Fix Verification (red-green cycle)

When verifying a fix that came through `debug` → `fix-issue` workflow AND debug Step 1.5 produced a test file:

1. **Red** — Run the failing test BEFORE confirming the fix is applied. Confirm it fails (exit non-zero).
2. **Confirm fix applied** — `git diff` shows the fix is present.
3. **Green** — Run the same test. Confirm it passes (exit 0).
4. **Regression** — Run the full test suite. Confirm no new failures introduced.

Evidence format: `[test name] pre-fix → FAIL (exit 1) | post-fix → PASS (exit 0)`

If debug Step 1.5 produced a screenshot/log instead of a test (non-unit-testable bug), use the screenshot/log as reproduction evidence and verify the symptom is gone via golden-path verification instead.

## Next in pipeline
→ `ship` (if deploying) or done

## Anti-patterns
- "I tested it mentally" — no evidence
- Only testing the golden path
- Skipping regression checks
- Claiming verification without running the app
- ANY wording implying success without having run verification

---

## Mode: ship

# Ship — Pre-Deploy Gate

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Imports
- core/git.md — check for uncommitted changes, pre-push validation
- core/quality.md — quality gate checklist (audit, harden, optimize, test), pre-push local validation
- core/format.md — ship gate format, verdict statement

## Trigger
`ship:`, `pre-deploy:`, `deploy:`, or before any deployment command

## Purpose
Blocks deployment until all checks pass. No exceptions.

## Gate checklist

**See:** core/quality.md — Quality gate checklist

Run all four gates: Audit (a11y, perf, technical), Harden (error/empty/loading states), Optimize (bundle, rendering, animation, images), Test (Playwright, suite, browser, regression)

## Frontend projects — Core Web Vitals gate

For projects with a frontend, add this check to the Audit gate before shipping:

```bash
next-browser profile
```

Pass thresholds (Google's "Good" tier):
- **LCP** (Largest Contentful Paint) < 2.5s
- **INP** (Interaction to Next Paint) < 200ms  
- **CLS** (Cumulative Layout Shift) < 0.1

Any metric above threshold = BLOCKED. Fix the performance issue and re-run before deploy.
Start daemon first if not running: `next-browser start`

## Gate result

**See:** core/format.md — Ship gate format

Output gate result with PASS/FAIL for each category and final verdict (CLEAR TO SHIP / BLOCKED)

## Pre-push local validation (L3)

**See:** core/quality.md — Pre-push local validation

Run: `npm run lint && npx tsc --noEmit && npm run build`
```
All three must exit 0. If any fail, fix locally — do not push a broken state.

## Rules
- Any FAIL blocks deployment
- Director can override a FAIL with explicit approval (logged)
- After fix, re-run the failed check — don't skip re-verification
- This gate runs in the main session, not in a sub-agent
- **Never downgrade lint/TS rules to pass CI (L2).** If lint has errors, fix the errors.
  Downgrading `"error"` → `"warn"` is only acceptable with an inline comment explaining why
  and an immediate follow-up task. CI green ≠ code healthy.
- **Verify CI steps exist locally before adding them (L4).** Before adding any step to a
  CI pipeline, run the command locally. If it exits non-zero or finds no files, do not add
  it — create the prerequisite first or omit the step.

## Post-ship archive

After a successful deploy, archive the spec to prevent .planning/specs/ from accumulating indefinitely:

1. Copy `templates/archive-stamp-template.md` to `.planning/specs/<topic>/archive-stamp.md`
2. Fill in: status (shipped), shipped_date, merge_sha, pr_url, summary
3. Move the entire `.planning/specs/<topic>/` folder to `.planning/archive/<topic>/`
4. Commit: `chore: archive <topic> spec post-ship`

This keeps .planning/specs/ clean — only in-progress specs live there.

---

## Mode: handoff

# Handoff — Session Continuity

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`handoff:`, auto-triggered by `on-context-threshold` at compact threshold, or when session is ending with work in progress

## Purpose
Capture the minimum context needed for the next session to continue without re-explanation. Write BOTH human-readable markdown AND machine-parseable JSON for programmatic recovery.

## Steps
1. **Current task** — What plan is being executed? Which task number? What step within that task?
2. **Phase** — Where in the pipeline? (think / plan / build / review / verify / ship)
3. **Progress** — What's done, what's in progress, what's not started?
4. **State** — What's working? What's broken? Any pending Director decisions?
5. **Files** — Which files are actively being touched?
5b. **Lessons & Gotcha Tracking** — Review the session for learnings:
   - **Lessons**: List any Director corrections, approach changes, or surprises as `lessons_this_session` entries
   - **Gotcha hits**: For each gotcha that was consulted or whose advice was followed during the session:
     - Add its ID to the `gotchas_hit` array (e.g., "parallel-same-file", "spec-before-constitution")
     - This includes: pre-flight gotcha briefings that changed your approach, gotchas from spec_risk_check that informed edge cases, or gotchas you recalled while debugging
     - Only log gotchas that actually influenced behavior — not every gotcha that was displayed
   - This creates a feedback loop: gotchas that frequently fire are proven valuable; gotchas that never appear in handoffs after 90 days get flagged by self-audit for removal
6. **Write to DB (primary)** — Call `insert_handoff()` and `insert_session()` from `hooks/lib/studio_db.py` with the structured handoff data. Register the project via `upsert_project()` if not already present. Mark the previous session's handoff as consumed via `mark_handoff_consumed()`.
6b. **Write both files** — markdown + JSON to `.sessions/YYYY-MM-DD/`. For `project_root` in the JSON, use the absolute path of the current working directory (the project root, not a subdirectory).
7. **Auto-draft** — After writing both files, scan the "What's broken / blocked" section for items that have an identified root cause — specifically patterns that are non-obvious and would recur in future sessions. If found: write a draft lesson to `meta/draft-lessons/YYYY-MM-DD-<topic>.md` with:
   - `Source: auto-harvest (handoff)`
   - `Confidence: medium` (root cause is identified but not yet validated by outcome)
   - Fill "What happened" from the blocked item, "Lesson" from the root cause, "Evidence" from the handoff context
   If "What's broken / blocked" is empty or all items lack root causes: skip silently.
8. **Print** — Print the handoff file path so Director can pass it to the next session

## Markdown output: `.sessions/YYYY-MM-DD/handoff-<topic>.md`
```markdown
# Handoff: [topic]
Date: YYYY-MM-DD

## Resume command
Read [plan path] — resume at Phase [N], Task [N.N]

## Current state
- Plan: [path to plan file]
- Pipeline phase: [think|plan|build|review|verify|ship]
- Current task: [task number + name]
- Progress: [X of Y tasks complete]
- Branch: [git branch name]
- Last commit: [short SHA + message]

## What's working
- [item]

## What's broken / blocked
- [item]: [detail]

## Pending decisions
- [decision needed]: [context]

## Active files
- [file path]: [what's being done to it]

## Lessons this session
- [correction or surprise]: [what was learned]

## Gotchas hit
- [gotcha-id]: [how it helped avoid an error]

## Next action
[Exact next thing to do — specific enough that a fresh session can start immediately]
```

## JSON output: `.sessions/YYYY-MM-DD/handoff-<topic>.json`
```json
{
  "topic": "feature-name",
  "date": "YYYY-MM-DD",
  "project_root": "/absolute/path/to/project",
  "plan_path": "docs/plans/plan-file.md",
  "pipeline_phase": "build",
  "current_task_id": "3.2",
  "current_task_name": "Wire up API endpoint",
  "tasks_completed": 5,
  "tasks_total": 12,
  "branch": "feat/feature-name",
  "last_commit": "abc1234",
  "working": ["auth flow", "database schema"],
  "broken": [{"item": "test suite", "detail": "2 failures in auth.test.ts"}],
  "pending_decisions": [{"decision": "cache strategy", "context": "Redis vs in-memory"}],
  "active_files": ["src/api/auth.ts", "src/lib/cache.ts"],
  "next_action": "Fix auth.test.ts failures, then continue task 3.3",
  "lessons_this_session": [{"lesson": "description", "source": "what triggered it"}],
  "gotchas_hit": ["gotcha-id-1", "gotcha-id-2"],
  "approaches_taken": [
    {"skill": "core:build", "approach": "parallel subagents for wave 1", "outcome": "success", "why": "3 independent tasks, no shared files"},
    {"skill": "quality:debug", "approach": "trace render pipeline end-to-end", "outcome": "correction", "why": "Director corrected: always check SSOT first"}
  ]
}
```

## Recovery state machine
The JSON handoff enables programmatic resume:
1. New session reads JSON → knows exact phase, task, branch
2. Checks out correct branch
3. Reads plan file at `plan_path`
4. Skips completed tasks (by `current_task_id`)
5. Resumes at `next_action`
6. Scans lessons_this_session for patterns worth promoting to gotchas.yml or memory

No re-reading conversation history. No orientation. Immediate productive work.

## Approach Capture
Before writing the handoff files (step 6):

1. **Record approaches** — For each skill invoked this session, add an entry to the `approaches_taken` array in the JSON output. Record: skill ID, approach description, outcome (success/failure/partial/correction), and why it worked or didn't.
2. **Persist to DB** — Call `capture_approach(skill, approach, outcome, context, why)` from `hooks/lib/studio_db.py` for each entry. This persists to SQLite for cross-session pattern detection.
3. **On resume** — When starting from a handoff, query `get_best_approaches(skill_id)` from `hooks/lib/studio_db.py` for skills about to be used. Surface proven approaches: "Prior sessions show [approach] worked [N]% of the time."

## Context pressure triggers
When context is growing large:
- If in `build` phase with independent remaining tasks → dispatch subagents (they get fresh context)
- If mid-task → complete current task, commit, then handoff
- Never handoff mid-edit — always reach a committed checkpoint first

## Rules
- **Targeted payload, not brain dump** — only what's needed to resume
- Write to `.sessions/YYYY-MM-DD/` — create directory if needed
- Always write BOTH .md and .json files
- The "Resume command" field is the single line the next session needs
- A fresh session should be able to resume using ONLY the handoff file
- Auto-draft triggers only on non-obvious root causes in "What's broken" — not every blocked item qualifies
- Auto-drafts are flagged `Source: auto-harvest (handoff)` and require Director approval before promotion

---

## Mode: recap

# Recap — Build Memory Capture

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`recap:`, `session recap:`, or auto-triggered after substantive builds

## Purpose
Record what happened in a build so future sessions and the Improvement Loop (Engine 2) have context.

## When to trigger
- After any build that created or modified 3+ files
- After any multi-task plan execution completes
- Before ending a session with significant work done
- On Director request

## Steps
1. **Gather** — What was built? Which files changed? What commits were made?
2. **Decisions** — What decisions were made during the build and why?
3. **Risks** — What risk flags were raised? What was deferred?
4. **Stack** — What technologies/patterns were used?
5. **Remaining** — What's left undone? What's the logical next step?
6. **Write to DB (primary)** — Call `end_session()` from `hooks/lib/studio_db.py` to update the session record with outcome, token counts, and tasks completed. Call `capture_approach()` for each notable approach.
6a. **Write file** — Output to `.sessions/YYYY-MM-DD/recap-<topic>.md`
6b. **Micro-capture** — Append a summary line to the daily capture file using `hooks/lib/micro_capture.py`:
   - Call: `append_capture(skill='recap', outcome='<pass|correction>', note='<one-line summary of what was built>')`
   - Use `outcome: correction` if any Director corrections or approach overrides were noted in the Decisions section
   - Use `outcome: pass` otherwise
   - The note should be a single sentence capturing the most important thing from this session
   - This feeds the daily learning pipeline — daily harvest reads these micro-captures
7. **Auto-draft** — After writing the recap file, scan what was captured for:
   - Any Director correction or approach override during the session
   - Any "Risk flags" entry that has an identified root cause (not just "risk exists" but "why it happened")
   If found: write a draft lesson to `meta/draft-lessons/YYYY-MM-DD-<topic>.md` using the standard draft lesson format, with:
   - `Source: auto-harvest (recap)`
   - `Confidence: high` (session context is still active — this is the richest capture moment)
   - Pre-fill "What happened", "Lesson", "Evidence", and "Applies to" from the recap content
   If nothing qualifies: skip silently — do not create an empty draft file.

## Output format
```markdown
# Recap: [topic]
Date: YYYY-MM-DD
Session: [session context if available]

## What was built
- [file/feature]: [what changed]
- Commits: [list of commit hashes + messages]

## Decisions
- [decision]: [rationale]

## Risk flags
- [risk]: [status — mitigated / deferred / open]

## Stack / patterns used
- [technology or pattern]: [how it was applied]

## Remaining work
- [task]: [status — not started / partial / blocked on X]

## Next step
[The single most logical next action for the next session]
```

## Approach Capture
After writing the recap (step 6) and before auto-draft (step 7):

1. **Query prior approaches** — Run `get_best_approaches(skill_id)` (from `hooks/lib/studio_db.py`) for each skill used this session. Surface patterns: "Past sessions show [approach] worked [N]% of the time for [skill]."
2. **Capture this session's approaches** — For each skill invoked this session, call `capture_approach(skill, approach, outcome, context, why)` from `hooks/lib/studio_db.py`. Focus on:
   - Corrections (Director overrode your approach)
   - Surprising outcomes (unexpected success or failure)
   - Notable approaches (parallel dispatch, specific debug strategy, etc.)
   Skip routine successes unless the approach itself was notable or new.

## Rules
- Write to `.sessions/YYYY-MM-DD/` — create directory if needed
- Be specific: file paths, commit hashes, decision rationale
- Keep it concise — this is a structured record, not a narrative
- The "Next step" field is critical — it's what the next session reads first
- Auto-drafts are flagged `Source: auto-harvest (recap)` — Director still decides whether to promote them
- Never create a draft lesson file if no correction or root-cause risk was captured — empty drafts pollute the backlog

---

## Mode: explain

# Explain — Trace How It Works

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`explain:`, `how does X work`, `walk me through`, `what is this doing`, `why does X behave like Y`

## Purpose
Trace a system, feature, or piece of code from its entry point through its layers to its output.
Not a line-by-line code reading — a structural explanation of WHY it's built this way.

## Scaling
- Single function → one paragraph + file:line reference
- Feature / module → layered explanation (entry → logic → output)
- System / architecture → component map with data flow

## Steps
1. **Identify entry point** — Where does the thing start? (function call, route, trigger, event)
2. **Trace 1-3 hops** — Follow the call chain. Read only the files you land on — no speculative reads.
3. **Identify SSOT** — For each layer, name the file that owns that behavior.
4. **Explain WHY, not WHAT** — Focus on design decisions, constraints, and invariants. The code already shows what; explain why it's structured that way.
5. **Offer depth** — After the first explanation, ask: "Want to go deeper on any layer, or a different angle?"

## Depth levels
- **Surface** (default): Entry point + 2 hops + purpose of each layer
- **Deep**: Full call chain + key decisions at each hop
- **Architecture**: Component map, data flow, boundaries, trade-offs

## Output format
```
## [Topic]: How X works

**Entry point**: `file:line` — [one-line description]

**Layer 1 — [name]**: `file:line`
[2-3 sentences: what this layer does, why it exists, what constraint it handles]

**Layer 2 — [name]**: `file:line`
[2-3 sentences]

**Output**: [what comes out and where it goes]

**Key design decision**: [the non-obvious thing — why this approach vs. alternatives]
```

## Rules
- Never read a file speculatively — only read what you land on in the trace
- Never explain line-by-line — explain layers and decisions
- Never claim to know something you didn't trace — say "I didn't follow that branch"
- Max 3 hops by default unless Director asks deeper

## Next in pipeline
→ `debug` (if explaining to diagnose a problem)
→ `think` (if explaining to inform a design decision)

## Anti-patterns
- Reading every file in a directory to "understand the codebase"
- Line-by-line code narration
- Explaining WHAT the code does without explaining WHY
- Going more than 3 hops without checking if Director wants that depth

---

