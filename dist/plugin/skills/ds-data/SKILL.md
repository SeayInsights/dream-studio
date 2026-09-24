---
name: ds-data
description: 'Data engineering and database quality — schema/query/migration audits, warehouse pipeline authoring. Use for: audit:, dbt:'
---

# Data — Database Quality & Data Engineering

## Mode dispatch

0. **Progressive disclosure check:** Before dispatching to a mode, apply the portable skill contract. If a current calibration interface is available in this checkout, use it; otherwise rely on the mode table below. If a mode is locked, show the unlock message and stop.

1. Parse the mode from the argument (first word).
2. If no mode given, infer from the user's message using the keyword table below.
3. If still ambiguous, list available modes and ask.
4. Read `modes/<mode>/SKILL.md` completely.
5. If `modes/<mode>/gotchas.yml` exists, read it before executing.
6. Follow the mode's instructions exactly as written.

| Mode | File | Keywords |
|---|---|---|
| database | modes/database/SKILL.md | audit:, database audit:, check schema:, check migrations:, db audit:, build:database |
| data-engineering | modes/data-engineering/SKILL.md | dbt, BigQuery, Snowflake, Redshift, Airflow DAG, Dagster asset, Debezium, warehouse SQL |

Both modes carry a dedicated subagent (`quality-database`, `data-engineer` — see
`canonical/agents/coverage.yml`); a caller with Task-tool access dispatches the
subagent directly rather than reading the mode file inline.

## Split history

Split out of the `quality` pack (`database`) and the `domains` pack
(`data-engineering`) — pack-split, 2026-09-24. Neither mode's own content,
rules, or subagent changed; only which pack owns them did.
