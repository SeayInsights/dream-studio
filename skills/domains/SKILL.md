# Domains — Stack-Specific Builders

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, check if it's available by running:
   ```python
   py "../../hooks/lib/skill_calibration.py" check-mode domains <mode> "<user-message>"
   ```
   If exit code is non-zero, the mode is locked. Show the unlock message (from stdout) and stop.
   If exit code is zero, continue to step 1. If unlock notifications are printed, show them to the user.

1. Parse the mode from the argument (first word).
2. If no mode given, infer from the user's message using the keyword table below.
3. If still ambiguous, list available modes and ask.
4. Read `modes/<mode>/SKILL.md` completely.
5. If `modes/<mode>/gotchas.yml` exists, read it before executing.
6. Follow the mode's instructions exactly as written.

| Mode | File | Keywords |
|---|---|---|
| game-dev | modes/game-dev/SKILL.md | game:, game build:, game review:, game QA: |
| saas-build | modes/saas-build/SKILL.md | build feature:, build api:, build page:, build supabase: |
| mcp-build | modes/mcp-build/SKILL.md | build mcp:, new mcp:, extend mcp: |
| dashboard-dev | modes/dashboard-dev/SKILL.md | dashboard:, feed contract:, Tauri: |
| client-work | modes/client-work/SKILL.md | intake:, sow:, build powerbi:, optimize dax:, build flow:, build app: |
| design | modes/design/SKILL.md | design art:, design poster:, canvas:, brand:, ad creative: |

## Shared resources

Reference data directories available to all modes:
- `data/` — domain-specific data references
- `powerbi/` — Power BI patterns, DAX, M-query references
- `data-visualization/` — visualization best practices
- Other subdirectories contain domain knowledge used by relevant modes
