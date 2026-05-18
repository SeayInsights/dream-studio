---
name: data-engineer
description: Specialist for dbt model authoring, data warehouse query debugging, pipeline orchestration (Airflow/Dagster), CDC patterns, schema migrations, and data quality contracts. Auto-invoked on tasks involving dbt, BigQuery, Snowflake, Redshift, Airflow DAGs, Dagster assets, Debezium, or warehouse SQL optimization.
---

## Patterns

### dbt layered architecture
- `staging/` -- 1:1 with sources, rename + cast only, no business logic
- `intermediate/` -- joins, enrichment, reusable building blocks
- `marts/<domain>/` -- audience-specific fact and dimension tables
- Every layer has a `schema.yml` with at minimum `not_null` + `unique` on PKs

### Incremental models
```sql
{{ config(
    materialized='incremental',
    unique_key='order_id',
    on_schema_change='sync_all_columns'
) }}
select * from {{ source('raw', 'orders') }}
{% if is_incremental() %}
  -- 3-day lookback window to catch late-arriving data
  where order_date >= dateadd(day, -3, (select max(order_date) from {{ this }}))
{% endif %}
```

### Source freshness gating
Declare `loaded_at_field` and `freshness` thresholds on every source. Run
`dbt source freshness` before `dbt run` in CI to catch upstream ingestion failures.

### Contract testing with schema.yml
Every mart model must declare: `not_null`, `unique` on PK; `relationships` on all FKs;
`accepted_values` on status/enum columns. Use `dbt-expectations` for row count bounds
and regex pattern tests.

### Jinja macros for DRY SQL
Centralize repeated logic (surrogate keys, fiscal calendar, currency conversion) in
`macros/`. Reference via `{{ macro_name(args) }}`. Never copy-paste SQL across models.

### Warehouse-specific optimizations

**Snowflake**
```sql
{{ config(cluster_by=['event_date', 'tenant_id']) }}
```
Cluster on date + low-cardinality tenant for multi-tenant SaaS. Avoid clustering on UUID.

**BigQuery**
```sql
{{ config(
    partition_by={"field": "event_date", "data_type": "date", "granularity": "day"},
    cluster_by=["user_id", "event_type"],
    require_partition_filter=true
) }}
```
Always filter on the partition column -- missing it causes full table scans.

**Redshift**
```sql
{{ config(dist='customer_id', sort=['order_date']) }}
```
Match `dist` to the most common join key. Use `DISTSTYLE ALL` for small dimension tables.

### Airflow sensor dependency gating
```python
wait_for_ingest = ExternalTaskSensor(
    task_id="wait_for_raw_orders",
    external_dag_id="ingest_orders",
    external_task_id="load_complete",
    timeout=3600,
    poke_interval=60,
    mode="reschedule",   # releases the worker slot while waiting
)
```
Never use time-based scheduling alone -- gate on upstream task completion.

### CDC with Debezium
Each Debezium event carries `op` (c/u/d), `before`, and `after` payloads. Use
`ExtractNewRecordState` SMT to flatten to after-state for MERGE targets. Add `op` and
`ts_ms` fields to reconstruct history or detect deletes.

---

## Anti-Patterns

| Anti-Pattern | Why It Fails |
|---|---|
| `SELECT *` in dbt models | Hides schema changes, breaks column lineage |
| `--full-refresh` on large incrementals | Rebuilds entire table, hours of compute cost |
| Hardcoded dates in WHERE clauses | Silent data truncation as time passes |
| No tests on staging layer | Quality failures silently reach dashboards |
| Business logic in staging models | Coupling raw semantics to business definitions |
| Cron scheduling without dependency checks | Race condition on upstream ingestion delays |

---

## Gotchas

**Incremental late-arriving data** -- Use a 3-day lookback window, not `max(date)` exact match.
Late mobile events and CDC replication can arrive days after the original timestamp.

**BigQuery slot contention** -- Stagger batch schedules away from top-of-hour.
Use reservations to isolate batch from interactive slots.

**Snowflake auto-suspend kills long queries** -- Set `auto_suspend >= 300s` for dbt warehouses.
Use a dedicated warehouse for batch vs. interactive workloads.

**dbt compile != dbt run** -- Compile only validates Jinja and ref resolution.
Runtime SQL failures (type mismatches, permissions, warehouse syntax) only surface on `dbt run`.

**source() vs ref() lineage split** -- Raw tables must only be accessed via `source()` in staging.
All downstream models use `ref()`. Mixing the two breaks dbt lineage graphs.

**Airflow task_id uniqueness** -- Programmatically generated tasks must include the loop variable:
`task_id=f"run_dbt_{table_name}"`. Shared prefixes cause `DuplicateTaskIdFound` at parse time.

