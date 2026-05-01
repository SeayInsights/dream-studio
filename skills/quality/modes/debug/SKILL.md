---
name: debug
description: Systematic problem solving — reproduce, hypothesize, test one variable at a time, narrow, fix, document. No shotgun debugging.
pack: core
triggers:
  - debug:
  - diagnose:
chain_suggests:
  - condition: "root_cause_found"
    next: "plan"
    prompt: "Root cause identified — plan the fix?"
  - condition: "debug_iterations_gte_3"
    next: "learn"
    prompt: "Complex debug — capture lesson?"
---

## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`debug:`, `diagnose:`

## Purpose
Diagnose and fix bugs using disciplined hypothesis testing. One variable at a time.

## Steps

**Pre-flight Gotcha Briefing** — Before starting diagnosis, surface recent gotchas for the domain being debugged:
1. Run `hooks/lib/gotcha_scanner.py` → `search_gotchas(topic)` where topic is the bug description
2. Also run `get_recent_gotchas(limit=3)` for the debug skill
3. Display matches as: `[severity] gotcha-id — title`
4. If a gotcha directly matches the bug symptoms, highlight it: "⚡ This gotcha may explain the issue"
5. Debug sessions are the highest-value place for this — most gotchas originated from debug sessions

0. **Load project context** — If `.planning/GOTCHAS.md` exists, read it before forming any hypothesis. Known failure patterns there may short-circuit the entire debug loop.
1. **Reproduce** — Confirm the bug exists. Get exact steps, error messages, stack traces.
2. **Hypothesize** — Form 2-3 hypotheses ranked by likelihood based on the error.
3. **Test** — Test the most likely hypothesis first. One variable at a time.
4. **Narrow** — Eliminate hypotheses based on results. Add new ones if needed.
5. **Fix** — Apply the fix. Verify it resolves the issue without introducing new ones.
6. **Document** — Record what was tried and ruled out so the next session doesn't repeat.
7. **Capture** — After any debug session that required ≥3 hypothesis iterations OR revealed a reusable pattern, invoke `learn:` before closing. This is not optional — draft lessons are the input to dream-studio's self-improvement loop. After the fix is committed and the GitHub issue is created, invoke `learn:` with the debug log summary as input.

## Debug log format
Track in conversation to prevent retrying failed approaches:
```
## Debug: [symptom]

### Reproduce
[exact steps to reproduce]

### Hypothesis 1: [description] — LIKELY / RULED OUT
- Test: [what you did]
- Result: [what happened]
- Conclusion: [ruled out / confirmed / need more data]

### Hypothesis 2: [description]
...

### Fix
[what was changed and why]

### Verified
[evidence the fix works + no regressions]
```

## Next in pipeline
→ back to `build` or `verify` (wherever the failure originated)

## Anti-patterns

| ❌ Wrong | ✅ Correct |
|---|---|
| "Let me try this" without stating a hypothesis | State hypothesis before every test: "I think X because Y" |
| Changing multiple things between tests | One variable per test — isolate the change |
| Ignoring error messages and guessing | Read the full error message first; it usually names the cause |
| Repeating a failed approach from a previous session | Read the debug log before forming hypotheses |
| Shotgun debugging (changing 5 things at once) | Test the single most likely hypothesis first |
| Skipping reproduction ("I think I know what it is") | Always reproduce with exact steps before hypothesizing |
| Not tracking hypotheses | Log every hypothesis — even obvious ones — so the next session doesn't repeat |
| Using shell grep or findstr to search TMDL/UTF-8 files on Windows | Use Python with `open(path, encoding='utf-8')` — shell tools break on accented characters |
| Continuing past 5 failed hypotheses without escalating | After 5 failures, stop and escalate to Director with the full debug log |
