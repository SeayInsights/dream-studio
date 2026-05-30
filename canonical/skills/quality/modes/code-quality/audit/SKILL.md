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
Audit code against rules.yml for maintainability, correctness, and idiomatic patterns. Works on Python, TypeScript, and JavaScript. For Python: full static analysis (AST, pyflakes, regex). For TypeScript/JavaScript: AST-described rules degrade to LLM semantic pass (Python ast cannot parse TS/JS; the concepts are universal). Seven rules are genuinely Python-specific (import ordering, bare except, docstrings, sleep-as-sync, wildcard imports, circular imports) — they skip gracefully on non-Python files without false-firing. Static analysis first, then LLM semantic pass for rules requiring design judgment. Classify findings by severity. Report. Never fix — classify and report only.

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

Baseline overlap detection is implemented in `canonical/skills/quality/shared/flake8_baseline.py`:

```python
from canonical.skills.quality.shared.flake8_baseline import (
    load_flake8_baseline, is_baselined, BASELINE_ANNOTATION
)

baseline = load_flake8_baseline("runtime/config/release-gates/flake8-baseline.txt")
# baseline: set of (relative_file_path, line_number) tuples
# Returns empty set if file missing — never crashes
```

When a code-quality finding co-locates with a baselined flake8 entry:
- Per `config.yml:flake8_baseline.behavior: mark_with_baseline_note`:
  - **Do NOT suppress** the finding — it is still real signal
  - Call `is_baselined(finding.file, finding.line, baseline)` — if True, append `BASELINE_ANNOTATION` to the finding's explanation: `(also in flake8-baseline: known accepted debt)`
  - This makes "things we already know about" visible without drowning the report

This ensures code-quality audit reveals the full scope of signal, while helping operators distinguish new findings from documented technical debt (736 baseline entries as of 18.4.3).

---

## Step 3 — Tool Availability

Check which analyzers are installed:
- `pyflakes`: `py -m pyflakes --version` — used for cq-006, cq-015
- `ruff`: `ruff --version` — preferred for many rules; `availability_note` if missing
- `mypy`: `mypy --version` — for type-checking rule; `availability_note` if missing

Per `config.yml log_tool_degradation: true`: include degraded-mode warning in report if ruff/mypy absent.

---

## Step 4 — Static Analysis Pass

**For Python files (`.py`):** Run all applicable static rules below.
**For TypeScript/JavaScript files (`.ts`, `.js`):** Run regex-based rules only. AST-based rules automatically degrade to LLM semantic pass (Python ast cannot parse TS/JS — `fallback_to_llm: true` fires). Seven Python-specific rules skip entirely (`languages: [python]`).

### AST-based rules (Python ast for Python; LLM semantic fallback for TypeScript/JavaScript)
- **cq-002** (function length): Python: AST line count. TS/JS: LLM counts function body lines.
- **cq-003** (param count): Python: AST param count (excluding self/cls). TS/JS: LLM counts parameters.
- **cq-005** (nesting depth): Python: AST nesting depth. TS/JS: LLM measures conditional/loop nesting.
- **cq-010** (constants): Python: AST module-level constant detection. TS/JS: LLM identifies non-SCREAMING constant declarations.
- **cq-021** (property side effects): Python: AST @property mutation detection. TS/JS: LLM identifies get methods with mutations.

### Python-only rules (skip gracefully on non-Python files — no findings, no errors)
- **cq-013** (import order): Python import system — skip on TS/JS.
- **cq-014** (circular imports): Python import graph — skip on TS/JS. Cross-reference dep-007 (calibrated version with TYPE_CHECKING exclusion).
- **cq-015** (bare except): Python exception syntax — skip on TS/JS.
- **cq-019** (sleep as sync): Python time.sleep/asyncio.sleep — skip on TS/JS.
- **cq-020** (docstrings): Python docstring convention — skip on TS/JS.
- **cq-A-explicit** (wildcard imports): Python `from X import *` — skip on TS/JS.
Note: cq-006 uses pyflakes (Python-specific tool) but has `fallback_to_llm: true` — on TS/JS, LLM handles silent-failure detection.

### pyflakes-based rules (if installed; LLM fallback if not)
- **cq-006** (silent failures): Detect `except: pass` / `except Exception: pass` with no log/reraise. Python: pyflakes. Others: LLM.
- **cq-015** (bare except): Detect `except:` and `except BaseException:`. Python only.

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
