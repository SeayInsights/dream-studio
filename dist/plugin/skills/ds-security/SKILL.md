---
name: ds-security
description: 'Enterprise security analysis — automated scanning, compliance mapping, mitigation generation, network compatibility, and executive dashboards. Use for: scan:, dast:, binary-scan:, mitigate:, comply:, netcompat:, dashboard:, review:'
---

# Security — Enterprise Security Analysis

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
| scan | modes/scan/SKILL.md | scan:, scan org:, run security scan: |
| review | modes/review/SKILL.md | review:, security review:, review PR:, code review:, pre-commit security:, audit:, security audit:, check security:, check codebase security:, build:security, enforce security:, security check before generate: |
| dast | modes/dast/SKILL.md | dast:, web scan:, pen test web: |
| binary-scan | modes/binary-scan/SKILL.md | binary-scan:, scan binary:, analyze exe: |
| mitigate | modes/mitigate/SKILL.md | mitigate:, how to fix findings:, generate mitigations: |
| comply | modes/comply/SKILL.md | comply:, compliance map:, SOC 2:, NIST:, audit evidence:, compliance audit:, gdpr audit:, privacy audit:, dbc audit: |
| netcompat | modes/netcompat/SKILL.md | netcompat:, Zscaler check:, proxy compatibility: |
| dashboard | modes/dashboard/SKILL.md | security dashboard:, export dataset: |

## Scripts and templates: `<skill-dir>`

**`<skill-dir>` in the mode docs is this skill's own directory**: the one holding this `SKILL.md`
and `modes/`. Claude Code reports it when the skill loads. The scripts the modes run (the
`etl/*.py` parsers, `scan_coverage.py`, `header_analysis.py`) and the templates they render or
read (`binary/`, `dast/`, `semgrep-rules/`, `github-actions/`, `compliance/`, `mitigations/`,
`powerbi/`) are shipped inside it, under `<skill-dir>/templates/security/`, with the layout the
scripts expect (`etl/` beside `compliance/` and `mitigations/`). The scripts run from any
working directory, import only their own directory, and find the Dream Studio home from
`DREAM_STUDIO_HOME`, else the home a self-installed app records in its venv, else `~/.dream-studio` (the same rule as the platform's, without importing it). They need Python 3.12 and, for some, PyYAML.

In a source checkout of dream-studio the same files are at `templates/security/` in the
repository root, with no `<skill-dir>` in front: `<skill-dir>/templates/security/etl/parse_dast.py`
is `templates/security/etl/parse_dast.py`. Never substitute a repository-relative path when the
skill is installed.
