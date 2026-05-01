---
name: think
model_tier: opus
description: Clarify an idea, explore 2-3 approaches with trade-offs, write a spec, and get approval before any code. Trigger on `think:`, `spec:`, `shape ux:`, `design brief:`, `research:`.
pack: core
chain_suggests:
  - condition: "always"
    next: "plan"
    prompt: "Spec approved — plan the tasks?"
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
