# Types-Deps — Audit Mode

## Scope variants

Three scope modes (same pattern as testing skill):

| Flag | Files analyzed | When to use |
|------|----------------|-------------|
| `--changed` (default) | Python files changed vs main | PR review — fast, targeted |
| `--full-repo` | All Python source files | Baseline audit, first run |
| `--sample` | 10 files per top-level source dir | Representative check on large repos |

**Language detection:** Use `detect_stack()` from `control/analysis/stacks/detector.py`.
- If `python` detected → use Python audit steps below
- If `typescript`/`javascript` detected → use TypeScript equivalents in each step
- If both → run both
**File scoping:** Python: `*.py` (excluding tests/). TypeScript: `*.ts`, `*.tsx` (excluding *.test.ts, *.spec.ts, node_modules/).

**Important:** Config rules (typ-001, dep-001, dep-002, dep-003) always run regardless of
scope flag. They are project-level findings, not per-file findings. You cannot scope them
out of an audit — they reflect the project's setup, not individual files.

## Audit process (8 steps)

### Step 1 — Config rules (always, all scopes)

Run all four project-level config rules in order:

**typ-001 — Type-checker scope:**
1. Discover source dirs (pyproject.toml or root package scan; see config.yml).
2. Find type checker config (pyrightconfig.json → mypy.ini → pyproject.toml).
3. Compare coverage to source dirs. Report gap as high; absent checker as critical.

**typ-001 TypeScript:** Find tsconfig.json. Check "include"/"exclude" arrays. Compare to src directories containing .ts files. Report uncovered dirs. No tsconfig → critical.

**dep-001 — CVE gate enforcement:**
1. Scan CI yaml files for CVE tool steps + continue-on-error.
2. If non-blocking (or absent): run `python -m pip_audit -r <requirements_file> --format json`
   if pip-audit is available.
3. Set severity from real output (critical if CVEs present; high if clean).

**dep-001 TypeScript/JS:** Scan CI yaml for npm audit/yarn audit steps + continue-on-error. Run `npm audit --json` if available. Report enforcement gaps.

**dep-002 — Lock file completeness:**
1. Check for production lock file (see lock_file_patterns in config.yml).
2. Check for dev lock file (dev_lock_patterns).
3. Check if requirements files use == pins throughout as alternative.
4. Report missing locks; note library-vs-application context.

**dep-002 TypeScript/JS:** Check for package-lock.json/yarn.lock/pnpm-lock.yaml. Check sync state (package.json newer than lock → out of sync). No separate dev lock — one lock covers all.

**dep-003 — License gate:**
1. Check for pip-licenses, liccheck, fossa in requirements and CI.
2. Check for license config files (.licenserc, liccheck.ini, etc.).
3. If absent: report high with tool-pointing remediation (no allowlist prescription).

**dep-003 TypeScript/JS:** Check for license-checker in devDependencies + CI license step with --failOn. No license gate configured → high.

### Step 2 — Determine in-scope files

Apply the scope flag:

**Python:** `*.py` files under source dirs, excluding tests/
- `--changed`: `git diff --name-only main...HEAD` filtered to `*.py`, excluding tests/
- `--full-repo`: all `*.py` under source dirs discovered in typ-001 step
- `--sample`: 10 files per top-level source dir

**TypeScript:** `*.ts`, `*.tsx` files under src/, app/, lib/, components/, hooks/ — excluding `*.test.ts`, `*.spec.ts`, `*.d.ts`, `node_modules/`, `dist/`, `.next/`
- `--changed`: `git diff --name-only main...HEAD` filtered to `*.ts`, `*.tsx`, applying exclusions above
- `--full-repo`: all `*.ts`, `*.tsx` under TypeScript source dirs discovered in typ-001 step
- `--sample`: 10 files per top-level TypeScript source dir

### Step 3 — Static pass: typ-003, typ-004

Run static checks on all in-scope files simultaneously (no LLM needed):

**typ-003 (type:ignore hygiene):** Grep for `# type: ignore` patterns. Flag any lacking
an explanatory comment after the suppression. Report file + line + full comment.

