# Database Build Mode

## Metadata
- **Pack:** quality
- **Mode:** database:build
- **Type:** enforcement
- **Model:** sonnet
- **Inputs:** code_block, generation_context, trigger_type
- **Outputs:** enforcement_decision (block | warn | info | pass)

## Before you start
1. Read `../gotchas.yml` if it exists.
2. Read `../rules.yml` — focus on rules where `action.build_mode` is not null.
3. Static only — no LLM calls in build mode. Synchronous enforcement.

## Trigger
`ds-quality:database:build`, `build:database`, `generate migration:`, `design schema:`, `write query:`

## Purpose
Static enforcement only. Checks code being generated before it is written. Blocks critical/high findings. Warns on medium. Never audits existing code — only inspects the generated block.

No DB connection required. No subprocess calls. File-read only.

---

## Step 1 — Detect Trigger Type

| Trigger | Rules to apply |
|---------|---------------|
| `generate migration` / `write migration` | db-001, db-002, db-005, db-006, db-007, db-010, db-011, db-021 |
| `write query` / `generate query` | db-009, db-014 |
| `design schema` / `create table` | db-001, db-002, db-003, db-004, db-005, db-006, db-007, db-021 |
| Generic (no specific trigger) | All rules where `action.build_mode` is not null |

---

## Step 2 — Static Enforcement

For each applicable rule, run static check on the provided code block:

**db-001 (PK required) — BLOCK on critical:**
- Regex: CREATE TABLE statement without PRIMARY KEY → block

**db-002 (FK ON DELETE) — WARN:**
- Regex: REFERENCES without ON DELETE → warn

**db-005 (money as float) — BLOCK:**
- Regex: REAL|FLOAT|DOUBLE near financial field name → block

**db-006 (UTC timestamps) — WARN:**
- Detect TIMESTAMP without timezone in Postgres; TEXT timestamp without UTC note in SQLite → warn

**db-007 (FK indexes) — WARN:**
- FK column detected without corresponding CREATE INDEX → warn

**db-009 (f-string SQL) — BLOCK:**
- f-string with SQL keywords + variable interpolation → block

**db-010 (schema in VCS) — WARN:**
- CREATE TABLE in non-migration Python file → warn

**db-011 (no DROP without deprecation) — BLOCK:**
- DROP TABLE/COLUMN without deprecation comment → block

**db-014 (cursor pagination) — WARN:**
- OFFSET in generated query → warn (suggest cursor-based alternative)

**db-021 (audit columns) — WARN:**
- CREATE TABLE with > 3 columns missing created_at/updated_at → warn

---

## Step 3 — Format Enforcement Response

For each finding:

```
🔴 BLOCKED [db-{N}] {rule.name}
   Found: {excerpt}
   Why: {one-sentence explanation}
   Fix: {rule.remediation.summary}

🟠 WARNING [db-{N}] {rule.name}
   Found: {excerpt}
   Suggestion: {rule.remediation.summary}
```

If no findings: `✓ Database quality check passed — no critical or high issues detected.`

**Per config.yml:**
- `halt_on_critical_in_build: true` → Critical finding blocks generation
- `warn_on_high_in_build: true` → High finding warns but does not block

Generation proceeds on medium/low findings with a warning.