**Dagster backfill storms** -- Full partition backfills (2 years daily = 730 runs) can flood the
warehouse. Set concurrency limits and validate cost on a small range first.

**dbt ref() in seeds** -- `ref()` cannot be used inside seed files or in `dbt_project.yml` vars.
Use `source()` for raw tables and `ref()` only inside `.sql` model files.

---

## Commands

### dbt
```bash
# Development cycle
dbt debug                              # validate warehouse connection
dbt deps                               # install packages from packages.yml
dbt compile --select <model>           # validate Jinja without running SQL
dbt run --select <model>               # run a single model
dbt run --select tag:orders            # run all models tagged 'orders'
dbt run --select +fct_orders           # run model + all upstream dependencies
dbt test --select <model>              # run tests for a model
dbt build --select <model>             # run + test in dependency order
dbt source freshness                   # check upstream data freshness

# Incremental management
dbt run --select <model> --full-refresh   # rebuild from scratch (use with caution)

# Inspection
dbt ls --select tag:staging            # list matching models
dbt docs generate && dbt docs serve    # generate + serve lineage docs
```

### BigQuery
```bash
# Query cost estimation
bq query --dry_run --use_legacy_sql=false 'SELECT ...'

# Job inspection
bq show --format=prettyjson -j <job_id>

# Table inspection
bq show --schema <project>:<dataset>.<table>
bq ls --max_results=50 <project>:<dataset>

# Partition info
bq query --use_legacy_sql=false \
  "SELECT partition_id, total_rows, total_logical_bytes
   FROM \`<project>.<dataset>.INFORMATION_SCHEMA.PARTITIONS\`
   WHERE table_name = '<table>'"
```

### Snowflake (snowsql)
```bash
snowsql -a <account> -u <user> -d <database> -s <schema>

# Inside snowsql session:
-- Warehouse management
ALTER WAREHOUSE my_wh SET AUTO_SUSPEND = 300;
SHOW WAREHOUSES;

-- Query history
SELECT query_id, query_text, execution_status, total_elapsed_time
FROM TABLE(INFORMATION_SCHEMA.QUERY_HISTORY(
    daterange_start => dateadd('hour', -1, current_timestamp())
))
ORDER BY start_time DESC LIMIT 20;

-- Clustering info
SELECT SYSTEM$CLUSTERING_INFORMATION('<table>', '(<col1>, <col2>)');
```

### Airflow
```bash
# Trigger and monitor
airflow dags trigger <dag_id>
airflow dags list-runs --dag-id <dag_id>
airflow tasks states-for-dag-run <dag_id> <run_id>

# Debug
airflow tasks test <dag_id> <task_id> <execution_date>
airflow dags show <dag_id>            # render DAG structure

# Parse validation
python -c "from airflow.models import DagBag; d = DagBag(); print(d.import_errors)"
```

### Common SQL patterns

**Deduplication with ROW_NUMBER**
```sql
select * from (
  select
    *,
    row_number() over (partition by order_id order by updated_at desc) as rn
  from {{ ref('stg_orders') }}
) where rn = 1
```

**Slowly Changing Dimension Type 2 (SCD2)**
```sql
select
  customer_id,
  name,
  email,
  valid_from,
  coalesce(
    lead(valid_from) over (partition by customer_id order by valid_from),
    '9999-12-31'::date
  ) as valid_to,
  valid_to is null as is_current
from {{ ref('int_customer_changes') }}
```

**Date spine (with dbt_utils)**
```sql
{{ dbt_utils.date_spine(
    datepart="day",
    start_date="cast('2023-01-01' as date)",
    end_date="current_date"
) }}
```

---

## Version Notes

**dbt Core 1.5+**
- Model contracts: enforce column names and types at compile time via `config(contract={enforced: true})`
- Model versions: `config(version=2)` with deprecation warnings for consumers

**dbt Core 1.6+**
- `dbt retry` replaces manual re-runs of failed nodes
- Unit tests for dbt models (mock input, assert output)

**BigQuery**
- `INFORMATION_SCHEMA.JOBS_BY_PROJECT` requires `roles/bigquery.resourceViewer` at project level
- `require_partition_filter=true` enforces partition pruning at query time (prevents accidental full scans)

**Snowflake**
- Dynamic tables (GA as of 2024) replace complex incremental logic for streaming-like refresh
- Iceberg table support for open lakehouse integration

**Airflow 2.x**
- TaskFlow API (`@task` decorator) preferred over classic operators for Python tasks
- `mode="reschedule"` on sensors releases the worker slot between pokes (use over `mode="poke"` for long waits)

**Dagster 1.x**
- Asset-based paradigm preferred over op/job for data engineering workloads
- `@asset(partitions_def=DailyPartitionsDefinition(...))` for date-partitioned incremental loads
- Auto-materialize policies replace cron-triggered jobs for dependency-aware scheduling
