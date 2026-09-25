# Release — Launch and Operational Readiness

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
| ops | modes/ops/SKILL.md | (no keyword trigger — invoke by explicit mode name) |
| pre-launch | modes/pre-launch/SKILL.md | (no keyword trigger — invoke by explicit mode name) |

Neither mode declares a `triggers:` entry in `metadata.yml` or a `## Trigger`
section in its own `SKILL.md`, so neither infers from natural-language
intent (step 2 of the dispatch algorithm above). Both are still reachable
by explicit mode name (step 1) now that this table names them — under
`quality`, neither mode appeared in that pack's own top-level dispatch
table at all, which is what made them genuinely unreachable there.

## Split history

Split out of the `quality` pack (`ops`, `pre-launch`) — pack-split,
2026-09-25. Neither mode's own content or rules changed; only which pack
owns them did.
