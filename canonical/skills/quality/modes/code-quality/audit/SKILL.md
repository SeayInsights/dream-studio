# Code-Quality Audit Mode

## Metadata
- **Pack:** quality
- **Mode:** code-quality:audit
- **Type:** diagnostic
- **Model:** sonnet
- **Inputs:** source_root, scope_mode, target_path
- **Outputs:** code_quality_audit_report, quality_metrics_update

## Before you start
1. Read `../gotchas.yml` if it exists.
2. Read `../rules.yml` fully — all 22 rules must be loaded.
3. Read `../config.yml` — check token budgets, behavior flags, and thresholds.

## Trigger
`ds-quality:code-quality:audit`, `audit:`, `code-quality audit:`, `cq audit:`

## Purpose
Audit Python code against rules.yml for maintainability, correctness, and idiomatic patterns. Static analysis first (AST, pyflakes, regex), then LLM semantic pass for rules requiring design judgment. Classify findings by severity. Report. Never fix — classify and report only.

---

## Step 1 — Determine Scope

| Flag | Behavior |
|------|----------|
| `--changed` (default) | Files changed vs main: `git diff --name-only main...HEAD` |
| `--full-repo` | All files matching applicable file types |
| `--sample` | Random N files (N from config.yml, default 50) |
| `--scope <path>` | Single file or directory override |

**cq-014 (circular imports) note:** This rule defaults to `--full-repo` and `--sample` only. It does NOT run in `--changed` scope unless `config.yml:circular_imports_in_changed: true` is set. Circular imports often involve files the changed file didn't touch, producing confusing findings in PR review.

Filter file list: `.py`, `.ts`, `.js` files matching rules' `applies_to.file_types`.

**Report header must state:** `Scope: --changed | --full-repo | --sample (N files) | --scope <path> — {file_count} files`

---

## Step 2 — flake8 Baseline De-duplication

**Load the flake8 baseline before running any analysis.**

```python
# Load known-debt lines from baseline
baseline_path = "runtime/config/release-gates/flake8-baseline.txt"
baseline_findings = load_flake8_baseline(baseline_path)
# baseline_findings: set of (file_path, line_number) or (file_path, rule_code, line_text)
```

When a code-quality finding co-locates with a baselined flake8 entry:
- Per `config.yml:flake8_baseline.behavior: mark_with_baseline_note`:
  - **Do NOT suppress** the finding — it is still real signal
  - **Annotate** the finding with: `(also in flake8-baseline: known accepted debt)`
  - This makes "things we already know about" visible without drowning the report

This ensures code-quality audit reveals the full scope of signal, while helping operators distinguish new findings from known-debt findings.

---

## Step 3 — Tool Availability

Check which analyzers are installed:
- `pyflakes`: `py -m pyflakes --version` — used for cq-006, cq-015
- `ruff`: `ruff --version` — preferred for many rules; `availability_note` if missing
- `mypy`: `mypy --version` — for type-checking rule; `availability_note` if missing

Per `config.yml log_tool_degradation: true`: include degraded-mode warning in report if ruff/mypy absent.

---

## Step 4 — Static Analysis Pass

For each in-scope file, run applicable static rules:

### AST-based rules (Python stdlib ast — always available)
- **cq-002** (function length): Count AST function body lines. Flag if > `config.thresholds.max_function_lines`.
- **cq-003** (param count): Count AST function arguments (excluding self/cls). Flag if > `config.thresholds.max_param_count`.
- **cq-005** (nesting depth): Walk AST nesting depth of if/for/while/with/try nodes. Flag if > `config.thresholds.max_nesting_depth`.
- **cq-010** (constants): Detect module-level assignments not SCREAMING_SNAKE_CASE.
- **cq-013** (import order): Parse import blocks, verify ordering groups.
- **cq-019** (sleep as sync): Detect sleep() calls inside retry/assertion loops.
- **cq-020** (docstrings): Detect public functions/classes missing docstrings.
- **cq-021** (property side effects): Detect @property with mutation AST nodes.
- **cq-A-explicit** (wildcard imports): Detect `from X import *`.
- **cq-014** (circular imports, full-repo/sample only): Build multi-file import graph. Detect cycles.

