# Career — Career Pipeline Management

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, check if it's available by running:
   ```python
   py "$PLUGIN/hooks/lib/skill_calibration.py" check-mode career <mode> "<user-message>"
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
| ops | modes/ops/SKILL.md | career:, job search, career ops |
| scan | modes/scan/SKILL.md | scan jobs:, find jobs:, search roles: |
| evaluate | modes/evaluate/SKILL.md | evaluate offer:, evaluate gig:, compare offers: |
| apply | modes/apply/SKILL.md | apply:, write cover letter:, tailor resume: |
| track | modes/track/SKILL.md | track:, pipeline:, update status: |
| pdf | modes/pdf/SKILL.md | resume:, generate pdf:, export resume: |
