# Data Modeling Patterns

Dimensional modeling reference for BI developers — covers warehouse design, load order, SCD handling, and the four standard BI query shapes. Sourced from: arpit-mittal-ds/Data-Architect, hoangsonww/End-to-End-Data-Pipeline.

---

## 1. Inmon vs Kimball

| Dimension | Inmon (3NF) | Kimball (Dimensional) |
|-----------|------------|----------------------|
| Shape | Normalized entity-relationship | Denormalized star/snowflake |
| Redundancy | Minimal — facts join many tables | Accepted — dims are wide |
| Query performance | Slower (many joins) | Faster (few joins) |
| Flexibility | High — schema change is cheap | Lower — dim changes ripple |
| Best for | Enterprise data vault, single source of truth | BI reporting, ad-hoc analytics |
| Power BI fit | Poor (too many joins, slow DirectQuery) | Excellent — native star schema support |

**Rule:** Default to Kimball star schema for Power BI semantic models. Use Inmon/vault only when a multi-mart enterprise layer exists upstream and Power BI connects to a mart, not the vault.

---

## 2. Star Schema Anatomy

```
          dim_date ─────────────┐
          dim_customers ────────┤
          dim_products ─────────┼──► fact_orders
          dim_devices ──────────┘
                                     ▼
                              agg_daily_orders   (pre-aggregated summary)
```

### Naming conventions
- Dimension tables: `dim_<entity>` (singular)
- Fact tables: `fact_<event>` (singular)
- Aggregate tables: `agg_<grain>_<metric>` (e.g., `agg_daily_orders`)
- Surrogate keys: `<entity>_key` (integer, never natural key)
- Natural/business keys: `<entity>_id` (source system identifier, preserved for debugging)

### Grain
Define the grain before adding columns. Every row in a fact table = one occurrence of the grain event.
- `fact_orders`: one row per order line item
- `fact_sensor_readings`: one row per sensor reading
- Mixing grains in one fact table causes incorrect aggregations in Power BI.

### Operational metadata as fact (anti-pattern)
`fact_pipeline_runs` (tracking ETL job metadata as a fact table) is a common convenience pattern but violates Kimball — operational metadata is not a business event. Use a separate logging/monitoring table outside the star schema instead.

---

## 3. SCD Type 2 — Slowly Changing Dimensions

Track historical attribute changes (e.g., customer address, product category) without overwriting old records.

### Column pattern
```sql
effective_from  TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
effective_to    TIMESTAMP   NOT NULL DEFAULT '9999-12-31',
is_current      BOOLEAN     NOT NULL DEFAULT TRUE
```

### Upsert logic (PostgreSQL)
```sql
-- Close the current record
UPDATE dim_customers
SET effective_to = NOW(), is_current = FALSE
WHERE customer_id = :id AND is_current = TRUE;

-- Insert new version
INSERT INTO dim_customers (..., effective_from, effective_to, is_current)
VALUES (..., NOW(), '9999-12-31', TRUE);
```

### DAX filter pattern (Power BI)
When connecting to an SCD2 source, always filter to the current record in Power Query or as a relationship filter:
```m
// M-Query — filter before load
Table.SelectRows(dim_customers, each [is_current] = true)
```
Or in DAX:
```dax
CurrentCustomers = FILTER(dim_customers, dim_customers[is_current] = TRUE)
```
Never expose the full SCD2 history to Power BI visuals without explicit time-travel intent — it multiplies row counts and breaks aggregations.

---

## 4. Kimball Load Ordering

Dependencies determine order — dimensions must exist before facts can reference them.

```
[stage_orders, stage_anomalies]   ← parallel staging (raw → staging layer)
            │
            ▼
         dims                     ← dimension upserts (MERGE/ON CONFLICT)
            │
            ▼
         facts                    ← fact inserts (LEFT JOIN anti-join for dedup)
            │
            ▼
         aggs                     ← aggregation refreshes (MERGE upsert)
            │
            ▼
       log_run                    ← operational metadata (success/failure)
```

### Staging layer deduplication
```sql
-- Anti-join pattern: only insert rows not already in the fact table
INSERT INTO fact_orders (...)
SELECT s.*
FROM stage_orders s
LEFT JOIN fact_orders fo ON s.order_id = fo.order_id
WHERE fo.order_id IS NULL;
```

### Dimension upsert (PostgreSQL)
```sql
INSERT INTO dim_products (product_id, name, category, ...)
VALUES (...)
ON CONFLICT (product_id) DO NOTHING;  -- idempotent for new records
```

---

## 5. Snowflake Date Spine + Fact Clustering

