## Before you start
Read `gotchas.yml` in this directory before every invocation.

## Trigger
`debug:`, `diagnose:`

## Purpose
Diagnose and fix bugs using disciplined hypothesis testing. One variable at a time.

## Pre-flight Intelligence
Before starting diagnosis, query the registry:
1. **Gotcha check** — `get_gotchas_for_skill('quality:debug')` from `hooks/lib/studio_db.py`. Show top 3 recent gotchas.
2. **Approach history** — `get_best_approaches('quality:debug')` from `hooks/lib/studio_db.py`. Prior debug patterns often short-circuit new diagnosis.
3. **Project context** — If `.planning/GOTCHAS.md` exists, read it before forming any hypothesis.

## Diagnose Before You Debug {#diagnose}

Match symptoms to category, then follow the trace strategy in the reference:

| Symptom Pattern | Bug Category | Trace Strategy | Reference |
|-----------------|--------------|----------------|-----------|
| ImportError, ModuleNotFoundError, missing attribute | Dependencies | Check venv, requirements, import paths | [runtime-errors](references/runtime-errors.md#dependencies) |
| TypeError, ValueError, AttributeError | Type/Data Issues | Trace data flow, validate types | [runtime-errors](references/runtime-errors.md) |
| Build fails, compilation errors, syntax errors | Build System | Check build config, dependencies, syntax | [build-failures](references/build-failures.md) |
| Wrong output, incorrect calculation, data mismatch | Logic Bug | Trace data flow, validate assumptions | [logic-bugs](references/logic-bugs.md) |
| Works locally, fails in prod/CI | Environment Drift | Compare envs, check config, secrets | [environment-drift](references/environment-drift.md) |
| Slow execution, timeout, high memory | Performance | Profile, measure, identify bottleneck | [performance-issues](references/performance-issues.md) |
| Unsure which tool to use (Grep/Read/LSP/Bash) | Tool Selection | Match scenario to tool capability | [tool-selection](references/tool-selection.md) |

## Workflow

0. **Reproduce** — Get exact steps, error messages, stack traces.
1. **Hypothesize** — Form 2-3 hypotheses ranked by likelihood. Check diagnose table first.
2. **Test** — Test most likely hypothesis. One variable at a time.
3. **Narrow** — Eliminate hypotheses. Add new ones if needed.
4. **Fix** — Apply fix. Verify no regressions.
5. **Document** — Record what was tried and ruled out.
6. **Capture** — After ≥3 iterations OR reusable pattern found, invoke `learn:` with debug log.

## Debug Log Template
```
## Debug: [symptom]
### Reproduce: [exact steps, error messages]
### Hypothesis 1: [description] — LIKELY/RULED OUT
- Test: [action] → Result: [outcome] → Conclusion: [status]
### Fix: [change + why]
### Verified: [evidence + no regressions]
```

## Next in pipeline
→ `build` or `verify`

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
