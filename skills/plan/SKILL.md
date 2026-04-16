---
name: plan
description: Break an approved spec into atomic, dependency-ordered tasks with per-task acceptance criteria. Trigger on `plan:` or after `think` is approved.
---

# Plan — Break Spec Into Steps

## Trigger
`plan:`, or after `think` spec is approved

## Purpose
Break an approved spec into executable steps with dependencies, order, and acceptance criteria.

## Steps
1. **Read spec** — Reference the approved spec from `think`. Confirm scope.
2. **Decompose** — Break into atomic tasks. Each task = one logical commit.
3. **Order** — Dependencies first. Identify what can run in parallel.
4. **Acceptance** — Each task gets acceptance criteria that can be verified without judgment.
5. **Write plan** — Output to `.planning/<topic>-plan.md`

## Plan format
```
# Plan: [topic]
Spec: [path to spec]
Date: YYYY-MM-DD

## Tasks
### 1. [Task name]
- Files: [what's touched]
- Depends on: [task numbers or "none"]
- Acceptance: [how to verify this is done]

### 2. [Task name]
...

## Summary
| # | Task | Depends on | Complexity |
|---|---|---|---|
| 1 | ... | none | low |
| 2 | ... | 1 | medium |
```

## Output
Plan document at `.planning/<topic>-plan.md`.

## Next in pipeline
→ `build` (execute the plan)

## Anti-patterns
- Tasks too large (multiple unrelated changes in one task)
- Missing acceptance criteria
- No dependency ordering
- Plan that doesn't cover the full spec
