# dream-studio:quality — Code Quality & Learning

A code quality and learning skill for Claude Code that helps you debug, polish, harden, secure, and continuously improve your codebase.

## Overview

The **quality** pack provides 7 modes for code quality and organizational learning:

- **debug** — Disciplined debugging. Hypothesis testing, one variable at a time
- **polish** — UI/UX refinement. Design critique, visual improvements, accessibility
- **harden** — Project setup. Best practices, tooling, CI/CD, observability
- **secure** — Security review. Vulnerability scanning, threat modeling, fix recommendations
- **structure-audit** — Architecture review. Dependency analysis, anti-pattern detection
- **learn** — Capture lessons. Extract reusable patterns from completed work
- **coach** — Workflow coaching. Intent classification, skill routing, meta-learning

## Installation

1. Copy this directory to your Claude Code plugins folder:
   ```
   ~/.claude/plugins/dream-studio-quality/
   ```

2. Add to your global `~/.claude/CLAUDE.md`:
   ```markdown
   ## dream-studio:quality routing
   When user says "debug:", "polish:", "harden:", "secure:", "learn:", or "/coach", invoke:
   Skill(skill="dream-studio:quality", args="<mode>")
   ```

3. Restart Claude Code

## Usage Examples

### Debug Mode
```
debug: Login form not submitting on Enter key
```
Forms hypotheses, tests systematically, documents what was ruled out. Captures lessons after complex bugs.

### Polish Mode
```
polish: Make the dashboard look more professional
```
Design critique from first principles, visual refinement suggestions, accessibility audit.

### Harden Mode
```
harden: Set up this new project with best practices
```
Configures linters, formatters, pre-commit hooks, CI/CD, error tracking, observability.

### Secure Mode
```
secure: Review this auth implementation for vulnerabilities
```
OWASP Top 10 check, dependency scanning, threat modeling, fix recommendations with diffs.

### Structure-Audit Mode
```
/structure-audit
```
Analyzes repository structure, detects anti-patterns, suggests refactoring opportunities.

### Learn Mode
```
learn: Capture lessons from the OAuth integration we just built
```
Extracts reusable patterns, gotchas, and decision rationale. Feeds dream-studio's self-improvement loop.

### Coach Mode
```
/coach
```
Classifies user intent, maps to nearest skill/mode, explains confidence and alternatives. Used as routing fallback.

## Prerequisites

- Claude Code CLI installed
- Git repository (for learn mode)
- Project with `CLAUDE.md` (recommended)

## Advanced Features

### Gotcha Registry
Debug mode queries a persistent gotcha registry to surface known failure patterns before diagnosis starts. Prevents re-debugging the same issues.

### Approach History
Debug mode tracks which approaches worked in past sessions and surfaces them as starting points for new bugs.

### Pre-flight Intelligence
Before starting diagnosis, debug mode:
1. Checks gotcha registry for matches
2. Loads best approaches from prior sessions
3. Reads `.planning/GOTCHAS.md` if it exists

### Learning Loop
After debug sessions requiring ≥3 hypothesis iterations, `learn:` mode is automatically invoked to capture patterns for future sessions.

### Security Rule Registry
Secure mode uses a structured rule registry (CWE, OWASP mapping) for consistent vulnerability detection across projects.

## Workflow Examples

### Debug Workflow
```
1. debug: API returning 500 on POST /users
   → Reproduces bug, forms 3 hypotheses, tests systematically
   → Identifies root cause: missing validation middleware
   → Applies fix, verifies resolution

2. learn: (auto-invoked after debug)
   → Captures lesson: "Always check middleware stack order"
   → Saves to gotcha registry for future sessions
```

### Harden Workflow
```
1. harden: New Express API project
   → Installs ESLint, Prettier, Husky, lint-staged
   → Configures GitHub Actions for CI
   → Sets up error tracking (Sentry)
   → Adds health check endpoints

2. secure: Review the new setup
   → Checks for security misconfigurations
   → Validates environment variable handling
   → Suggests rate limiting, helmet.js
```

### Polish Workflow
```
1. polish: Dashboard feels cluttered
   → Design critique: information hierarchy, whitespace, color contrast
   → Suggests removing secondary actions, grouping related metrics
   → Provides before/after mockup diffs

2. verify: (from core pack)
   → Tests on multiple screen sizes
   → Validates accessibility (WCAG AA)
```

## Directory Structure

```
dream-studio-quality/
├── SKILL.md              # Complete mode documentation
├── plugin.json           # Plugin metadata
├── README.md             # This file
└── modes/
    ├── debug/
    ├── polish/
    ├── harden/
    ├── secure/
    ├── structure-audit/
    ├── learn/
    └── coach/
```

## Integration with Core Pack

Quality pack works standalone or alongside `dream-studio:core`:

```
Core workflow:
think → plan → build → review → verify → ship

Quality enhancement:
build → debug (if issues)
review → secure (for security-critical changes)
ship → harden (for new projects)
```

## Debug Log Format

Debug mode maintains a structured log to prevent retrying failed approaches:

```markdown
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

### Verification
[proof that fix works]
```

## License

MIT

## Support

- GitHub: https://github.com/SeayInsights/dream-studio
- Issues: https://github.com/SeayInsights/dream-studio/issues
