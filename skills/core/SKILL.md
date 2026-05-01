# Core — Build Lifecycle

## Mode dispatch

1. Parse the mode from the argument (first word).
2. If no mode given, infer from the user's message using the keyword table below.
3. If still ambiguous, list available modes and ask.
4. Read `modes/<mode>/SKILL.md` completely.
5. If `modes/<mode>/gotchas.yml` exists, read it before executing.
6. Follow the mode's instructions exactly as written.

| Mode | File | Keywords |
|---|---|---|
| think | modes/think/SKILL.md | think:, spec:, shape ux:, design brief:, research: |
| plan | modes/plan/SKILL.md | plan: |
| build | modes/build/SKILL.md | build:, execute plan: |
| review | modes/review/SKILL.md | review:, review code:, review PR: |
| verify | modes/verify/SKILL.md | verify:, prove it: |
| ship | modes/ship/SKILL.md | ship:, pre-deploy:, deploy: |
| handoff | modes/handoff/SKILL.md | handoff: |
| recap | modes/recap/SKILL.md | recap:, session recap: |
| explain | modes/explain/SKILL.md | explain:, how does, walk me through, what is this doing, why does |

## Shared resources

Core shared modules available to all modes (and other packs):
- `git.md` — branch operations, commit formatting, diff reading
- `format.md` — output formatting, checkpoint format, task progress
- `quality.md` — build commands, test execution, quality gate checklist
- `orchestration.md` — subagent spawning, model selection, review loops
- `traceability.md` — TR-ID validation, traceability file structure
- `repo-map.md` — repository structure mapping
