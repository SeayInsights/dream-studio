# Token-Efficient Prompting Guide

**Goal:** Get better results while using 40-70% fewer tokens.

**Core principle:** Specificity reduces exploration. Vague prompts trigger broad context gathering. Specific prompts enable narrow execution.

---

## Quick Wins

### ❌ Token-Wasteful
```
"explore this repo"
"investigate this codebase"
"check this out"
"design something"
"fix this"
```
**Why wasteful:** I don't know what you need, so I read broadly and build full context.

### ✅ Token-Efficient
```
"Read README + SKILL.md, tell me: what does this do, does it have X feature?"
"Grep for error handling patterns in src/, summarize approach"
"Brand: Linear (logo + colors only, skip design direction)"
"Design: landing page, Pentagram style, no other options"
"Debug: auth failing on /login POST, check middleware first"
```
**Why efficient:** I know exactly what you need, read only relevant files, execute narrowly.

**Savings:** 40-60% fewer tokens on average

---

## The Specificity Ladder

### Level 0: Vague (Highest Token Cost)
```
"Make this better"
"Design something cool"
"Fix the bug"
```
**What happens:** I explore everything, ask clarifying questions, build broad context.  
**Token cost:** 100% (baseline)

### Level 1: Directional (60% Cost)
```
"Improve performance"
"Design a landing page"
"Fix the login bug"
```
**What happens:** I narrow domain but still explore options.  
**Token cost:** 60% (moderate exploration)

### Level 2: Specific (30% Cost)
```
"Reduce bundle size by code-splitting routes"
"Design landing page in Pentagram style (info architecture)"
"Debug: login fails on invalid token, check auth middleware"
```
**What happens:** I execute narrowly, minimal exploration.  
**Token cost:** 30% (focused execution)

### Level 3: Surgical (15% Cost)
```
"Add React.lazy() to src/App.tsx lines 15-20 for /dashboard and /settings routes"
"Apply Pentagram style to hero section: black/white + brand color, 60% whitespace, Helvetica"
"Fix auth/middleware.ts:47 - token validation should check expiry before signature"
```
**What happens:** I execute exactly what you specified, zero exploration.  
**Token cost:** 15% (pure execution)

**Aim for Level 2-3 when you know what you want. Use Level 0-1 when you genuinely need exploration.**

---

## Skill-Specific Patterns

### dream-studio:think

❌ **Wasteful:**
```
"Think about how to build this feature"
```

✅ **Efficient:**
```
"think: Add real-time collaboration to editor
Context: React 19 + Cloudflare Workers + D1
Constraints: <100ms latency, max 1000 concurrent users
Evaluate: WebSocket vs SSE vs polling, focus on infra cost"
```

**Why:** Gives me constraints + evaluation criteria upfront, I don't explore every possible approach.

---

### dream-studio:plan

❌ **Wasteful:**
```
"Plan how to build the feature"
```

✅ **Efficient:**
```
"plan: Implement real-time collaboration (WebSocket approach approved)
Scope: presence indicators, cursor tracking, text sync
Out of scope: voice/video, permissions, conflict resolution v2
Break into max 8 tasks, frontend-first"
```

**Why:** Approach already approved (from think), clear scope boundaries, task count limit.

---

### dream-studio:build

❌ **Wasteful:**
```
"Build the feature"
```

✅ **Efficient:**
```
"build: Execute plan from .planning/realtime-collab.md
Start with tasks 1-3 (WebSocket server + connection manager + presence)
Skip task 6 (cursor tracking) for now, I'll add later
Use subagents, commit after each task"
```

**Why:** References existing plan, specifies task range, clear exclusions, execution strategy.

---

### dream-studio:design

❌ **Wasteful:**
```
"Design a landing page"
```

✅ **Efficient (when you know style):**
```
"brand: Stripe (get logo + colors only, I have design direction)
Then apply to landing page: hero + features + pricing sections"
```

