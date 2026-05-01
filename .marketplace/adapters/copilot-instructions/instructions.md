# dream-studio — GitHub Copilot Instructions

This document provides GitHub Copilot with dream-studio workflow conventions for efficient, high-quality software delivery.

## Core Workflow: Think → Plan → Build → Review → Verify → Ship

### 1. Think (Design Before Building)
**Triggers:** `think:`, `spec:`, `research:`, `shape ux:`

Before writing code:
- Clarify what's being built and why
- Explore 2-3 approaches with trade-offs
- Write a spec with user stories, functional requirements, success criteria
- Surface assumptions and constraints
- Get approval before proceeding

**Scaling:**
- Config change → 1 paragraph summary
- Bug fix → problem statement + approach
- Feature → full spec with alternatives
- New system → architecture spec with diagrams

### 2. Plan (Break Work into Atomic Tasks)
**Triggers:** `plan:`, `break down:`, `task list:`

Create an atomic build plan:
- Each task touches 1-3 files max
- Tasks are independently committable
- File-level precision (list exact files to modify)
- Numbered tasks (T001, T002, etc.)
- Dependencies clearly marked

### 3. Build (Execute the Plan)
**Triggers:** `build:`, `implement:`, `execute plan:`

Implementation rules:
- Execute tasks in order (T001, T002, T003...)
- Commit after each task completes
- One logical change per commit
- Read files before editing them
- Verify changes compile/run before committing

### 4. Review (Quality Gate)
**Triggers:** `review:`, `review code:`, `review PR:`

Check before shipping:
- Code quality (duplication, complexity, readability)
- Security (input validation, auth, secrets)
- Architecture (consistency with existing patterns)
- Edge cases (error handling, boundary conditions)
- Documentation (README, comments for complex logic)

### 5. Verify (Prove It Works)
**Triggers:** `verify:`, `prove it:`, `test it:`

Validation checklist:
- Run the build/tests
- Test the happy path manually
- Test edge cases and error scenarios
- Verify UI changes in browser before pushing
- Check for runtime errors

### 6. Ship (Final Quality Gate)
**Triggers:** `ship:`, `deploy:`, `release:`

Pre-deployment checks:
- All tests passing
- No console errors
- PR is green (CI passed)
- Changelog updated
- Breaking changes documented

---

## Git Workflow Conventions

### Branch Management
- **Never push directly to `main`** — always use feature branches
- Branch naming: `feat/<topic>`, `fix/<topic>`, `chore/<topic>`
- Check for open PRs before starting: `gh pr list`
- Never force-push without explicit approval
- Before pushing to existing PR branch, verify it hasn't been merged

### Issue → PR Workflow (Recommended)
1. Create GitHub issue: `gh issue create`
2. Create branch: `git checkout -b fix/issue-123-description`
3. Implement, build, verify
4. Commit: `fix: description (fixes #123)`
5. Push and create PR: `gh pr create` with `Fixes #123` in body
6. Verify PR is green, then merge

### Commit Conventions
- One logical change per commit
- Commit messages explain **why**, not what
- **Never add Co-Authored-By attribution**
- Reference issues in commits: `(fixes #123)` or `(relates to #123)`

### PR Size & Quality
- Keep PRs under ~120 lines of changes
- Split larger work into independent PRs
- Each PR should be independently reviewable and deployable

---

## Code Quality Patterns

### Debug Workflow
**Triggers:** `debug:`, `diagnose:`, `fix:`, `why is this broken:`

When debugging:
1. Reproduce the issue
2. Identify root cause (trace execution, check logs)
3. Create GitHub issue with debug log
4. Fix following Issue → PR workflow
5. Verify fix resolves the issue
6. Add regression test if applicable

### Polish & UX
**Triggers:** `polish:`, `UI cleanup:`, `redesign:`, `look better:`

UI refinement checklist:
- Verify changes in browser before committing
- Check responsive behavior (mobile, tablet, desktop)
- Test user interactions (hover, click, keyboard nav)
- Validate accessibility (ARIA labels, contrast, focus states)
- Grep all selector variants before broad CSS renames

### Security Review
**Triggers:** `secure:`, `security review:`, `vulnerabilities:`

Security audit checklist:
- Input validation (XSS, injection, CSRF)
- Authentication & authorization checks
- Secrets management (no hardcoded credentials)
- Dependency vulnerabilities (audit logs)
- HTTPS/TLS enforcement
- Rate limiting for APIs

### Project Hardening
**Triggers:** `harden:`, `project setup:`, `best practices:`

Infrastructure quality:
- CI/CD pipeline configured
- Linting and formatting enforced
- Pre-commit hooks (tests, lint, format)
- Dependency security scanning
- Environment-specific configs (.env pattern)

---

## Testing & Verification

### Before Pushing UI Changes
- Verify in browser/build
- Run build and check for runtime errors
- For "X isn't showing up" bugs, trace full render pipeline before editing

### Build Verification
- Run `npm run build` (or equivalent) before declaring complete
- Check console for errors/warnings
- Test critical paths manually

### Context Management
- Complete and commit each task independently
- Keep PRs small and focused for easier review
- Use grep to verify all selector variants before committing broad renames

---

## Deploy Safety

### CI/CD First
- **Never run deploy commands directly** (e.g., `wrangler deploy`)
- Push to GitHub and let CI handle deploys
- CI auto-deploys after merge (regular PRs don't need manual ship gate)

### When to Use Ship Gate
Use full `ship:` quality gate for:
- Major releases
- Client demos
- After risky refactors
- Before production deploys

Regular PRs do NOT need the ship gate.

---

## Model Usage Guidance

- **Fast models (Haiku):** Searches, exploration, file lookups
- **Capable models (Sonnet):** Code changes, implementation, reasoning
- **Most capable models (Opus):** Complex analysis, architecture, design decisions

---

## Summary

These conventions create a systematic approach to software delivery:
1. Think before building (avoid wasted effort)
2. Plan with precision (atomic, committable tasks)
3. Build incrementally (commit often, small changes)
4. Review thoroughly (quality gate before shipping)
5. Verify completely (prove it works)
6. Ship safely (CI/CD, no manual deploys)

Following these patterns reduces bugs, improves code quality, and makes collaboration easier.
