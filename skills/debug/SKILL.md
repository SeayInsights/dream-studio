---
name: debug
description: Systematic problem solving — reproduce, hypothesize, test one variable at a time, narrow, fix, document. No shotgun debugging. Trigger on `debug:`, `diagnose:`, or on build/verify failure.
pack: quality
---

# Debug — Scientific Method

## Before you start
Read `gotchas.yml` in this directory before every invocation.
If the project has `.planning/GOTCHAS.md` — read it before starting.
If the project has `.planning/CONSTITUTION.md` — read it before starting.

## Trigger
`debug:`, `diagnose:`, on build failure, on verify failure, on agent retry

## Purpose
Systematic problem solving. Reproduce, hypothesize, test, narrow, fix. No shotgun debugging.

## Steps
0. **Load project context** — If `.planning/GOTCHAS.md` exists, read it before forming any hypothesis. Known failure patterns there may short-circuit the entire debug loop.
1. **Reproduce** — Confirm the bug exists. Get exact steps, error messages, stack traces.
1.5. **Capture** — Encode the reproduction as a failing artifact:
   - **If unit-testable:** Write a minimal failing test that encodes the exact reproduction steps. This test becomes the fix's acceptance criterion and is used by `verify` as the red-green check.
   - **If NOT unit-testable** (UI rendering, race condition, infrastructure): Capture a screenshot or log as the reproduction artifact instead.
   - Set `testable: true/false` in debug output — the `fix-issue` workflow uses this to conditionally fire the `write-failing-test` node.
2. **Hypothesize** — Form 2-3 hypotheses ranked by likelihood based on the error.
3. **Test** — Test the most likely hypothesis first. One variable at a time.
4. **Narrow** — Eliminate hypotheses based on results. Add new ones if needed.
5. **Fix** — Apply the fix. Verify it resolves the issue without introducing new ones.
6. **Document** — Record what was tried and ruled out so the next session doesn't repeat. **Mandatory:** After any debug session that required ≥ 3 hypothesis iterations OR revealed a reusable pattern (a class of bug, a hidden invariant, a surprising interaction), invoke `learn:` before closing the session. This is not optional — draft lessons are the input to dream-studio's self-improvement loop. Include the debug log summary and why the standard approach failed as the lesson input.

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
