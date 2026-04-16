---
name: build
description: Execute a plan with atomic commits, per-task evaluation (3-retry cap), drift detection, and periodic checkpoints. Trigger on `build:`, `execute plan:`, or after `plan`.
---

# Build — Execute With Discipline

## Trigger
`build:`, `execute plan:`, or after `plan` is complete

## Purpose
Execute the plan with atomic commits, drift detection, and built-in evaluation.

## Steps
For each task in the plan:

1. **Start** — State which task you're executing. Reference the plan.
2. **Implement** — Write the code. One task = one logical change.
3. **Evaluate** — Check output against the task's acceptance criteria.
   - PASS → commit and move to next task
   - FAIL → iterate (max 3 attempts). After 3 failures → stop and escalate to Director.
4. **Commit** — Atomic commit with message referencing the plan task number.
5. **Checkpoint** — After every 3 tasks or 30 minutes (whichever first), report progress:
   - Tasks completed / total
   - Any drift from plan
   - Blockers or concerns

## Drift detection
If implementation diverges from the plan:
- **Minor drift** (different variable name, slightly different approach) → note it, continue
- **Major drift** (new dependency, scope change, architecture change) → STOP. Report to Director: "Drift detected: [what changed and why]. Adjust plan or revert?"

## Output
Committed code. One commit per task. Checkpoint summaries in conversation.

## Next in pipeline
→ `review` (quality check the completed work)

## Anti-patterns
- Skipping evaluation ("it compiles, ship it")
- Committing multiple tasks in one commit
- Continuing past major drift without Director approval
- Building features not in the plan
