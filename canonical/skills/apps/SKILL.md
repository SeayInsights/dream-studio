# Apps — SaaS, Mobile, Game, and MCP Builders

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
| saas-build | modes/saas-build/SKILL.md | build feature:, build api:, build page:, build supabase: |
| mobile | modes/mobile/SKILL.md | iOS, Android, Swift, SwiftUI, Kotlin, Compose, React Native, Flutter |
| game-dev | modes/game-dev/SKILL.md | game:, game build:, game review:, game QA: |
| mcp-build | modes/mcp-build/SKILL.md | build mcp:, new mcp:, extend mcp: |

`mobile` carries a dedicated subagent (`mobile-developer` — see
`canonical/agents/coverage.yml`); a caller with Task-tool access dispatches it
directly rather than reading the mode file inline. The other three are
inlined directly by whichever skill owns the flow (each is under the
5000-byte isolation threshold).

## Shared resources

Reference data directories available to the relevant modes:
- `mobile/` — native mobile patterns (iOS/Android/RN/Flutter)
- `saas-build/` — animation patterns and component-library references

## Split history

Split out of the `domains` pack (`saas-build`, `mobile`, `game-dev`,
`mcp-build`) — pack-split, 2026-09-24. Neither mode's own content, rules, or
subagent changed; only which pack owns them did.
