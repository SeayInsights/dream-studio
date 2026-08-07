---
dream_studio:
  skill_id: ds-quality
  pack: quality
  mode: audit
  mode_type: diagnostic
  inputs: [source_root, db_path, slice_id]
  outputs: [health_report, consolidation_report]
  capabilities_required: [Read, Grep, Bash, Glob]
  model_preference: sonnet
  estimated_duration: 10-20min
---

## Before you start
Read `gotchas.yml` in this directory if present. Read `.planning/pre-slice<N>-audit.md` if a pre-audit exists.

## Trigger
`audit:health`, `audit:consolidate`

## Purpose
Audit Dream Studio build health and skill architecture. Produce classification reports only — do NOT fix in the same invocation as the audit.

## classify-before-fix rule
**NEVER fix in the same invocation as the audit.** Produce the report, classify every failure, and stop. Fixing in the same pass contaminates the audit signal and hides systemic patterns. The operator reviews the report and decides which category to act on first.

---

## audit:health

Run at the end of every slice before marking `SLICE_N_COMPLETE`. Collects pass/fail evidence across all known test groups and static checks.

### Steps

1. **Run batched test suites** (never run `py -m pytest tests/unit/` as a single call — OOM guaranteed):
   - Run each batch separately (e.g., `test_a*`, `test_b*`, etc.)
   - Record: pass count, fail count, error count, skipped count per batch
   - Never include `test_session_cleanup.py` in any batch invocation

2. **Run `git diff --check`** — verify no whitespace errors or conflict markers

3. **Run `py -m py_compile` spot-check** on recently modified files

4. **Check packs.yaml integrity**:
   - Every mode in packs.yaml must have a directory in `canonical/skills/<pack>/modes/<mode>/`
   - Every directory in `canonical/skills/<pack>/modes/` must be listed in packs.yaml
   - Run `tests/unit/canonical/test_packs_yaml.py` to confirm

5. **Classify every failure** using this taxonomy:

   | Category | Definition | Action |
   |----------|-----------|--------|
   | `REAL_BUG` | Code defect introduced this slice | Fix in next session |
   | `TEST_DEBT` | Test is fragile, over-specified, or brittle | Schedule cleanup |
   | `CONFIG_MISMATCH` | Environment or fixture mismatch, not a logic error | Note and skip |
   | `INTENTIONAL_SKIP` | Known pre-existing failure (baseline) | Confirm against baseline |
   | `REGRESSION` | Passing before this slice, failing now | Highest priority |

6. **Write output** to `.audit/build-health-YYYY-MM-DD.md` (create `.audit/` directory if needed)

### Output format

```markdown
# Build Health Audit — <slice_id> — <date>

## Summary
- Batches run: N
- Total tests: N passed / N failed / N errors
- git diff --check: CLEAN | DIRTY (list issues)
- packs.yaml integrity: PASS | FAIL

## Failures

| Test | File | Category | Notes |
|------|------|----------|-------|
| test_foo | tests/unit/test_foo.py | REAL_BUG | Introduced in 6c |
| test_bar | tests/unit/test_bar.py | INTENTIONAL_SKIP | Pre-existing baseline |

## Accepted Baseline
List pre-existing failures that are NOT regressions.

## Verdict
SLICE_N_COMPLETE | SLICE_N_BLOCKED (list blocking failures)
```

---

## audit:consolidate

Run after a slice is complete. Checks for architectural drift and coverage overlap across packs and modes.

### Steps

1. **Scan mode coverage overlap** — for each pair of modes in the same pack or across packs:
   - Identify modes with overlapping trigger keywords or purposes
   - Flag if two modes would handle the same user intent

2. **Check skill file length** — any SKILL.md under 80 lines may be under-specified; over 400 lines may be a split candidate

3. **Cross-pack boundary review** — flag cases where a skill in pack A directly imports or depends on a skill file from pack B (coupling that should go through the registry or spool instead)

4. **Identify orphan modes** — modes in packs.yaml with no tests in `tests/unit/canonical/`

5. **Produce consolidation recommendations**:
   - `MERGE`: two modes that should be one
   - `SPLIT`: one mode with two distinct responsibilities
   - `RENAME`: mode name doesn't match its actual behavior
   - `TEST_GAP`: mode with no canonical test coverage
   - `BOUNDARY_VIOLATION`: cross-pack direct dependency

6. **Write output** to `.audit/consolidation-YYYY-MM-DD.md`

### Output format

```markdown
# Consolidation Audit — <slice_id> — <date>

## Overlap Analysis
| Pack A | Mode A | Pack B | Mode B | Overlap Type | Recommendation |
|--------|--------|--------|--------|-------------|----------------|

## Length Check
| Pack | Mode | Lines | Flag |
|------|------|-------|------|

## Orphan Modes (no canonical tests)
- pack:mode

## Recommendations
| ID | Type | Target | Rationale |
|----|------|--------|-----------|
```
