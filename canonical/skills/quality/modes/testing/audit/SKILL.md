# Testing Audit Mode

## Metadata
- **Pack:** quality
- **Mode:** testing:audit
- **Type:** diagnostic
- **Model:** sonnet
- **Inputs:** source_root, scope_mode, target_path
- **Outputs:** testing_audit_report, quality_metrics_update

## Before you start
1. Read `../gotchas.yml` — contains Dream Studio-specific positive patterns and known false-positive risks.
2. Read `../rules.yml` fully — all 15 rules must be loaded.
3. Read `../config.yml` — check scope settings, critical_path_globs, coverage gap threshold, and LLM batch size.

## Trigger
`ds-quality:testing:audit`, `testing audit:`, `check tests:`, `test audit:`

## Purpose
Audit test files against rules.yml. Static checks first (ast, coverage.py), then LLM semantic pass for rules requiring judgment. Never fixes — classifies and reports only.

---

## Step 1 — Determine Scope

Parse invocation flags:

| Flag | Behavior |
|------|----------|
| `--changed` (default) | Test files changed vs main: `git diff --name-only main...HEAD` filtered to test files |
| `--full-repo` | All test files under testpaths from pyproject.toml (LLM in batches of `config.testing_audit.llm_batch_size`) |
| `--sample` | N files per top-level test directory (N from config `scope_modes.sample_size`, default 10) |
| `--scope <path>` | Single file or directory override |

Filter: keep only files matching `test_*.py` pattern under test directories.

**For --sample:** Enumerate top-level test directories (unit/, integration/, evals/, and root test files). Select N random files from each. Report: `Scope: --sample (N per dir, M total files)`.

**Report header must state:** `Scope: --changed | --full-repo | --sample (N/dir) | --scope <path> — {file_count} test files`

**Dream Studio note (from config.yml known_context):** The pre-push hook runs tests/evals/ only. Full suite runs remote CI. This is NOT a tst-014 violation — include as an informational note in the report, not a finding.

---

## Step 2 — Load Coverage Data

Check for coverage data:
```
coverage report --format=json > /tmp/coverage_report.json
```

If coverage data available:
- Parse for module-level coverage %
- Note fail_under from pyproject.toml
- Compute enforcement gap: gap = actual_total - fail_under

If coverage data unavailable (no .coverage file): note in report. tst-001 falls back to path-scan.

---

## Step 3 — Static Analysis Pass

### tst-001 (coverage-based existence check)
If coverage data available: flag source modules with 0% line coverage (excluding suppressions).
If path-scan fallback: flag source modules with no test file import/reference.
Severity: critical. List flagged modules with actual coverage %.

### tst-003 (determinism patterns — static candidates)
For each test function in scope, use ast to detect:
- `datetime.now()` / `datetime.utcnow()` without surrounding `@patch` or `monkeypatch`
- `time.time()` / `time.monotonic()` without patch
- `random.*()` without patch
- `uuid.uuid4()` used in assertion context

Report as: **CANDIDATE (high severity)** — pattern detected; LLM confirmation required for critical escalation.

### tst-006 (assertion count — static proxy)
Count `assert` statements per test function. Flag functions with > 5 assertions as LLM review candidates.

### tst-007 (naming — static filter)
Flag test functions with generic names (test_1, test_it, test_check, test_run, test_main) as LLM candidates.

### tst-010 (coverage gap)
If coverage data: compute gap = actual_total_% - fail_under.
If gap > config.coverage.gap_high_severity_threshold (default 22): finding = high severity.
Always report both numbers.

### tst-011 (sleep() — static)
Use ast to flag any `time.sleep()` or `asyncio.sleep()` in test function bodies. Severity: critical. No LLM pass needed.

### tst-012 (fixture scope — static candidates)
Parse conftest.py and test files for `@pytest.fixture(scope='session')` or `scope='module'`. Flag as LLM candidates.

### tst-013 (file organization)
For each source file in configured paths: check if corresponding test file exists. Low severity.

### tst-014 (CI config)
Check .github/workflows/*.yml for pytest/test execution step. Critical if absent.

### tst-015 (slow unit tests)
Parse tests/unit/**/*.py only: flag sqlite3.connect(), requests.get(), httpx.get(), subprocess.run(). Medium severity.

---

## Step 4 — LLM Semantic Pass (batched)

