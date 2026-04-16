---
name: debug
description: Systematic problem solving — reproduce, hypothesize, test one variable at a time, narrow, fix, document. No shotgun debugging. Trigger on `debug:`, `diagnose:`, or on build/verify failure.
---

# Debug — Scientific Method

## Trigger
`debug:`, `diagnose:`, on build failure, on verify failure, on agent retry

## Purpose
Systematic problem solving. Reproduce, hypothesize, test, narrow, fix. No shotgun debugging.

## Steps
1. **Reproduce** — Confirm the bug exists. Get exact steps, error messages, stack traces.
2. **Hypothesize** — Form 2-3 hypotheses ranked by likelihood based on the error.
3. **Test** — Test the most likely hypothesis first. One variable at a time.
4. **Narrow** — Eliminate hypotheses based on results. Add new ones if needed.
5. **Fix** — Apply the fix. Verify it resolves the issue without introducing new ones.
6. **Document** — Record what was tried and ruled out so the next session doesn't repeat.

## Debug log format
Track in conversation to prevent retrying failed approaches:
```
## Debug: [symptom]

### Reproduce
[exact steps + error output]

### Hypothesis 1: [description] — LIKELY / RULED OUT
- Test: [what you did]
- Result: [what happened]
- Conclusion: [confirmed / ruled out / inconclusive]

### Hypothesis 2: [description]
...

### Fix
[what was changed and why]

### Verified
[evidence the fix works + no regressions]
```

## Rules
- Never shotgun debug (changing multiple things at once)
- Never skip reproduction ("I think I know what it is")
- Track every hypothesis — even obvious ones
- If 3 hypotheses fail, re-read the error from scratch
- If stuck after 5 hypotheses, escalate to Director with the full debug log

## Next in pipeline
→ back to `build` or `verify` (wherever the failure originated)

## Anti-patterns
- "Let me try this" without stating a hypothesis
- Changing multiple things between tests
- Ignoring error messages and guessing
- Repeating a failed approach from a previous session
