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

## Cross-Database Support

The database skill runs against all SQL and NoSQL database backends. Rules use the
detected database type (from `detect_stack().database_type`) to dispatch engine-specific
detection notes while preserving universal rule semantics.

**Universal rules (14):** Schema integrity (db-001–007, db-021) and query rules (db-008–015, db-020).
SQL DDL syntax (PRIMARY KEY, FOREIGN KEY, CHECK, CREATE INDEX) is identical across
SQLite, Postgres, and MySQL. LLM handles semantic classification (PII, migration safety).

**Engine-specific rules (7):** db-012 (connection pool), db-013 (statement timeout),
db-016–018 (backups + RTO/RPO), db-019 (EOL version), db-021. Concept is universal;
detection branches on detected database type. D1/managed databases skip operational
checks where the platform handles them automatically.

**SQLite/D1-only rule:** db-022 (WAL mode + D1 eventual consistency). Skips on
non-SQLite projects (Postgres, MySQL, MongoDB, DynamoDB).

**db-009 ↔ sec-002 boundary:** db-009 fires on string-formatted SQL (design smell, medium severity).
sec-002 fires on the same pattern from the injection-risk angle (critical severity). Both may
fire on the same code — they are complementary, not duplicate.

**Database-type detection:** `control/analysis/stacks/detector.py._detect_database_type()`
reads package.json deps, pyproject.toml, go.mod, Cargo.toml, and wrangler.jsonc to identify
the primary database type. Result stored in `DetectedStack.database_type`.

**Proving grounds:**
- DreamySuite (Cloudflare D1 / SQLite-compatible): schema + migration + query rules
- dream-studio-clean (Python + SQLite): operational rules
