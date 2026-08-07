# Code-Quality Mode — Core Imports

## Imported Modules

### ds-core/git.md
**Usage:** Scope determination for `--changed` mode.
**Pattern:** `git diff --name-only main...HEAD`
**Impact if changed:** --changed scope breaks; fall back to --full-repo.

### canonical/skills/quality/references/code-writing-best-practices.md
**Usage:** Authoritative source for rule content (LIST-4, sections A-N).
**Impact if changed:** `source.item` text in rules.yml may need updating.

### canonical/skills/quality/shared/trust_boundary_detection.py
**Usage:** External entry point detection for cq-016 (validate-at-internal-boundaries).
Provides `is_external_entry_point(func_node)` and `classify_boundary(func_node)`.
**Impact if changed:** cq-016 detection accuracy affected. Must re-validate against
Dream Studio's CLI and hook patterns when new frameworks are added.

### runtime/config/release-gates/flake8-baseline.txt
**Usage:** Flake8 baseline for co-location marking (audit/SKILL.md Step 2).
**Impact if changed:** Baseline de-duplication may mark different lines. Re-verify
first-audit findings count after baseline update.

## Static Tools

### pyflakes (Python, INSTALLED v3.4.0)
**Usage:** cq-006 (bare except without log), cq-015 (specific exceptions),
cq-013 (import hints).

### Python ast stdlib (ALWAYS available)
**Usage:** cq-002 (line count), cq-003 (param count), cq-005 (nesting depth),
cq-010 (constants), cq-013 (import order), cq-014 (circular imports), cq-019 (sleep),
cq-020 (docstrings), cq-021 (property side effects), cq-A-explicit (wildcard imports).

### ruff (NOT installed; `availability_note` in rules.yml)
Would handle: naming, complexity, import ordering, and many other patterns.
Install ruff for cheaper static execution across most cq-* rules.

### mypy (NOT installed; `availability_note` in rules.yml)
Would handle: cq-M-partial (type checker automated), type narrowing checks.

## Skill Boundary Partners

### ds-quality:security (complementary, not dependency)
Cross-references: cq-016 ↔ sec-003; cq-006/cq-015 ↔ sec-013 (indirectly).

### ds-quality:database (complementary, not dependency)
Cross-references: cq-011 (magic numbers) ↔ db-005 (float money — more specific).

## Maintenance Notes

When new framework entry-point patterns are encountered in Dream Studio:
1. Add the pattern to `canonical/skills/quality/shared/trust_boundary_detection.py`
2. The pattern propagates to cq-016 automatically (no rules.yml change needed)
3. Commit on any branch touching the detection logic; update this core-imports.md

When 18.5.1 (testing skill) ships:
- Review Section G in code-writing-best-practices.md
- Determine if any testing rules in that section should stay as code-quality cross-references
- Migration plan documented in 18.5.1 pre-flight, not here
