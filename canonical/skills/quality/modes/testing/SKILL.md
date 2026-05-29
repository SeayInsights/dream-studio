# Testing — Test Quality Audit and Test Generation Guidance

## Mode dispatch

0. **Progressive disclosure check:** Apply the portable skill contract before dispatching.

1. Parse the mode from the argument (first word).
2. If no mode given, default to `audit`.
3. Read `modes/<mode>/SKILL.md` completely before executing.
4. If `gotchas.yml` exists in this directory, read it before executing.
5. Follow the mode's instructions exactly.

| Mode | File | Keywords |
|------|------|---------|
| audit | audit/SKILL.md | audit:, testing audit:, check tests:, test audit:, build:testing |
| build | build/SKILL.md | build:testing, generate tests:, write tests:, add test: |

## What This Skill Does

`audit` — retrospective test quality scan. Static analysis of test files for determinism, isolation, and coverage patterns, followed by LLM semantic pass for judgment-dependent rules (behavior vs. implementation, mock location, AAA structure). Three scope modes: `--changed` (default), `--full-repo`, `--sample`. Produces a classified report. Never fixes — classifies and reports only.

`build` — test generation guidance. Runs static-only checks on code about to receive tests, then provides structured guidance for writing tests that follow the approved patterns (behavior-first, AAA, mock at boundaries, critical-path-first). Blocks generation on high/critical structural violations in existing test files.

## Source Authority

Rules are defined in `rules.yml` in this directory. Both modes read from the same rule set. Rules with `action.build_mode: null` apply to audit only.

## Reference Document

Rule source: `canonical/skills/quality/references/testing-best-practices.md` (Section G + Section I sleep cross-reference, LIST-4).

## Skill Boundary

**Testing owns:** the quality of test code — test file existence (via coverage), determinism, isolation, structure, naming, assertion quality, mocking location.

**Code-quality owns:** the testability of production code — pure functions, CQS, no side effects from getters, low coupling.

When code-quality firing on a source file, it may cross-reference testing for post-refactor test review.

**Cross-references:**
- `tst-011` (no sleep() in test bodies) ↔ `cq-019` (no sleep() in production code): same symptom, test vs. production code. Reports note the sibling rule.
- `tst-009` (critical paths covered) ↔ `cq-016` (trust boundaries): CQ identifies entry points; testing verifies they're covered. Different files, different angles.
