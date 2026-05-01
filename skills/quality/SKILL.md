# Quality — Code Quality & Learning

## Mode dispatch

1. Parse the mode from the argument (first word).
2. If no mode given, infer from the user's message using the keyword table below.
3. If still ambiguous, list available modes and ask.
4. Read `modes/<mode>/SKILL.md` completely.
5. If `modes/<mode>/gotchas.yml` exists, read it before executing.
6. Follow the mode's instructions exactly as written.

| Mode | File | Keywords |
|---|---|---|
| debug | modes/debug/SKILL.md | debug:, diagnose: |
| polish | modes/polish/SKILL.md | polish ui:, critique design:, redesign:, make it premium: |
| harden | modes/harden/SKILL.md | /harden, harden audit, harden fix |
| secure | modes/secure/SKILL.md | secure:, security review:, audit code: |
| structure-audit | modes/structure-audit/SKILL.md | /structure-audit, audit structure: |
| learn | modes/learn/SKILL.md | learn:, capture lesson: |
| coach | modes/coach/SKILL.md | /coach, workflow coaching: |
