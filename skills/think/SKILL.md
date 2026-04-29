---
name: think
description: Clarify an idea, explore 2-3 approaches with trade-offs, write a spec, and get approval before any code. Trigger on `think:`, `spec:`, `shape ux:`, `design brief:`, `research:`.
pack: core
---

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
2. **Explore** — 2-3 approaches with trade-offs. Pros, cons, complexity, risk for each.
3. **Recommend** — Pick one approach with rationale.
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

## Next in pipeline
→ `plan` (break spec into executable steps)

## Anti-patterns
- Writing code before spec is approved
- Spec with only one approach (always explore alternatives)
- Spec longer than the implementation would be
- Asking Director to make every technical decision (recommend, let them override)
