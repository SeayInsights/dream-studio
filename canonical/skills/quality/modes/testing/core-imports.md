# Testing Mode — Core Imports

## Imported Modules

### ds-core/git.md
**Usage:** Scope determination for `--changed` mode.
**Pattern:** `git diff --name-only main...HEAD`
**Impact if changed:** --changed scope breaks; fall back to --full-repo.

### canonical/skills/quality/references/testing-best-practices.md
**Usage:** Authoritative source for rule content (LIST-4, Section G + Section I).
**Impact if changed:** `source.item` text in rules.yml may need updating.

### pyproject.toml (project file)
**Usage:** Coverage configuration (fail_under threshold for tst-010), pytest config (testpaths for tst-001/tst-014).
**Impact if changed:** tst-010 gap calculation uses fail_under; tst-014 checks for test runner in CI.

## Static Tools

### Python ast stdlib (ALWAYS available)
**Usage:** tst-003 (determinism patterns), tst-004 (shared state), tst-006 (assertion count),
tst-007 (name pattern), tst-011 (sleep()), tst-012 (fixture scope), tst-013 (file organization),
tst-015 (slow patterns in unit tests).

### coverage.py (INSTALLED, via `pip install coverage`)
**Usage:** tst-001 (module coverage ≥ 0%), tst-010 (actual coverage % + enforcement gap).
**Version:** Check with `coverage --version`.
**Fallback:** If coverage data unavailable (no .coverage file), tst-001 falls back to path-scan.

### No additional static tools required
Unlike code-quality (pyflakes) or database (sqlparse), testing analysis is primarily ast + LLM.
pytest is used for context (collecting test names) but is NOT invoked to run tests.

## LLM Semantic Pass Rules

Rules requiring LLM: tst-002, tst-004 (confirmation), tst-005, tst-006 (confirmation),
tst-007 (confirmation), tst-008, tst-012 (confirmation).

Rules with pre-committed demotion criterion (>20% human-LLM disagreement → requires_human_review):
- tst-002 (behavior vs implementation)
- tst-008 (mock location)

Record agreement rate in verification paste after first audit.

## Skill Boundary Partners

### ds-quality:code-quality (complementary, not dependency)
Cross-references: tst-011 ↔ cq-019 (sleep); tst-009 ↔ cq-016 (entry points/critical paths).
When testing fires on a test file, code-quality may fire on the corresponding source file.
Reports note sibling rules; neither skill duplicates the other.

## Maintenance Notes

When new pytest fixture patterns are encountered in Dream Studio:
1. If the pattern is a positive (like conftest.py early-isolation), add to gotchas.yml with severity: informational
2. If the pattern is a gotcha (false positive pattern), add to gotchas.yml with the suppression mechanism

When tst-002 or tst-008 demotion criterion is evaluated (first audit):
1. Record agreement rate in the first-audit verification paste
2. If > 20% disagreement: update the rule's `requires_human_review: true` in rules.yml
3. Update this file with the measurement date and result

When 18.5.2 (types-dependencies) ships:
- Section K of code-writing-best-practices.md will ship; no testing rules are expected to migrate
- Review the boundary documentation for any overlap
