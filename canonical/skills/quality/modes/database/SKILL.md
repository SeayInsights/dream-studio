# Database — Schema, Query, Migration, and Backup Quality

## Mode dispatch

0. **Progressive disclosure check:** Apply the portable skill contract before dispatching.

1. Parse the mode from the argument (first word).
2. If no mode given, default to `audit`.
3. Read `modes/<mode>/SKILL.md` completely before executing.
4. If `gotchas.yml` exists in this directory, read it before executing.
5. Follow the mode's instructions exactly.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, database audit:, check schema:, check migrations:, db audit: |
| build | build/SKILL.md | build:database, generate migration:, design schema:, write query: |

## What This Skill Does

`audit` — retrospective database quality scan. Static analysis of migration files + schema patterns, followed by LLM semantic pass for design rules requiring reasoning. Three scope modes: `--changed` (default, files changed vs main), `--full-repo`, `--sample`. Produces a classified report with severity tiers. Never fixes — classify and report only.

`build` — pre-generation enforcement. Runs static-only checks on migration/query/schema code about to be generated. Blocks generation on critical/high findings (e.g., money stored as float, missing PK). Static only — no LLM call, no DB connection required.

## Source Authority

Rules are defined in `rules.yml` in this directory. Both modes read from the same rule set. Rules with `action.build_mode: null` apply to audit only.

## Reference Document

Rule source list: `canonical/skills/quality/references/database-best-practices.md` (sections A-M, LIST-3).

## Skill Boundary

This skill is complementary to `ds-quality:security`. Cross-references apply:
- `sec-002` (parameterized queries, SQLi risk) ↔ `db-009` (f-string SQL, design anti-pattern)
- `sec-013` (PII in logs, runtime) ↔ `db-020` (PII in wrong schema columns, design)
- Backup encryption → `sec-023` (security skill 18.4.3). Strategy/ops → `db-016/017/018` (this skill).

Neither skill duplicates the other. When both fire on the same file, reports cross-reference.