For rules requiring LLM: tst-002, tst-004, tst-005, tst-007 (confirmation), tst-008, tst-009, tst-012 (confirmation).
For rules with static candidates needing confirmation: tst-003 (confirm-to-critical), tst-006 (confirmation).

**Batch size:** `config.testing_audit.llm_batch_size` (default 20 test files per batch).

For each batch:
1. Cache check: (rule_id, sha256(file_content)) — skip if clean result cached.
2. Extract context based on rule's `detection.llm.context_scope`:
   - `function`: each test function body
   - `full_file`: entire test file
3. Send prompt per rule per context unit (prompt from rules.yml).
4. Parse response. If `finding: true` AND `confidence >= 0.75`: add to findings.
5. For tst-003 candidates: LLM confirmation escalates from high to critical.
6. Update session cache.

**For tst-002 and tst-008 specifically:** Track the LLM calls and any human-reviewed disagreements for the demotion criterion (>20% disagreement → demote to requires_human_review: true). Record in verification paste.

**Token tracking:** Accumulate per batch. Warn if approaching budget.

---

## Step 5 — Apply Suppressions

For each finding:
1. Check `rule.suppressions[*].path_glob` — skip if file matches
2. Check ±3 lines for `rule.suppressions[*].inline_comment`
3. Check `../suppressions.yml` if it exists (operator-level suppressions with expiry)

---

## Step 6 — False-Positive Check (mandatory on first audit)

For tst-001 and tst-003, perform the false-positive check:

**tst-001:** Of the modules flagged as 0% coverage, verify:
- Some might be tested via integration tests not captured by coverage run
- Some might be pure re-exports or stub modules
- Report: N flagged, M confirmed-real after review

**tst-003:** Of the determinism candidates from static pass:
- Report: N candidates (static), M confirmed-critical (LLM confirmed non-determinism reaches assertion)
- This is the calibration validation: the ratio should show static overshoots, LLM filters to real criticals

---

## Step 7 — Generate Report

```markdown
# Testing Quality Audit Report
**Date:** {YYYY-MM-DD}
**Scope:** {scope_mode} — {file_count} test files evaluated
**Coverage data:** {available/unavailable} | actual: {actual_%} | fail_under: {fail_under} | gap: {gap} points
{if gap > threshold: "⚠ Enforcement gap: gate permits up to {gap}-point coverage regression before triggering"}

## Summary

| Severity | Count |
|----------|-------|
| Critical | N |
| High     | N |
| Medium   | N |
| Low      | N |
| Suppressed | N |

## Critical Findings
### {rule.name} — `{file}:{function}` [{rule_id}]
- **Severity:** critical | **Detected by:** {static/LLM semantic/tool}
- **Excerpt:** `{excerpt}`
- **Why:** {explanation}
- **Remediation:** {rule.remediation.summary}
{if cross-reference: "**Cross-reference:** {rule_id} in ds-quality:{skill} covers the {angle} angle."}

{tst-003 confirmed-critical findings labeled: "CONFIRMED CRITICAL — non-determinism verified to reach assertion"}
{tst-003 unconfirmed candidates: note in High section as "CANDIDATE — confirm whether assertion is affected"}

## High / Medium / Low Findings
{same structure, condensed}

## False-Positive Check (first audit)
- tst-001: {N} flagged, {M} confirmed-real after integration-test review
- tst-003: {N} static candidates, {M} confirmed-critical (LLM confirmation rate: {%})
- tst-002 agreement rate: {%} | tst-008 agreement rate: {%}
{if any rate < 80%: "⚠ Demotion criterion approaching: demotion at < 80% agreement"}

## Informational Context (not findings)
- Dream Studio CI pattern: pre-push hook runs tests/evals/ only (documented decision; not tst-014 violation)
- conftest.py early isolation: module-import-time env var setting recognized as positive pattern

## Token Usage
- LLM tokens this run: {count}
- Budget ({scope_mode}): {from config.yml} [estimate — first real measurement]

## Rules Not Evaluated
{list rules skipped — requires tool not available}
```

---

## Step 8 — Record Quality Metrics

Update `../metadata.yml`:
- `times_used`: increment by 1
- `avg_token_usage`: running average
- `last_success`: today's date
- `success_rate`: successful_runs / times_used

**First run only:** Update `../config.yml` budget fields with measured actuals. Report in verification paste.
