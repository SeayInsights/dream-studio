---
name: analyze
description: "Multi-perspective analysis engine and domain-specific evaluation."
argument-hint: "multi | domain-re"
user_invocable: true
args: mode
---

# Analyze — Analysis Engine

## Mode dispatch

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