**typ-003 TypeScript:** Grep for `// @ts-ignore` / `// @ts-expect-error` without trailing justification. Skip on Go/Rust (skip_on declared in rule).

**typ-004 (missing return annotations):** AST parse; find public functions without `->`.
Apply exemptions (dunder methods, @property, @classmethod, test files).

**typ-004 TypeScript:** Find exported functions without return type annotation. Same summary format as Python.

### Step 4 — Static pass + auto-accept: typ-002 (Any leakage candidates)

1. AST parse in-scope files; find `Any` in annotation positions.
2. Apply auto-accept rules (dict[str,Any], boundary param names, boundary fn prefixes).
   Auto-accepted instances are recorded as "boundary Any — accepted" in the report.
3. Remaining instances → candidate pool for LLM confirmation.
4. Report candidate count before sending to LLM.

**typ-002 TypeScript:** Find `any` annotations in .ts/.tsx files. Same auto-accept patterns (boundary param names, JSON parsing context). Remaining → LLM confirmation queue.
LLM prompt applies to TypeScript with the same boundary classification logic.

### Step 5 — Static pass + TYPE_CHECKING exclusion: dep-007 (circular import candidates)

1. Build import graph from all source files (all scopes for dep-007 — cycles can span
   files not in the changed set).
2. At AST level: exclude TYPE_CHECKING-guarded imports and function-level imports.
3. Run SCC / DFS cycle detection on pruned graph.
4. Remaining cycles → candidate pool for LLM confirmation.
5. Report candidate count before sending to LLM.

### Step 6 — LLM confirmation pass (typ-002 and dep-007 candidates)

Send candidates to LLM in batches (see llm_batch_size in config.yml).

**typ-002 batching:** Group up to 20 Any-candidate functions per LLM call. Each call
returns confirmed interior-leakage or benign-boundary verdict.

**dep-007 batching:** Send each cycle with all its constituent module excerpts. One LLM
call per cycle (cycles are usually small — 2-4 modules). Returns real-runtime-cycle or
broken-at-runtime verdict.

Only finding: true with confidence >= 0.75 is promoted to a finding.

### Step 7 — False-positive check (mandatory before reporting)

Before assembling the final report:
- Count typ-002: flagged candidates vs. confirmed interior-leakage. If > 80% return
  benign-boundary, note this in the report summary and suggest expanding auto-accept patterns.
- Count dep-007: flagged candidates vs. confirmed real cycles. If the majority are
  broken-at-runtime, the AST exclusion may have missed a pattern — note it.

The false-positive rate is evidence of calibration quality. Report it explicitly.

### Step 8 — Assemble and deliver the report

**Report structure:**

```
## Types & Dependencies Audit — [project name]
**Scope:** [--changed | --full-repo | --sample] | **Files analyzed:** N

### Summary
| Rule | Status | Severity | Count |
|------|--------|----------|-------|
| typ-001 | FINDING | high | Type checker covers X/N source dirs |
| typ-002 | N findings / M auto-accepted | high/critical | — |
| typ-003 | PASS | — | 0 |
| typ-004 | N findings | medium | — |
| dep-001 | FINDING | critical/high | CVE gate non-blocking + [CVE count] |
| dep-002 | FINDING | high | No dev lock file |
| dep-003 | FINDING | high | No license gate |
| dep-007 | N findings / M cleared | high/critical | — |

### Critical findings (address before merge)
...

### High findings (address in current sprint)
...

### Medium findings (address in next sprint)
...

### False-positive audit
- typ-002: X candidates, Y confirmed (Z% false-positive rate)
- dep-007: A candidates, B confirmed (C% false-positive rate)
[If false-positive rate > 50%: suggest auto-accept expansion or AST exclusion updates]
```

## Token measurement

After the first real audit, measure:
- Static-only pass (steps 1-5): actual tokens used
- LLM confirm pass (step 6): tokens per confirmed finding
- Total per audit scope

Update metadata.yml quality_metrics and config.yml budgets with measured values.
