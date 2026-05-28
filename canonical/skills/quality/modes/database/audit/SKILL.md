# Database Audit Mode

## Metadata
- **Pack:** quality
- **Mode:** database:audit
- **Type:** diagnostic
- **Model:** sonnet
- **Inputs:** source_root, scope_mode, target_path
- **Outputs:** database_audit_report, quality_metrics_update

## Before you start
1. Read `../gotchas.yml` if it exists.
2. Read `../rules.yml` fully — all 22 rules must be loaded.
3. Read `../config.yml` — check token budgets and behavior flags.

## Trigger
`ds-quality:database:audit`, `audit:`, `database audit:`, `check schema:`, `db audit:`

## Purpose
Audit schema files, migration files, and query code against rules.yml. Static checks first (sqlparse + regex), then LLM semantic pass for design rules requiring reasoning. Classify findings by severity. Report. Never fix — classify and report only.

---

## Step 1 — Determine Scope

Parse invocation flags:

| Flag | Behavior |
|------|----------|
| `--changed` (default) | Files changed vs main: `git diff --name-only main...HEAD` |
| `--full-repo` | All files matching applicable file types |
| `--sample` | Random N files (N from config.yml `scope_modes.sample_size`, default 50) |
| `--scope <path>` | Single file or directory override |

Filter file list: keep only files whose extension matches at least one rule's `applies_to.file_types`.
Primary target types: `.sql` (migrations), `.py` (query code), `.yml`/`.yaml` (config/backup), `.md` (runbook/docs), `Dockerfile`.

**Note on migration files:** For `--changed` scope, ALWAYS include ALL `.sql` files in `core/event_store/migrations/` even if not in the git diff, because new migrations need schema context from prior migrations to evaluate db-001/002/007/021 correctly.

**Report header must state:** `Scope: --changed | --full-repo | --sample (N files) | --scope <path> — {file_count} files`

---

## Step 2 — Load Tool Availability

Check which static analyzers are installed:
- `sqlfluff`: run `sqlfluff --version 2>$null` — note Y/N (optional; LLM fallback if missing)
- `semgrep`: run `semgrep --version 2>$null` — note Y/N (for db-005, db-009)
- `sqlparse`: `python -c "import sqlparse; print(sqlparse.__version__)"` — note version (installed; use for schema scans)

Record availability. For each missing tool where the rule has `detection.static.fallback_to_llm: true`, flag that rule for the LLM pass instead.

**Per config.yml `log_tool_degradation: true`:** If sqlfluff or semgrep missing, include in report:
```
⚠ Degraded mode: [tool-name] not installed — LLM fallback active for [rule-ids]
```

---

## Step 3 — Static Analysis Pass

### Schema rules via sqlparse (db-001, db-002, db-006, db-007, db-009, db-021)

For each `.sql` migration file in scope:

```python
import sqlparse
statements = sqlparse.parse(sql_content)
# For each CREATE TABLE: extract column list, check for PRIMARY KEY, FK constraints, audit columns
# For each column: check type (db-005 REAL/FLOAT/DOUBLE), check NULL constraints (db-003/004)
# For each .py file: scan for f-string SQL patterns (db-009)
```

**db-001 (PKs):** Flag CREATE TABLE without PRIMARY KEY constraint or column with PRIMARY KEY keyword.

**db-002 (FK ON DELETE):** Flag REFERENCES clause without ON DELETE/ON UPDATE action.

**db-005 (money as float):** Regex: `(REAL|FLOAT|DOUBLE)` within ±2 lines of `(amount|price|cost|fee|payment|balance|total|revenue|tax|charge)` — case insensitive.

**db-007 (indexes on FKs):** Map FK columns to CREATE INDEX statements; flag FK columns without corresponding index.

**db-009 (f-string SQL):** Regex in .py files: `f['"].*\b(SELECT|INSERT|UPDATE|DELETE|WHERE|FROM)\b.*{` — f-string containing SQL keywords with variable interpolation.

