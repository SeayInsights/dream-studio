---
ds:
  pack: core
  mode: plan
  mode_type: planning
  inputs: [approved_spec, user_stories, requirements]
  outputs: [plan_document, task_list, traceability_registry, github_issues]
  capabilities_required: [Read, Write, Bash]
  model_preference: sonnet
  estimated_duration: 15-45min
---

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
