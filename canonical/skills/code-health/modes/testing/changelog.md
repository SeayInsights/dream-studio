# Testing Skill Changelog

## v1.0.0 — 2026-05-29 (18.5.1)

Initial release.

- 15 testing rules (tst-001 through tst-015) sourced from code-writing-best-practices.md Section G and Section I sleep cross-reference
- Two modes: audit (static + LLM semantic pass, 3 scope variants) + build (test generation guidance)
- Five calibrations from design-proposal review:
  1. tst-001: coverage-based detection (not path-scan), distinct from tst-013
  2. tst-003: static pass `high` (candidate), confirm-to-critical via LLM
  3. tst-009: config-driven `critical_path_globs`, default `projections/api/routes/**`
  4. tst-010: flags enforcement gap (fail_under vs actual), not bare threshold
  5. tst-002/tst-008: pre-committed >20% disagreement demotion criterion
- Gotchas pre-seeded with Dream Studio-specific patterns (conftest.py isolation, tst-003 benign datetime, tst-010 gap)
- Skill boundary documented with ds-quality:code-quality
- Cross-references: tst-011 ↔ cq-019; tst-009 ↔ cq-016
