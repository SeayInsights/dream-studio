# Database Mode — Core Imports

## Imported Modules

### ds-core/git.md
**Usage:** Scope determination for `--changed` mode. Get list of files changed vs. base branch.
**Where used:** `audit/SKILL.md` — Step 1 (scope determination)
**Pattern used:** `git diff --name-only main...HEAD` (or `origin/main...HEAD` in CI)
**Impact if changed:** `--changed` scope breaks; fall back to `--full-repo` until fixed.

### canonical/skills/quality/references/database-best-practices.md
**Usage:** Authoritative source for all 22 rule definitions. Sections A-M, LIST-3.
**Where used:** `rules.yml` — each rule's `source.list`, `source.section`, `source.item` fields.
**Impact if changed:** `source.item` text in rules.yml may need updating. No runtime behavior change — source attribution is informational only.

## Static Analysis Tools

### sqlparse (Python, installed)
**Usage:** SQL tokenization for schema rules — detect missing PK/FK patterns in migration files, find f-string SQL construction (db-009), identify money columns using REAL/FLOAT (db-005).
**Where used:** `audit/SKILL.md` — static analysis pass for rules with `detection.type: static`.
**Impact if unavailable:** Python stdlib fallback (string pattern matching). Reduced precision for complex SQL patterns; LLM fills the gap.

### sqlite3 (Python stdlib, always available)
**Usage:** Live schema inspection when DB path is accessible. Cross-validates static migration file analysis.
**Where used:** `audit/SKILL.md` — optional schema validation step.
**Impact if unavailable:** static-only mode (migration file analysis only, no live schema check).

## Skill Boundary Cross-References

### ds-quality:security (complementary skill)
**Not a dependency — a boundary partner.**
Rules that cross-reference:
- `db-009` ↔ `sec-002`: f-string SQL (design) ↔ parameterized queries (injection). Both may fire on the same code with different remediation context.
- `db-020` ↔ `sec-013`: PII column design ↔ PII in runtime logs. Different layers, complementary.
- `db-016/017/018` ↔ `sec-023` (future 18.4.3): backup strategy ↔ backup encryption. Documented split.

**Do NOT call ds-quality:security from this skill.** They run independently. Cross-references are text notes, not runtime invocations.

## Maintenance Notes

This skill intentionally does NOT overlap with `ds-security:dast` (web dynamic testing) or `ds-quality:harden` (project structure). Those skills have non-overlapping concerns.

When `sqlfluff` becomes available:
- Wire it for SQL syntax linting in audit mode (db-001 through db-009 static pass)
- Add `sqlfluff` to `tools_optional` list in metadata.yml
- Update `detection.static.tool: sqlfluff` for applicable rules in rules.yml
