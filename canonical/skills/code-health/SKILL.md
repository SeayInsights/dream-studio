# Code Health — Quality, Architecture, and Test Discipline

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
| code-quality | modes/code-quality/SKILL.md | audit:, code-quality audit:, cq audit:, check code quality:, build:code-quality |
| architecture | modes/architecture/SKILL.md | (no keyword trigger — invoke by explicit mode name) |
| structure-audit | modes/structure-audit/SKILL.md | /structure-audit, audit structure: |
| audit | modes/audit/SKILL.md | audit:health, audit:consolidate |
| groom | modes/groom/SKILL.md | groom:, groom lessons:, apply lessons: |
| testing | modes/testing/SKILL.md | audit:, testing audit:, check tests:, test audit:, build:testing |
| debug | modes/debug/SKILL.md | debug:, diagnose: |

## Split history

Split out of the `quality` pack (`code-quality`, `architecture`, `structure-audit`,
`audit`, `groom`, `testing`, `debug`) — pack-split, 2026-09-25. None of the seven
modes' own content or rules changed; only which pack owns them did. `on-quality-score`,
`on-structure-check`, and `on-agent-correction` moved with them (runtime/hooks/code-health/);
`on-security-scan` stayed with `quality` (harden's security scan, not this pack's concern).
The two structure rule files (`structure/architecture.md`, `structure/fsc.md`) moved with
`structure-audit`, their only referrer.
