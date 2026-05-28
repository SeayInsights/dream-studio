# Database Skill Changelog

## v1.0.0 — 2026-05-28

**Initial release (WO 18.4.2)**

22 rules from LIST-3 (database-best-practices.md sections D, E, F, C, I, M).
Sections J (multi-tenancy) and K (compliance) deferred — J to future, K to 18.7.1.

Skill boundary established with ds-quality:security:
- Database owns: schema design, query patterns, migration safety, backup strategy/ops
- Security owns: parameterized queries (inject risk), encryption, PII in logs, backup encryption

Token budgets are estimates. Batch 7 measures actuals on dream-studio-clean.

Files created:
- SKILL.md — mode dispatch, skill description, boundary documentation
- metadata.yml — jit-pending status, dependency list
- config.yml — token budgets (estimated), LLM cache config, config_section scope
- gotchas.yml — empty (JIT: populate from first audit)
- changelog.md — this file
- core-imports.md — dependency impact analysis
- smoke-test.md — quick validation procedure
- rules.yml — 22 rules
- audit/SKILL.md — 7-step audit process
- build/SKILL.md — static enforcement for migration/query/schema generation
