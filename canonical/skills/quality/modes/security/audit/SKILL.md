# Security Audit Mode

## Metadata
- **Pack:** quality
- **Mode:** security:audit
- **Type:** diagnostic
- **Model:** sonnet
- **Inputs:** source_root, scope_mode, target_path
- **Outputs:** security_audit_report, quality_metrics_update

## Before you start
1. Read `../gotchas.yml` if it exists.
2. Read `../rules.yml` fully — all 22 rules must be loaded.
3. Read `../config.yml` — check token budgets and behavior flags.

## Trigger
`ds-quality:security:audit`, `audit:`, `security audit:`, `check security:`

## Purpose
Audit code against rules.yml. Static checks first, LLM semantic pass for rules requiring reasoning. Classify findings by severity. Report. Never fix in the same invocation — classify and report only.

---

## Step 1 — Determine Scope

Parse invocation flags:

| Flag | Behavior |
|------|----------|
| `--changed` (default) | Files changed vs main branch: `git diff --name-only main...HEAD` |
| `--full-repo` | All files in target matching applicable file types |
| `--sample` | Random N files (N from config.yml `scope_modes.sample_size`, default 50) |
| `--scope <path>` | Single file or directory override |

Filter file list: keep only files whose extension matches at least one rule's `applies_to.file_types`.

**Report header must state:** `Scope: --changed | --full-repo | --sample (N files) | --scope <path> — {file_count} files`

---

## Step 2 — Load Tool Availability

Check which static analyzers are installed:
- `gitleaks`: run `gitleaks version 2>$null` — note Y/N
- `bandit`: run `py -m bandit --version 2>$null` — note Y/N
- `semgrep`: run `semgrep --version 2>$null` — note Y/N
- `pip-audit`: run `py -m pip_audit --version 2>$null` — note Y/N

Record availability. For each missing tool where the rule has `detection.static.fallback_to_llm: true`, flag that rule for the LLM pass instead.

**Per config.yml `log_tool_degradation: true`:** If any tool missing, include in report:
```
⚠ Degraded mode: [tool-name] not installed — LLM fallback active for [rule-ids]
```
This is visible in the report, not a silent failure.

---

## Step 3 — Static Analysis Pass

For each rule where `detection.type` is `static` or `hybrid` AND the tool is available:

**gitleaks (sec-001):**
```
gitleaks detect --source <repo_root> --no-git --report-format json --report-path /tmp/gitleaks-current.json
gitleaks detect --source <repo_root> --report-format json --report-path /tmp/gitleaks-history.json
```
Both current state and git history. Map findings to sec-001.

**bandit (sec-005, sec-021):**
```
py -m bandit -r <in_scope_files> -f json -o /tmp/bandit-output.json
```
Map B106/B107 (hardcoded passwords) → sec-005. Map B303/B304/B305/B308/B413/B501 (weak crypto) → sec-021.

**semgrep (sec-002, sec-013):**
```
semgrep --config p/sql-injection <files> --json -o /tmp/semgrep-sqli.json
semgrep --config p/python.lang.security.audit.logging-pii <files> --json -o /tmp/semgrep-pii.json
```
Map SQL injection findings → sec-002. Map PII-in-logs → sec-013.

**pip-audit (sec-019):**
```
py -m pip_audit --format json -o /tmp/pip-audit-output.json
```
Any known CVE = finding for sec-019. Map severity: CRITICAL/HIGH CVE → sec-019 severity=high; MEDIUM → medium.

**Caching:** Before running, check (rule_id, file_hash) against session cache. Skip if clean result cached.

**Deduplication:** Remove duplicate findings with same (rule_id, file_path, line). Keep the one with higher confidence.

---

## Step 4 — LLM Semantic Pass

For each rule where `detection.type` is `llm` or `hybrid` (or static tool was missing and `fallback_to_llm: true`):

For each in-scope file matching `applies_to.file_types` and `applies_to.languages`:

