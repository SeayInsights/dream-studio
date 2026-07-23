---
dream_studio:
  skill_id: ds-core
  pack: core
  mode: think
  mode_type: analysis
  inputs: [problem_statement, constraints, context, user_goals]
  outputs: [spec_document, user_stories, requirements, decision_rationale]
  capabilities_required: [Read, Write, Grep, WebSearch]
  model_preference: sonnet
  estimated_duration: 30-90min
---

# Think — Design Before Building

## Before you start
Read `gotchas.yml` in this directory before every invocation.
If the project has `.planning/GOTCHAS.md` — read it before starting.
If the project has `.planning/CONSTITUTION.md` — read it before starting.

## Trigger
`think:`, `spec:`, `shape ux:`, `design brief:`, `research:`

## Flags
- `--recommend-tools` — Appends external tool suggestions based on problem keywords
- `--research` — Appends web research findings with source quality assessment

## Purpose
Clarify the idea, explore approaches with trade-offs, write a spec, get Director approval. No code until approved.

## Scaling
- Config change → 1 paragraph summary
- Bug fix → problem statement + approach
- Feature → full spec with alternatives
- New system → architecture spec with diagrams

## Template
Use `skills/think/templates/spec-template.md` for structure:
- User Stories (P1/P2/P3 prioritized)
- Functional Requirements (FR-001 format)
- Success Criteria (SC-001 measurable outcomes)
- Edge Cases and Assumptions

## Steps
1. **Clarify** — Restate what's being built and why. Ask Director 3-5 targeted questions if unclear. Read `.planning/CONSTITUTION.md` if exists.

2. **Explore** — 2-3 approaches with trade-offs (pros, cons, complexity, risk).

3. **Recommend** — Pick one approach with rationale.

4. **Spec** — Author to the docstore using the template: `ds files write "specs/<topic>/spec.md" --category planning` (zero-disk — `.planning/` disk writes are denied).

   - **If `--recommend-tools` flag:** Use the maintained Dream Studio tool discovery interface if present. Append top 5 tools (confidence >0.7) with install commands. If no maintained interface exists, state that tool discovery is unavailable.
   
   - **If `--research` flag:** Use the maintained Dream Studio research cache/source interface if present. Append findings with Tier 1/2 sources, confidence score, and summary (3-5 sentences). If no maintained interface exists, perform normal sourced research and note that cache persistence was skipped.

   **Detailed workflow:** See `references/workflow-details.md` for sub-step details, research cache checks, source quality validation, and risk pre-population.

5. **Approve** — Present spec to Director. Wait for explicit "go" before any code.

## Example Output

```markdown
# User Authentication Spec

## User Stories
- (P1) Email/password login
- (P2) Password reset
- (P3) OAuth integration

## Requirements
- FR-001: System MUST hash passwords with bcrypt
- SC-001: 95% of users complete login in <30 seconds

## Recommended Tools (if --recommend-tools used)
- **bcrypt** (92% confidence) - Password hashing library
  - Install: `pip install bcrypt`

## Research Findings (if --research used)
**Topic:** Authentication best practices
**Confidence:** 0.85 (High) | **Triangulation:** 1.0 (6+ sources)

**Sources:** [bcrypt vs Argon2](https://github.com/...) (Tier 1: GitHub), ...

**Summary:** bcrypt is industry standard with wide support. Argon2 is newer and more resistant to GPU attacks but has fewer implementations. For most applications, bcrypt is recommended.
```

## Output
Spec document in the docstore as `specs/<topic>/spec.md` (`ds files read`). Director approval in conversation.

For complex features, also author `specs/<topic>/design.md` to the docstore (`ds files write --category planning`) using `templates/design-template.md`.

## Next in pipeline
→ `plan` (break spec into executable steps)

## Anti-patterns
- Writing code before spec is approved
- Spec with only one approach (always explore alternatives)
- Spec longer than the implementation would be
- Asking Director to make every technical decision (recommend, let them override)
