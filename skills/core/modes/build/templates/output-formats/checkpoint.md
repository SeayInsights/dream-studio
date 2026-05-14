# Build Checkpoint Format

Output this checkpoint after every 3 tasks or 30 minutes.

```markdown
## Build Checkpoint — [Timestamp]

### Progress
- Tasks completed: [N] / [Total]
- Last completed: Task [N] — [task name]
- Next up: Task [N+1] — [task name]

### Drift Detection
- [✅ No drift | ⚠️ Minor drift | 🔴 Major drift]
- Details: [if drift detected, explain what and why]

### Blockers / Concerns
- [List any blockers or concerns]
- [Empty if none]

### Context Usage
- Estimated: [~XX%]
- Action: [Continue | Consider handoff after next task | Handoff now]

### Files Changed
- [file1]
- [file2]
- ... ([N] total)

### Next Action
[What happens next — continue with task N+1, address blocker, etc.]
```

## Example

```markdown
## Build Checkpoint — 2026-04-28 14:30

### Progress
- Tasks completed: 3 / 8
- Last completed: Task 3 — Create checkout endpoint
- Next up: Task 4 — Add webhook handler

### Drift Detection
- ⚠️ Minor drift
- Details: Task 3 used Zod validation instead of manual checks (better approach, same outcome)

### Blockers / Concerns
None

### Context Usage
- Estimated: ~45%
- Action: Continue (room for 2-3 more tasks)

### Files Changed
- models/subscription.ts
- lib/stripe.ts
- api/checkout.ts
(3 total)

### Next Action
Continue with Task 4 (webhook handler)
```