1. **Cache check:** Skip if (rule_id, sha256(file_content)) found in session cache with clean result.

2. **Extract context** based on `detection.llm.context_scope`:
   - `function`: Extract each function/method separately (grep for `def ` in Python, `function` in JS)
   - `class`: Extract each class block
   - `full_file`: Send entire file content

3. **Prompt per rule per context unit:**

```
You are a security auditor checking one specific rule.

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
  "excerpt": "the specific problematic code, max 100 chars",
  "explanation": "one sentence: what was found and why it violates the rule"
}

Only return finding: true if confidence >= {config.thresholds.min_confidence_for_llm_finding}.
Do not flag theoretical issues. Only flag what you can see in the provided code.

Code ({context_scope} from {filename}):
{code_excerpt}
```

4. Parse response. If `finding: true` AND `confidence >= threshold`: add to findings.
5. Update session cache with (rule_id, sha256(file_content), result).

**Token tracking:** Accumulate token count per LLM call. Stop and warn if approaching budget limit from config.yml for the current scope mode.

---

## Step 5 — Apply Suppressions

For each finding:
1. Check `rule.suppressions[*].path_glob` — if file path matches, remove finding, increment suppressed count
2. Scan file content within ±3 lines of finding location for `rule.suppressions[*].inline_comment` text — if found, suppress
3. Check `../suppressions.yml` (operator-level) for matching rule_id + path pattern. Check `expires` field — if date is past, ignore the suppression entry and log: `⚠ Suppression entry for {rule_id} in suppressions.yml expired {date} — treating as active finding`

---

## Step 6 — Generate Report

```markdown
# Security Audit Report
**Date:** {YYYY-MM-DD}
**Scope:** {scope_mode} — {file_count} files evaluated
**Tool availability:** gitleaks={Y/N} bandit={Y/N} semgrep={Y/N} pip-audit={Y/N}
{if any missing: "⚠ Degraded mode: [tool] not installed — LLM fallback active for [rule-ids]"}
{if any suppression expired: "⚠ Expired suppressions: [list]"}

## Summary

| Severity | Count |
|----------|-------|
| Critical | N |
| High     | N |
| Medium   | N |
| Low      | N |
| Info     | N |
| Suppressed | N |

## Critical Findings
{for each critical finding, sorted by rule_id:}
### {rule.name} — `{file}:{line}`
- **Rule:** {rule.id} | **Severity:** critical
- **Regulatory anchors:** {rule.regulatory_anchors[*].standard joined}
- **Detected by:** {static tool name | LLM semantic pass | LLM fallback (tool missing)}
- **Excerpt:** `{excerpt}`
- **Why this is a finding:** {explanation}
- **Remediation:** {rule.remediation.summary}

## High Findings
{same structure}

## Medium Findings
{same structure}

## Low / Info Findings
{condensed list: rule.name — file:line — one-line explanation}

## Suppressed Findings
{count} findings suppressed ({breakdown by suppression type: path_glob / inline_comment / suppressions.yml})

## Token Usage
- LLM tokens used this run: {count}
- Budget ({scope_mode}): {budget from config.yml}
{if within budget: "✓ Within budget"}
{if over budget: "⚠ Over budget by {N} tokens. Consider --changed scope for routine checks or --sample for estimation."}

## Rules Not Evaluated
{list any rules entirely skipped — e.g., tool missing AND fallback_to_llm: false}
```

---

## Step 7 — Record Quality Metrics

After each completed audit, update `../metadata.yml`:
- `times_used`: increment by 1
- `avg_token_usage`: running average (new_avg = ((old_avg * (times_used-1)) + this_run_tokens) / times_used)
- `avg_execution_time_seconds`: running average
- `last_success`: today's date (on clean run)
- `success_rate`: successful_runs / times_used

**First run only (Batch 7):** Also update `../config.yml` token budget fields with measured values. Replace roadmap estimates with real numbers. See TODO(18.4.1-batch7) comment in config.yml.
