---
name: <pack-name>
description: <one line, ~80 chars — list mode names, no trigger keywords>
argument-hint: "<mode1> | <mode2> | <mode3>"
user_invocable: true
args: mode
---

# <Pack Display Name>

## Mode dispatch

1. Parse the mode from the argument (first word).
2. If no mode given, infer from the user's message using the keyword table below.
3. If still ambiguous, list available modes and ask.
4. Read `modes/<mode>/SKILL.md` completely.
5. If `modes/<mode>/gotchas.yml` exists, read it before executing.
6. Follow the mode's instructions exactly as written.

| Mode | File | Keywords |
|---|---|---|
| example | modes/example/SKILL.md | example:, sample: |

## Shared resources

List any shared files in this pack directory that modes may reference:
- (none by default)
