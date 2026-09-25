---
name: ds-domains
description: 'Stack-specific and domain builders. Use for: dashboard-dev:, intake:'
---

# Domains — Stack-Specific Builders

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, apply the portable skill contract. If a current calibration interface is available in this checkout, use it; otherwise rely on the mode table below. If a mode is locked, show the unlock message and stop.

1. Parse the mode from the argument (first word).
2. If no mode given, infer from the user's message using the keyword table below.
3. If still ambiguous, list available modes and ask.
4. Read `modes/<mode>/SKILL.md` completely.
5. If `modes/<mode>/gotchas.yml` exists, read it before executing.
6. Follow the mode's instructions exactly as written.

| Mode | File | Keywords |
|---|---|---|
| dashboard-dev | modes/dashboard-dev/SKILL.md | dashboard:, feed contract:, Tauri: |
| power-platform | modes/power-platform/SKILL.md | intake:, sow:, build powerbi:, optimize dax:, build flow:, build app: |

## Shared resources

Reference data directories available to all modes:
- `data/` — domain-specific data references
- `powerbi/` — Power BI patterns, DAX, M-query references
- `data-visualization/` — visualization best practices
- Other subdirectories contain domain knowledge used by relevant modes
