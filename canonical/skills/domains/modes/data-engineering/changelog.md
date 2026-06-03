# Data-Engineering Skill Changelog

## v1.0.0 — 2026-06-03

**Promoted from agent to skill (WO 18.9 Tier 4)**

Content transferred verbatim from `canonical/agents/data-engineer.md` (266 lines).
No content changes — relocation only, per JIT policy: enrich after first real usage.

Files created:
- SKILL.md — dbt architecture, incremental patterns, warehouse optimizations (BigQuery/Snowflake/Redshift), Airflow sensor gating, CDC/Debezium, anti-patterns, gotchas, commands, SQL patterns, version notes
- metadata.yml — skill metadata, jit-pending status, single-mode-deliberate note
- gotchas.yml — 8 gotchas from agent file, structured with severity/category
- config.yml — invocation type (subagent-target), graceful degradation flag
- changelog.md — this file

Agent file reduced to thin wrapper (~20 lines).

**DELIBERATE SINGLE-MODE PROMOTION:**
Content size (266 lines) is the largest of any promoted agent. Split into multiple
modes (e.g., dbt-pipelines vs warehousing vs orchestration) is deferred to Phase 19
based on real usage signals. Phase 19 will have data from actual invocations to inform
which topics cluster together and which warrant a mode split. No premature splitting.

**Scope boundary documented:**
data-engineering = data pipelines, warehouse query patterns, dbt/Airflow/Dagster orchestration,
CDC, warehouse-specific SQL optimizations (BigQuery partitions, Snowflake clustering, Redshift dist).
database skill = application-layer schema integrity, indexes, FK design, query anti-patterns in
transactional databases (SQLite, Postgres, MySQL). Different scopes — pipeline/warehouse vs
application schema. Both can fire on the same project without duplication.