### pyflakes-based rules (if installed)
- **cq-006** (silent failures): Detect `except: pass` / `except Exception: pass` with no log/reraise.
- **cq-015** (bare except): Detect `except:` and `except BaseException:`.

### Regex-based rules
- **cq-007** (intent names): Single-char variable names in function bodies (not loop vars).
- **cq-008** (noise words): Class/function names matching *Manager, *Helper, *Util, *Data, *Info.
- **cq-011** (magic literals): Numeric literals (not 0, 1, -1) in function bodies.
- **cq-017** (dead code): Comment blocks containing Python syntax patterns.
- **cq-018** (TODO format): Bare `# TODO:` without context.

**Caching:** Check (rule_id, sha256(file_content)) before scanning. Skip if clean.

---

## Step 5 — LLM Semantic Pass

For rules with `detection.type: llm` or `hybrid` (or tool missing with `fallback_to_llm: true`):

For each in-scope file:
1. **Cache check:** Skip if (rule_id, sha256(file)) cached clean.
2. **Extract context** per `detection.llm.context_scope`:
   - `function`: each function/method separately
   - `class`: each class block
   - `full_file`: entire file content
3. **cq-016 pre-filter:** Before running the LLM for cq-016, call `classify_boundary(func_node)` from `trust_boundary_detection.py`. If result is `"external"`, skip this function for cq-016. Only `"internal"` and `"ambiguous"` functions are evaluated.

**Prompt structure (per rule per context unit):**
```
You are a code quality auditor checking one specific rule.

Rule: {rule.id} — {rule.name}
Severity: {rule.severity}
What to look for: {rule.triggers joined with '; '}
Suppressions (do NOT flag): {rule.suppressions plain English}

Return JSON:
{
  "finding": true | false,
  "confidence": 0.0-1.0,
  "location": "filename:line_number",
  "excerpt": "problematic code, max 100 chars",
  "explanation": "one sentence: what and why"
}

Only return finding: true if confidence >= {config.thresholds.min_confidence_for_llm_finding}.
```

4. Parse. If `finding: true` AND confidence >= threshold: add to findings.
5. Update session cache.

**Token tracking:** Accumulate tokens. Warn if approaching scope budget.

---

## Step 6 — Apply Suppressions

1. Check `rule.suppressions[*].path_glob` — if file path matches, suppress.
2. Scan ±3 lines for `rule.suppressions[*].inline_comment` text — if found, suppress.
3. Check `../suppressions.yml` if exists — operator-level with expiry.

---

## Step 7 — Generate Report

```markdown
# Code-Quality Audit Report
**Date:** {YYYY-MM-DD}
**Scope:** {scope_mode} — {file_count} files evaluated
**Tool availability:** pyflakes={Y/N} ruff={Y/N} mypy={Y/N}
{if any missing: "⚠ Degraded mode: [tool] not installed — LLM fallback active for [rule-ids]"}

## Summary

| Severity | Count | Notes |
|----------|-------|-------|
| Critical | N | cq-006, cq-012, cq-015, cq-019, cq-021 |
| High     | N | |
| Medium   | N | includes N marked "also in flake8-baseline" |
| Low      | N | |

## Critical Findings
### {rule.name} — `{file}:{line}`
- **Rule:** {rule.id} | **Severity:** critical
- **Detected by:** {static tool | LLM semantic | LLM fallback}
- **Excerpt:** `{excerpt}`
- **Why this is a finding:** {explanation}
- **Remediation:** {rule.remediation.summary}
{if cross_references and surface_co_located: "**Also see:** {cross_ref.skill}:{cross_ref.rule_id} — {cross_ref.reason}"}
{if in flake8-baseline: "*(also in flake8-baseline: known accepted debt)*"}

## High / Medium / Low Findings
{same structure, condensed for lower severities}

## Token Usage
- LLM tokens this run: {count}
- Budget ({scope_mode}): {from config.yml}

## Rules Not Evaluated
{list if any skipped}
```

---

## Step 8 — Record Quality Metrics

Update `../metadata.yml`:
- `times_used`: +1
- `avg_token_usage`: running average
- `last_success`: today's date

**First run only:** Update `../config.yml` token budgets with measured actuals.
