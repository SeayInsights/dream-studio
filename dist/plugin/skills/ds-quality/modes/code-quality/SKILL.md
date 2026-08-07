# Code-Quality — Code Maintainability, Correctness, and Idiom

## Mode dispatch

0. **Progressive disclosure check:** Apply the portable skill contract before dispatching.

1. Parse the mode from the argument (first word).
2. If no mode given, default to `audit`.
3. Read `modes/<mode>/SKILL.md` completely before executing.
4. If `gotchas.yml` exists in this directory, read it before executing.
5. Follow the mode's instructions exactly.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, code-quality audit:, cq audit:, check code quality: |
| build | build/SKILL.md | build:code-quality, generate:, write:, code-quality check before generate: |

## What This Skill Does

`audit` — retrospective code quality scan. Static analysis (AST, pyflakes, regex) followed by LLM semantic pass for rules requiring design judgment. Three scope modes: `--changed` (default), `--full-repo`, `--sample`. Produces classified report. Never fixes — classify and report only.

`build` — static-only enforcement on code about to be generated. Applies the 12 static rules only. No LLM call. Blocks on critical findings; warns on high. Exposes a callable self-audit interface for ds-skills:build-mode-orchestration (18.8.1) to wire.

## Source Authority

Rules are defined in `rules.yml` in this directory. Both modes read from the same rule set. Rules with `action.build_mode: null` are audit-only.

## Reference Documents

- Rule source: `canonical/skills/quality/references/code-writing-best-practices.md` (LIST-4, sections A-N)
- Shared utility: `canonical/skills/quality/shared/trust_boundary_detection.py` (external entry point detection)

## Three-Way Skill Boundary

This skill is complementary to `ds-quality:security` and `ds-quality:database`.

- **Security** owns: adversarial misuse, breach risk, injection vectors (sec-001 through sec-025)
- **Database** owns: schema design, query patterns, migration safety (db-001 through db-022)
- **Code-quality** owns: maintainability, correctness, idiom (cq-001 through cq-A-explicit)

Cross-references apply: cq-016 ↔ sec-003; cq-006/cq-015 ↔ sec-013. No rule ID is duplicated across skills. When two skills fire on the same line, the findings report renders them together with cross-reference notes (see `cross_references` field in rules.yml).

**External entry points:** Code-quality's cq-016 (validate-at-internal-boundaries) explicitly excludes external trust boundaries (FastAPI/Flask routes, Click commands, Dream Studio hook handlers, argparse subcommands). Security skill's sec-003 owns those. Detection via `canonical/skills/quality/shared/trust_boundary_detection.py`.

## Build Mode Self-Audit

When other skills generate Python, they may invoke code-quality's build mode to validate the generated code. This is a callable interface — invocation wiring is handled by ds-skills:build-mode-orchestration (18.8.1, future). Code-quality's build mode applies static rules only (no LLM recursion) per Decision 8 (18.4.3).
