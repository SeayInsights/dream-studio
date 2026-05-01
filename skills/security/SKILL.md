# Security — Enterprise Security Analysis

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, check if it's available by running:
   ```python
   py "$PLUGIN/hooks/lib/skill_calibration.py" check-mode security <mode> "<user-message>"
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
| scan | modes/scan/SKILL.md | scan:, scan org:, run security scan: |
| dast | modes/dast/SKILL.md | dast:, web scan:, pen test web: |
| binary-scan | modes/binary-scan/SKILL.md | binary-scan:, scan binary:, analyze exe: |
| mitigate | modes/mitigate/SKILL.md | mitigate:, how to fix findings:, generate mitigations: |
| comply | modes/comply/SKILL.md | comply:, compliance map:, SOC 2:, NIST:, audit evidence: |
| netcompat | modes/netcompat/SKILL.md | netcompat:, Zscaler check:, proxy compatibility: |
| dashboard | modes/dashboard/SKILL.md | security dashboard:, export dataset: |
