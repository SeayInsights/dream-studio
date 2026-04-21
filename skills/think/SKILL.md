---
name: think
description: Clarify an idea, explore 2-3 approaches with trade-offs, write a spec, and get approval before any code. Trigger on `think:`, `spec:`, `shape ux:`, `design brief:`, `research:`.
pack: core
---

# Think — Design Before Building

## Trigger
`think:`, `spec:`, `shape ux:`, `design brief:`, `research:`

## Purpose
Clarify the idea, explore approaches with trade-offs, write a spec, get Director approval. No code until approved.

## Scaling
- Config change → 1 paragraph summary
- Bug fix → problem statement + approach
- Feature → full spec with alternatives
- New system → architecture spec with diagrams

## Steps
1. **Clarify** — Restate what's being built and why. Surface assumptions. Ask Director if anything is unclear.
2. **Explore** — 2-3 approaches with trade-offs. Pros, cons, complexity, risk for each.
3. **Recommend** — Pick one approach with rationale.
4. **Spec** — Write to `.planning/<topic>.md` with:
   - Problem statement
   - Chosen approach + why
   - Scope: in / out
   - Dependencies
   - Risk flags
5. **Approve** — Present spec to Director. Wait for explicit "go" before any code.

## Output
Spec document at `.planning/<topic>.md`. Director approval in conversation.

## Next in pipeline
→ `plan` (break spec into executable steps)

## Anti-patterns
- Writing code before spec is approved
- Spec with only one approach (always explore alternatives)
- Spec longer than the implementation would be
- Asking Director to make every technical decision (recommend, let them override)
