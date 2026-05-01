# Analyze — Analysis Engine

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, check if it's available by running:
   ```python
   py "../../hooks/lib/skill_calibration.py" check-mode analyze <mode> "<user-message>"
   ```
   If exit code is non-zero, the mode is locked. Show the unlock message (from stdout) and stop.
   If exit code is zero, continue to step 1. If unlock notifications are printed, show them to the user.

1. Parse the mode from the argument (first word).
2. If no mode given, infer from the user's message using the keyword table below.
3. If still ambiguous, default to `multi` (the general-purpose analysis mode).
4. Read `modes/<mode>/SKILL.md` completely.
5. If `modes/<mode>/gotchas.yml` exists, read it before executing.
6. Follow the mode's instructions exactly as written.

| Mode | File | Keywords |
|---|---|---|
| multi | modes/multi/SKILL.md | analyze:, evaluate idea:, /analyze |
| domain-re | modes/domain-re/SKILL.md | domain-re:, real estate:, /domain-re |

## Shared resources

- `analysts/` — analyst persona definitions (used by multi mode)
- `modes.yml` — mode and analyst configuration
