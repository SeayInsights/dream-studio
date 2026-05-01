# dream-studio:core — Build Lifecycle

A complete build lifecycle skill for Claude Code that takes you from idea to deployment with disciplined workflows at each stage.

## Overview

The **core** pack provides 9 modes covering the full development lifecycle:

- **think** — Design before building. Clarify requirements, explore approaches, write specs
- **plan** — Break work into tasks. Create atomic, testable plans with clear dependencies
- **build** — Execute the plan. One task at a time, with verification loops
- **review** — Code review. Automated quality checks + human-readable feedback
- **verify** — Prove it works. Run tests, check edge cases, validate against spec
- **ship** — Pre-deploy quality gate. Final checks before release
- **handoff** — Context transfer. Pass minimal context to fresh sessions
- **recap** — Session summary. What was done, what's left, key decisions
- **explain** — Code walkthrough. Understand how systems work

## Installation

1. Copy this directory to your Claude Code plugins folder:
   ```
   ~/.claude/plugins/dream-studio-core/
   ```

2. Add to your global `~/.claude/CLAUDE.md`:
   ```markdown
   ## dream-studio:core routing
   When user says "think:", "plan:", "build:", "review:", "verify:", "ship:", "handoff:", "recap:", or "explain:", invoke:
   Skill(skill="dream-studio:core", args="<mode>")
   ```

3. Restart Claude Code

## Usage Examples

### Think Mode
```
think: Should we use REST or GraphQL for this API?
```
Outputs a spec with 2-3 approaches, trade-offs, and a recommendation. No code until approved.

### Plan Mode
```
plan: Add user authentication to the app
```
Generates a task breakdown with dependencies, estimates, and verification criteria.

### Build Mode
```
build: Execute the plan from .planning/
```
Implements tasks one at a time, runs tests, commits atomically.

### Review Mode
```
review: Check PR #42
```
Runs linters, tests, security checks. Provides line-specific feedback in GitHub PR format.

### Verify Mode
```
verify: Test the login flow
```
Runs tests, checks edge cases, validates against acceptance criteria from the spec.

### Ship Mode
```
ship: Ready to deploy
```
Runs full quality gate: tests, linters, security scan, bundle size check, changelog update.

### Handoff Mode
```
handoff: Pass context to a new session
```
Outputs minimal context needed to continue work in a fresh session. Used when tokens approach limit.

### Recap Mode
```
recap: Summarize this session
```
Generates a concise summary of what was built, key decisions, and next steps.

### Explain Mode
```
explain: How does the auth middleware work?
```
Walks through code flow, explains design decisions, surfaces gotchas.

## Prerequisites

- Claude Code CLI installed
- Git repository (for review, ship modes)
- Project with `CLAUDE.md` (recommended)

## Advanced Features

### Progressive Disclosure
Modes unlock as you use the skill. Early modes (think, plan, build) are always available. Advanced modes (ship, handoff) unlock after you've used the basic workflow.

### Gotcha Tracking
Each mode has a `gotchas.yml` file with known failure patterns. Read automatically before execution.

### Research Cache
Think mode caches research findings to avoid re-researching the same topics across sessions.

### Shared Resources
All modes share common modules:
- `git.md` — Branch operations, commit formatting
- `format.md` — Output formatting, progress tracking
- `quality.md` — Build commands, test execution
- `orchestration.md` — Subagent spawning, model selection

## Directory Structure

```
dream-studio-core/
├── SKILL.md              # Complete mode documentation
├── plugin.json           # Plugin metadata
├── README.md             # This file
└── modes/
    ├── think/
    ├── plan/
    ├── build/
    ├── review/
    ├── verify/
    ├── ship/
    ├── handoff/
    ├── recap/
    └── explain/
```

## Workflow Example

Full workflow from idea to deployment:

```
1. think: Build a task queue for background jobs
   → Outputs spec with architecture options

2. plan: Implement the task queue (after spec approved)
   → Generates 8 tasks with dependencies

3. build: Execute the plan
   → Implements tasks T001-T008, commits atomically

4. review: Check the PR
   → Automated quality checks, feedback

5. verify: Test the task queue
   → Runs integration tests, edge case validation

6. ship: Deploy to production
   → Quality gate, changelog, deployment checklist
```

## License

MIT

## Support

- GitHub: https://github.com/SeayInsights/dream-studio
- Issues: https://github.com/SeayInsights/dream-studio/issues
