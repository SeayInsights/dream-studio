# Security — Build-Time Code Security Enforcement

## Mode dispatch

0. **Progressive disclosure check:** Apply the portable skill contract before dispatching.

1. Parse the mode from the argument (first word).
2. If no mode given, default to `audit`.
3. Read `modes/<mode>/SKILL.md` completely before executing.
4. If `gotchas.yml` exists in this directory, read it before executing.
5. Follow the mode's instructions exactly.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, security audit:, check security:, check codebase security: |
| build | build/SKILL.md | build:security, enforce security:, security check before generate: |

## What This Skill Does

`audit` — retrospective codebase scan. Static passes (gitleaks, bandit, semgrep, pip-audit) followed by LLM semantic pass for rules that require reasoning. Three scope modes: `--changed` (default, files changed vs main), `--full-repo`, `--sample`. Produces a classified report with severity tiers. Never fixes — classify and report only.

`build` — pre-generation enforcement. Runs static-only checks on code about to be generated. Blocks generation on critical/high findings. Warns on medium. Static only (no LLM call in build mode — synchronous, no subprocess).

## Source Authority

Rules are defined in `rules.yml` in this directory. Both modes read from the same rule set. Rules with `action.build_mode: null` apply to audit only.

## Regulatory Reference

Applicable framework standards: see `ds-security/references/regulatory-anchors.md` sections J, L, N.
Rule source list: `docs/architecture/launch-readiness-checklist.md` section 3 (security baseline).