**db-021 (audit columns):** For each CREATE TABLE with > 3 data columns, verify `created_at` and `updated_at` are present.

**Caching:** Check (rule_id, file_hash) before scanning. Skip if clean result cached.

---

## Step 4 — LLM Semantic Pass

For each rule where `detection.type` is `llm` or `hybrid` (or static tool missing with fallback_to_llm: true):

For each in-scope file matching `applies_to.file_types` and `applies_to.languages`:

1. **Cache check:** Skip if (rule_id, sha256(file_content)) found with clean result.

2. **Extract context** based on `detection.llm.context_scope`:
   - `function`: Extract each function/method (Python `def`, JS `function`/arrow)
   - `full_file`: Send entire file content (migration files, config files)
   - `config_section`: Extract the relevant config block (connection pool, WAL mode, backup config)

3. **Prompt per rule per context unit:**

```
You are a database quality auditor checking one specific rule.

Rule: {rule.id} — {rule.name}
Severity: {rule.severity}
What to look for: {rule.triggers joined with '; '}
Suppressions (do NOT flag if these apply): {rule.suppressions mapped to plain English}

Analyze the following {context_scope} for this rule only.
Return JSON exactly:
{
  "finding": true | false,
  "confidence": 0.0-1.0,
  "location": "filename:line_number or 'unknown'",
  "excerpt": "the specific problematic code or schema, max 100 chars",
  "explanation": "one sentence: what was found and why it violates the rule"
}

Only return finding: true if confidence >= {config.thresholds.min_confidence_for_llm_finding}.
Do not flag theoretical issues. Only flag what you can see in the provided code.

Code ({context_scope} from {filename}):
{code_excerpt}
```

4. Parse response. If `finding: true` AND `confidence >= threshold`: add to findings.
5. Update session cache.

**Token tracking:** Accumulate token count per LLM call. Stop and warn if approaching budget limit.

---

## Step 5 — Apply Suppressions

Same as security audit:
1. Check `rule.suppressions[*].path_glob`
2. Scan ±3 lines for `rule.suppressions[*].inline_comment`
3. Check `../suppressions.yml` (operator-level) with expiry check

---

## Step 6 — Generate Report

```markdown
# Database Quality Audit Report
**Date:** {YYYY-MM-DD}
**Scope:** {scope_mode} — {file_count} files evaluated
**Tool availability:** sqlfluff={Y/N} semgrep={Y/N} sqlparse={version}
{if any missing: "⚠ Degraded mode: [tool] not installed — LLM fallback active for [rule-ids]"}

## Summary

| Severity | Count |
|----------|-------|
| Critical | N |
| High     | N |
| Medium   | N |
| Suppressed | N |

## Critical Findings
### {rule.name} — `{file}:{line}`
- **Rule:** {rule.id} | **Severity:** critical
- **Detected by:** {static tool | LLM semantic pass | LLM fallback (tool missing)}
- **Excerpt:** `{excerpt}`
- **Why this is a finding:** {explanation}
- **Remediation:** {rule.remediation.summary}
- **Reference:** {rule.remediation.guide_ref}
{if cross-ref security rule: "**Cross-reference:** {sec-NNN} in ds-quality:security covers the security angle of this finding."}

## High / Medium / Low Findings
{same structure, condensed for lower severities}

## Suppressed Findings
{count} suppressed

## Token Usage
- LLM tokens this run: {count}
- Budget ({scope_mode}): {from config.yml}
{within/over budget note}

## Rules Not Evaluated
{list rules skipped — tool missing AND fallback_to_llm: false}
```

---

## Step 7 — Record Quality Metrics

Update `../metadata.yml`:
- `times_used`: increment by 1
- `avg_token_usage`: running average
- `last_success`: today's date
- `success_rate`: successful_runs / times_used

**First run only (Batch 7):** Update `../config.yml` token budget fields with measured actuals.
