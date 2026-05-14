# Analyze — Analysis Engine

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, apply the portable skill contract. If a current calibration interface is available in this checkout, use it; otherwise rely on the mode table below. If a mode is locked, show the unlock message and stop.

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
| repo | modes/repo/SKILL.md | analyze repo:, repo patterns:, compare repos:, repo analysis: |
| intelligence | modes/intelligence/SKILL.md | analyze project:, project intelligence:, scan codebase: |

## Shared resources

- `analysts/` — analyst persona definitions (used by multi mode)
- `modes.yml` — mode and analyst configuration