✅ **Efficient (when you don't know style):**
```
"design direction: B2B SaaS landing page
Prefer: clean/professional over creative/bold
Recommend 2 options (not 3), brief descriptions"
```

**Why:** Either skip design direction (saves 40%), or constrain it (saves 20%).

---

### dream-studio:debug

❌ **Wasteful:**
```
"The app is broken, fix it"
```

✅ **Efficient:**
```
"debug: Dashboard charts not rendering after deploy
Reproduction: /dashboard route, Chrome, happens 100% of time
Hypothesis: D1 binding missing in wrangler.toml (worked locally)
Start: check wrangler.toml, compare to local, verify bindings"
```

**Why:** Reproduction steps + hypothesis = I start focused, not exploring every possible cause.

---

### dream-studio:review

❌ **Wasteful:**
```
"Review this PR"
```

✅ **Efficient:**
```
"review: PR #47 (real-time collab)
Spec: .planning/realtime-collab.md
Focus: WebSocket error handling, race conditions, memory leaks
Skip: code style (auto-formatted), file structure (already approved in plan)"
```

**Why:** Reference spec for compliance check, focus areas specified, explicit skips.

---

### dream-studio:verify

❌ **Wasteful:**
```
"Test this feature"
```

✅ **Efficient:**
```
"verify: Real-time collaboration feature
Golden path: 2 users join, both see cursors, text syncs
Edge cases: network disconnect, reconnect, 10+ concurrent users
Skip: load testing (defer to later), mobile (desktop-only for v1)
Capture screenshots of 2-user session"
```

**Why:** Clear test scope, explicit edge cases, known skips, output requirements.

---

### huashu-design

❌ **Wasteful:**
```
"Make a prototype"
```

✅ **Efficient:**
```
"prototype: iOS onboarding (4 screens)
Flow: welcome → permissions → customize → done
Use brand-spec.md from assets/myapp/ (already have logo/colors)
Skip Playwright verification (trust for now, will verify manually)"
```

**Why:** Screen count, flow specified, reference existing assets, skip optional verification.

---

## Multi-Step Tasks: The "Don't Implement Yet" Pattern

### Pattern: Big Request → Spec First → Approve → Implement

❌ **Wasteful (one-shot):**
```
"Build a real-time collaboration feature"
→ I build immediately, you realize it's not what you wanted, I rebuild
→ Token cost: 200% (build + rebuild)
```

✅ **Efficient (spec-first):**
```
Step 1: "think: Real-time collaboration feature, don't implement yet"
→ I write spec, you review
→ Token cost: 30%

Step 2: "plan: Implement WebSocket approach (option B from spec)"
→ I break into tasks, you approve
→ Token cost: 20%

Step 3: "build: Execute plan, tasks 1-5"
→ I implement what was approved
→ Token cost: 50%

Total: 100% (vs 200% for one-shot + rebuild)
```

**Key phrase: "don't implement yet"** — Signals you want spec/plan, not code.

---

## When To Skip Steps

### You Can Skip "think" If:
- You already know the approach
- It's a simple, well-understood task
- You're following an existing pattern

**Example:**
```
"build: Add /api/users endpoint following same pattern as /api/posts
GET (list), POST (create), same auth middleware, same validation approach"
```

### You Can Skip "plan" If:
- Task is <2 hours
- No dependencies
- Straightforward implementation

**Example:**
```
"Add loading spinner to Dashboard component on src/pages/Dashboard.tsx
Use <Spinner /> from components/ui, show while data.isLoading"
```

### You Can Skip "review" If:
- Trivial changes (typo fixes, config tweaks)
- You'll review yourself
- Fast iteration context (prototyping)

**Example:**
```
"Fix typo in README line 47: 'teh' → 'the', commit directly"
```

---

## Context Management: When To Start Fresh

### Continue Current Session If:
- Follow-up to previous task
- Related context (same feature/module)
- <50% context used

### Start New Session If:
- Context >50% and starting unrelated task
- Token usage feels sluggish
- After large research/exploration task

**How to check:** Look at system reminder "Context at ~X%"

**How to start fresh:**
1. Finish current work, commit
2. Run `dream-studio:handoff` to save state
3. Start new session
4. Reference handoff doc if continuing work

---

## Research vs Execution Mode

### Research Mode (Exploration Expected)
```
"investigate huashu-design repo - what does it do, how does it compare to our design skill?"
"explore options for real-time sync: WebSocket, SSE, polling - pros/cons of each"
"analyze codebase: how is auth implemented, what patterns do we use?"
```
**Token cost:** High (intentional exploration)  
**When to use:** When you genuinely don't know and need me to explore

### Execution Mode (Minimal Exploration)
```
"Read huashu-design/README.md and SKILL.md, tell me: core capabilities + does it export PPTX?"
"Implement WebSocket approach for real-time sync (SSE rejected, polling too slow)"
"Add JWT validation to auth/middleware.ts following existing pattern in auth/login.ts"
```
**Token cost:** Low (focused execution)  
**When to use:** When you know what you want, just need execution

**Signal research vs execution clearly** — I'll match your mode.

---

## File Operations: Targeted vs Broad

### ❌ Broad (Wasteful)
```
"Check this codebase"
→ I read 20+ files to understand structure
```

### ✅ Targeted (Efficient)
```
"Read src/auth/middleware.ts, check if it validates JWT expiry"
→ I read 1 file, answer specific question
```

### ❌ Broad (Wasteful)
```
"Find where we handle errors"
→ I grep entire codebase, read many files
```

### ✅ Targeted (Efficient)
```
"Grep 'try.*catch' in src/api/, show error handling pattern"
→ I grep specific directory, report pattern
```

**Rule:** Tell me exactly which files/directories to check when you know.

---

## Batching: One Clear Request > Multiple Vague Requests

### ❌ Incremental (Wasteful)
```
Turn 1: "Check auth"
Turn 2: "Now check the API"
Turn 3: "Also check the DB schema"
Turn 4: "Put it all together"
→ 4 turns, I rebuild context each time
```

### ✅ Batched (Efficient)
```
Turn 1: "Review auth flow end-to-end:
1. How does login work (auth/login.ts)
2. How is JWT validated (auth/middleware.ts)
3. Where is user stored (check schema)
4. Summarize the full flow"
→ 1 turn, I build context once
```

**Savings:** 60-70% vs incremental

---

## Common Scenarios

### Scenario: New Feature Request

**Bad prompting (200% tokens):**
```
"I need a new feature"
→ "What feature?"
→ "Real-time collaboration"
→ "What approach?"
→ "WebSocket maybe?"
→ I build something, you say "not what I wanted", I rebuild
```

**Good prompting (80% tokens):**
```
"think: Real-time collaboration feature
Requirements: presence indicators, cursor tracking, text sync
Constraints: <100ms latency, Cloudflare Workers (no long-lived connections)
Evaluate: WebSocket vs SSE vs polling
Don't implement yet, I'll review spec first"
→ I write spec with 3 options
→ You pick option B
→ "plan: Implement SSE approach from spec"
→ "build: Execute plan"
```

---

### Scenario: Bug Fix

**Bad prompting (150% tokens):**
```
"Something is broken"
→ "What's broken?"
→ "Login doesn't work"
→ "What's the error?"
→ "Invalid token"
→ I explore entire auth system
```

**Good prompting (40% tokens):**
```
"debug: Login fails with 'invalid token' error
Reproduction: POST /api/login with valid credentials
Error appears in console: 'JWT verification failed'
Hypothesis: token expiry check might be wrong
Start with auth/middleware.ts token validation logic"
→ I start focused, find issue quickly
```

---

### Scenario: Design Work

**Bad prompting (180% tokens):**
```
"Design a landing page"
→ I run Design Direction Advisor, show 3 options
→ You pick Pentagram
→ I ask about content
→ You provide content
→ I ask about assets
→ You provide logo
→ I build
```

**Good prompting (60% tokens):**
```
"brand: Acme Corp (need logo + colors, skip design direction)
Then design landing page in Pentagram style:
- Hero: 'Ship faster with Acme' + screenshot
- Features: speed, security, scale (3 columns)
- CTA: 'Start free trial'
Use Helvetica, black/white + brand color, 60% whitespace"
→ I get assets, build exactly what you specified
```

---

### Scenario: Code Review

**Bad prompting (120% tokens):**
```
"Review my changes"
→ I read all changed files, review everything
→ You say "I only care about security"
→ I re-review focused on security
```

**Good prompting (50% tokens):**
```
"review: Focus on security only
Check: SQL injection, XSS, auth bypass, secrets in code
Skip: code style, performance, file structure
Files changed: src/api/users.ts, src/auth/middleware.ts"
→ I review only security in those 2 files
```

---

## Emergency: Context Blowout Recovery

If context usage spikes unexpectedly:

### Immediate Actions
1. **Stop current task:** Don't continue if context is >70%
2. **Commit what's done:** Save progress before reset
3. **Start fresh session:** New session = fresh context
4. **Reference prior work:** "Continue from commit abc123" or "Read .planning/task.md and resume"

### Prevention
- Break large tasks into smaller chunks
- Commit after each logical unit
- Use `dream-studio:handoff` before context fills
- Start new session for unrelated tasks

---

## Cheat Sheet

| Want to... | Efficient Prompt Pattern |
|-----------|-------------------------|
| Explore options | "think: X, evaluate A vs B vs C on criteria Y, don't implement" |
| Break into tasks | "plan: X (approach A approved), max 8 tasks, frontend-first" |
| Execute plan | "build: Execute .planning/X.md tasks 1-5, commit each" |
| Get brand assets | "brand: X (logo + colors only, skip direction)" |
| Design with direction | "design direction: X for Y audience, prefer clean over bold, 2 options" |
| Debug issue | "debug: X fails when Y, hypothesis Z, start with file.ts:line" |
| Review code | "review: focus on A and B, skip C and D, files: X.ts Y.ts" |
| Test feature | "verify: X feature, golden: A, edges: B and C, skip: D" |
| Quick file read | "Read X.ts lines 10-50, check if it does Y" |
| Quick search | "Grep 'pattern' in src/dir/, count matches" |

---

## Before You Prompt, Ask Yourself:

1. **Do I know the approach?** → Skip "think", go to "plan" or "build"
2. **Is this <2 hours?** → Skip "plan", go to "build"
3. **Do I know the file/module?** → Tell me exactly where to look
4. **Do I need exploration?** → Signal "research mode" vs "execution mode"
5. **Can I describe the output?** → Specify exactly what you want
6. **Are there optional steps?** → Say "skip X" explicitly

**The more you know, the more you specify. The more you specify, the fewer tokens I use.**

---

## Summary: 3 Rules

1. **Be specific** — Tell me what you need, where to look, what to skip
2. **Spec before build** — "Don't implement yet" for big tasks, review spec first
3. **Batch requests** — One clear request > multiple vague rounds

Follow these 3 rules → 40-70% token savings with better results.
