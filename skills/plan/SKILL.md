---
name: plan
description: Break an approved spec into atomic, dependency-ordered tasks with per-task acceptance criteria. Trigger on `plan:` or after `think` is approved.
pack: core
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
5. **Assess traceability need** — See Traceability section below.
6. **Write plan** — Output to `.planning/<topic>-plan.md`
7. **Write traceability registry** — If traceability is active, output to `.planning/traceability.yaml`

## Traceability

Traceability links spec requirements → plan tasks → commits → tests via TR-IDs.

**When to activate (any of these):**
- Plan has **4 or more tasks**
- Spec has distinct, separately-verifiable requirements (not one monolithic goal)
- User explicitly asks for traceability (`plan: with traceability`, `track requirements`)
- Work is for a client, production system, or anything that needs an audit trail

**When to skip:**
- Plan has **3 or fewer tasks** AND user didn't request traceability
- Prototype or experimental work (`prototype:`, `experiment:`, `spike:`)
- Single-file bug fixes

**When active:**
1. Extract distinct requirements from the spec
2. Assign each a TR-ID (`TR-001`, `TR-002`, ...) with priority (must/should/could)
3. Tag each task with the TR-IDs it implements
4. Write `.planning/traceability.yaml` using the template from `templates/traceability-registry.yaml`
5. Include the Requirements table and TR-ID column in the plan

**When inactive:**
- Skip steps 1-5 above
- Use the simplified plan format (no Requirements table, no TR-ID column)
- Do NOT create traceability.yaml
- The build and verify skills will detect the absence and skip their traceability steps

## Plan format — Full (traceability active)
```
# Plan: [topic]
Spec: [path to spec]
Traceability: .planning/traceability.yaml
Date: YYYY-MM-DD

## Requirements
| TR-ID | Description | Priority | Tasks |
|-------|-------------|----------|-------|
| TR-001 | ... | must | 1, 2 |
| TR-002 | ... | should | 3 |

## Tasks
### 1. [Task name]
- Implements: TR-001
- Files: [what's touched]
- Depends on: [task numbers or "none"]
- Acceptance: [how to verify this is done]

### 2. [Task name]
...

## Summary
| # | Task | Depends on | TR-IDs | Complexity |
|---|---|---|---|---|
| 1 | ... | none | TR-001 | low |
| 2 | ... | 1 | TR-001 | medium |
```

## Plan format — Lite (traceability inactive)
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
- Plan document at `.planning/<topic>-plan.md` (always)
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