### Date spine generation (no seed table required)
```sql
-- Snowflake: generate 3 years of dates
INSERT INTO dim_date (date_key, full_date, year, month, day, ...)
SELECT
  TO_NUMBER(TO_CHAR(DATEADD(DAY, seq4(), '2024-01-01'::DATE), 'YYYYMMDD')) AS date_key,
  DATEADD(DAY, seq4(), '2024-01-01'::DATE) AS full_date,
  YEAR(DATEADD(DAY, seq4(), '2024-01-01'::DATE)) AS year,
  MONTH(DATEADD(DAY, seq4(), '2024-01-01'::DATE)) AS month,
  DAY(DATEADD(DAY, seq4(), '2024-01-01'::DATE)) AS day
FROM TABLE(GENERATOR(ROWCOUNT => 1096));  -- 3 years

-- PostgreSQL equivalent
SELECT generate_series('2024-01-01'::date, '2026-12-31'::date, '1 day'::interval);
```

### Fact table clustering (Snowflake)
Cluster on the most-filtered dimensions to optimize BI query performance:
```sql
ALTER TABLE fact_orders CLUSTER BY (date_key, customer_key);
ALTER TABLE fact_sensor_readings CLUSTER BY (date_key, device_key);
```
**Rule:** Always cluster on `date_key` first (most selective filter in BI), then the primary entity key.

### Automated aggregation refresh (Snowflake Task — no Airflow needed)
```sql
CREATE OR REPLACE TASK refresh_daily_orders_agg
  WAREHOUSE = compute_wh
  SCHEDULE = 'USING CRON 0 1 * * * UTC'
AS
MERGE INTO agg_daily_orders t
USING (SELECT date_key, SUM(amount) AS total_revenue, COUNT(*) AS order_count
       FROM fact_orders GROUP BY date_key) s
ON t.date_key = s.date_key
WHEN MATCHED THEN UPDATE SET ...
WHEN NOT MATCHED THEN INSERT ...;
```

---

## 6. Four Standard BI Query Shapes

Every star schema naturally supports four reporting patterns. Design fact and dim tables to answer all four.

### (a) Time series — "How did X trend over time?"
```sql
SELECT d.full_date, COALESCE(a.total_revenue, 0) AS revenue
FROM dim_date d
LEFT JOIN agg_daily_orders a ON d.date_key = a.date_key
WHERE d.full_date >= DATEADD(DAY, -90, CURRENT_DATE)
ORDER BY d.full_date;
```
*COALESCE + LEFT JOIN ensures zero-fill on days with no orders (critical for trend lines).*

### (b) Customer / entity ranking — "Who are the top X?"
```sql
SELECT c.customer_name, c.segment,
       SUM(f.amount) AS lifetime_value,
       COUNT(DISTINCT f.order_id) AS order_count
FROM dim_customers c
LEFT JOIN fact_orders f ON c.customer_key = f.customer_key
WHERE c.is_current = TRUE
GROUP BY c.customer_name, c.segment
ORDER BY lifetime_value DESC;
```

### (c) Exception / alert report — "What crossed a threshold?"
```sql
SELECT d.device_id, f.reading_value, f.timestamp
FROM fact_sensor_readings f
JOIN dim_devices d ON f.device_key = d.device_key
WHERE f.is_anomaly = TRUE
  AND f.timestamp >= DATEADD(DAY, -7, CURRENT_TIMESTAMP);
```

### (d) Operational health — "Is the pipeline working?"
```sql
SELECT DATE(run_start) AS run_date,
       COUNT(*) AS total_runs,
       SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS successes,
       ROUND(AVG(DATEDIFF('second', run_start, run_end)), 1) AS avg_duration_sec
FROM fact_pipeline_runs
WHERE run_start >= DATEADD(DAY, -30, CURRENT_TIMESTAMP)
GROUP BY run_date ORDER BY run_date DESC;
```

---

## 7. Anti-Patterns

| ❌ Anti-pattern | ✅ Correct approach |
|----------------|-------------------|
| Loading facts before dimensions | Always: staging → dims → facts → aggs |
| Skipping the staging layer | Stage raw data first — enables replay on failure |
| Using natural keys as fact FKs | Use surrogate (integer) keys — natural keys change |
| Mixing grains in one fact table | One grain per fact table |
| SCD2 without `is_current` filter in Power BI | Always filter `WHERE is_current = TRUE` before joining |
| Hardcoding date ranges in dim_date | Generate dynamically; refresh when range expires |
| Tracking ETL metadata as a Kimball fact | Use a separate operational log table |
| Clustering on low-cardinality columns | Cluster on high-cardinality time + entity keys |
