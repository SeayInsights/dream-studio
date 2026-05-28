# Code-Quality Skill Changelog

## v1.0.0 — 2026-05-28

**Initial release (WO 18.4.3). Closes Phase 18.4 Layer 1.**

22 rules from LIST-4 (code-writing-best-practices.md sections A, B, C, D, E, F, H, I, L, M-partial).
Sections G (Testing → 18.5.1), J (Security → 18.4.1), K (Deps → 18.5.2),
M-rest (Ops → 18.6.3), O (Frontend → 18.6.1), P (Backend → 18.5.3) deferred.
cq-022 (CQS) deferred to Phase 19.

Three-way skill boundary established with security and database skills.
Shared utility `trust_boundary_detection.py` created — first canonical skill shared utility.

Files created:
- SKILL.md — mode dispatch, boundary documentation
- metadata.yml — jit-pending
- config.yml — token budgets (estimated), flake8 baseline dedup config
- gotchas.yml — empty (JIT)
- changelog.md — this file
- core-imports.md — dependency documentation
- smoke-test.md — quick validation
- rules.yml — 22 rules with cross_references schema extension
- audit/SKILL.md — 7-step audit process with flake8 baseline dedup
- build/SKILL.md — static enforcement; self-audit callable for 18.8.1
- canonical/skills/quality/shared/trust_boundary_detection.py — external entry point detection
