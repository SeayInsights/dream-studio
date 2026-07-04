"""DuckDB analytics store — connection layer for aggregate_metrics.db.

aggregate_metrics.db is a DuckDB file (NOT SQLite) that holds analytics
rollup tables and DuckDB-side projection tables that mirror business_* from
studio.db (read model for dashboard API routes and analytics queries).

DECISION (WO-SCHEMA-TRUTH-DEBT): Keep DuckDB as the analytics store.
  - aggregate_metrics.db must be a DuckDB file. Delete any legacy SQLite file
    at that path before connecting if one exists from pre-DuckDB versions.
  - dispatch_to_duckdb (framework.py) requires _analytics_conn to be set
    (currently None — future wiring point, not wired yet).
  - aggregate_metrics.py reads studio.db (SQLite) and writes aggregate_metrics.db
    (DuckDB) via this module. These are distinct stores; no module should open
    aggregate_metrics.db with sqlite3.connect().

Authority boundary: this store is NEVER-AUTHORITY.
  - It receives aggregated data from studio.db (read-only source).
  - No canonical event is emitted based on DuckDB reads.
  - No gate decision uses DuckDB as source.
  - API routes open read-only connections only.
  - The aggregation pipeline and projection runners hold the sole
    read-write connection (core/projections/runner.py only).
"""

from __future__ import annotations

import logging
from pathlib import Path

try:
    import duckdb
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "duckdb is required for the analytics store. Run: pip install duckdb>=0.10"
    ) from exc

from core.config.paths import state_dir

logger = logging.getLogger(__name__)


class AnalyticsStoreFormatError(RuntimeError):
    """The analytics store file exists but is not a native DuckDB store.

    Raised by connect_analytics (fail-loud) rather than letting DuckDB open a
    wrong-format file — a SQLite masquerade opens silently via DuckDB's compat
    layer (row-store, not columnar), and a corrupt file yields a cryptic error.
    The analytics store is NEVER-AUTHORITY and rebuildable: delete it to rebuild.
    """


def _ensure_native_duckdb(path: Path) -> None:
    """Guarantee the file at ``path`` is a native DuckDB store, or fail loud.

    DuckDB silently opens a SQLite file via its compat layer, defeating the
    native columnar store (the WO-DUCKDB-REAL bug). Handling:
      - absent or empty file → no-op (DuckDB initialises it natively);
      - SQLite masquerade → deleted + recreated native, with a loud warning
        (analytics is rebuildable, so self-heal beats crashing);
      - native DuckDB (``DUCK`` magic at offset 8) → accepted;
      - anything else (corrupt/foreign) → AnalyticsStoreFormatError (fail-loud),
        instead of a silent wrong-format open or a swallowed None.
    """
    if not path.exists():
        return
    head = path.read_bytes()[:16]
    if not head:
        return  # empty file — duckdb.connect writes a fresh native header

    if head.startswith(b"SQLite format 3"):
        logger.warning(
            "aggregate_metrics.db at %s is a legacy SQLite file — removing and "
            "recreating as a native DuckDB store (analytics is rebuildable).",
            path,
        )
        for suffix in ("", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)
        return

    # Native DuckDB stores carry the ASCII magic "DUCK" at byte offset 8.
    if b"DUCK" not in head:
        raise AnalyticsStoreFormatError(
            f"aggregate_metrics.db at {path} is not a native DuckDB store "
            f"(header={head!r}); refusing to open it silently. The analytics "
            f"store is rebuildable — delete the file to have it recreated."
        )


_ROLLUP_TABLES_DDL = """
    CREATE TABLE IF NOT EXISTS finding_rollups (
        project_id TEXT NOT NULL,
        skill_id TEXT NOT NULL,
        severity TEXT NOT NULL,
        day TEXT NOT NULL,
        finding_count INTEGER NOT NULL DEFAULT 0,
        new_count INTEGER NOT NULL DEFAULT 0,
        fixed_count INTEGER NOT NULL DEFAULT 0,
        persisting_count INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (project_id, skill_id, severity, day)
    );

    CREATE TABLE IF NOT EXISTS rule_fire_rates (
        rule_id TEXT NOT NULL,
        skill_id TEXT NOT NULL,
        language TEXT,
        fire_count INTEGER NOT NULL DEFAULT 0,
        scan_count INTEGER NOT NULL DEFAULT 0,
        dismiss_count INTEGER NOT NULL DEFAULT 0,
        fp_rate DOUBLE,
        last_fired_at TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (rule_id, skill_id)
    );

    CREATE TABLE IF NOT EXISTS baseline_trends (
        project_id TEXT NOT NULL,
        skill_id TEXT NOT NULL,
        baseline_count INTEGER NOT NULL DEFAULT 0,
        current_count INTEGER NOT NULL DEFAULT 0,
        delta INTEGER NOT NULL DEFAULT 0,
        trend_direction TEXT,
        scan_count INTEGER NOT NULL DEFAULT 0,
        last_scan_at TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (project_id, skill_id)
    );

    CREATE TABLE IF NOT EXISTS guard_calibration (
        rule_id TEXT NOT NULL PRIMARY KEY,
        total_fires INTEGER NOT NULL DEFAULT 0,
        dismiss_count INTEGER NOT NULL DEFAULT 0,
        block_count INTEGER NOT NULL DEFAULT 0,
        advisory_count INTEGER NOT NULL DEFAULT 0,
        fp_rate DOUBLE,
        calibration_status TEXT DEFAULT 'pending',
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pattern_catalog (
        pattern_id TEXT NOT NULL PRIMARY KEY,
        project_id TEXT,
        skill_sequence TEXT NOT NULL,
        occurrence_count INTEGER NOT NULL DEFAULT 0,
        avg_findings_per_run DOUBLE,
        last_seen_at TEXT,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS recommendation_outcomes (
        rule_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        recommendation_type TEXT NOT NULL,
        presented_count INTEGER NOT NULL DEFAULT 0,
        acted_count INTEGER NOT NULL DEFAULT 0,
        acceptance_rate DOUBLE,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (rule_id, project_id, recommendation_type)
    );

    CREATE TABLE IF NOT EXISTS _aggregate_meta (
        key TEXT NOT NULL PRIMARY KEY,
        value TEXT NOT NULL
    );
"""

_ANALYTICS_TABLES_DDL = """
    CREATE TABLE IF NOT EXISTS duckdb_execution_events (
        event_id TEXT NOT NULL PRIMARY KEY,
        event_type TEXT NOT NULL,
        event_name TEXT,
        project_id TEXT,
        milestone_id TEXT,
        task_id TEXT,
        session_id TEXT,
        skill_id TEXT,
        workflow_id TEXT,
        agent_id TEXT,
        hook_id TEXT,
        tool_id TEXT,
        model_id TEXT,
        adapter_id TEXT,
        outcome_status TEXT,
        created_at TEXT NOT NULL
    );
"""


# Read-model VIEWS over events_fact — present the old SQLite read-model shapes so
# dashboard/CLI readers only swap their connection (SQLite→DuckDB), no SQL rewrite.
# These are derived from canonical events (via events_fact), so they're complete
# where the old SQLite projections were partial (e.g. token capture). Created after
# events_fact in ensure_analytics_schema (they depend on it).
_PROJECTION_VIEWS_DDL = """
    CREATE OR REPLACE VIEW token_usage_records AS
    WITH tok AS (
        SELECT
            *,
            COALESCE(model_id, json_extract_string(payload, '$.model')) AS payload_model,
            TRY_CAST(json_extract_string(payload, '$.cache_creation_input_tokens') AS BIGINT)
                AS payload_cache_write,
            TRY_CAST(json_extract_string(payload, '$.cache_read_input_tokens') AS BIGINT)
                AS payload_cache_read
        FROM events_fact WHERE event_type LIKE 'token%'
    )
    SELECT
        t.event_id AS token_usage_id, t.project_id, t.milestone_id, t.task_id,
        NULL AS process_run_id,
        t.agent_id, t.skill_id, t.workflow_id, t.hook_id,
        t.payload_model AS model_id, NULL AS provider,
        t.input_tokens, t.output_tokens, t.payload_cache_write AS cached_tokens,
        COALESCE(t.input_tokens,0)+COALESCE(t.output_tokens,0) AS total_tokens,
        CASE WHEN p.model IS NULL THEN NULL ELSE (
            COALESCE(t.input_tokens,0) * p.input_per_m
            + COALESCE(t.output_tokens,0) * p.output_per_m
            + COALESCE(t.payload_cache_write,0) * p.cache_write_per_m
            + COALESCE(t.payload_cache_read,0) * p.cache_read_per_m
        ) / 1000000.0 END AS estimated_cost,
        NULL AS purpose, t.event_timestamp AS created_at,
        NULL AS source_refs_json, NULL AS evidence_refs_json, t.adapter_id, NULL AS billing_mode,
        NULL AS token_visibility, NULL AS cost_visibility, NULL AS usage_source,
        NULL AS cost_source,
        NULL AS accounting_confidence, t.payload_cache_read AS cache_read_tokens
    FROM tok t
    LEFT JOIN token_model_pricing p
        ON p.model = regexp_replace(lower(trim(t.payload_model)), '-\\d{8}$', '');
    CREATE OR REPLACE VIEW hook_executions AS SELECT
        event_id AS hook_exec_id, NULL::BIGINT AS activity_id,
        json_extract_string(payload,'$.hook_name') AS hook_name,
        json_extract_string(payload,'$.hook_type') AS hook_type,
        json_extract_string(payload,'$.trigger_context') AS trigger_context,
        json_extract_string(payload,'$.started_at') AS started_at,
        json_extract_string(payload,'$.completed_at') AS completed_at,
        duration_ms, exit_code, status, json_extract_string(payload,'$.output') AS output,
        json_extract_string(payload,'$.error_message') AS error_message,
        TRY_CAST(json_extract_string(payload,'$.cpu_time_ms') AS BIGINT) AS cpu_time_ms,
        TRY_CAST(json_extract_string(payload,'$.memory_mb') AS DOUBLE) AS memory_mb
    FROM events_fact WHERE event_type='system.hook.execution.logged';
    CREATE OR REPLACE VIEW validation_failures AS SELECT
        event_id AS failure_id, event_id,
        event_type AS vf_event_type,
        event_type,
        json_extract_string(payload,'$.errors') AS errors,
        json_extract_string(payload,'$.invalid_event_type') AS attempted_event,
        event_timestamp AS attempted_at
    FROM events_fact WHERE event_type='event.validation.failed';
    CREATE OR REPLACE VIEW raw_sessions AS
    WITH recorded AS (
        SELECT
            json_extract_string(payload,'$.session_id') AS session_id,
            json_extract_string(payload,'$.project_id') AS project_id,
            json_extract_string(payload,'$.topic') AS topic,
            json_extract_string(payload,'$.pipeline_phase') AS pipeline_phase,
            event_timestamp AS started_at,
            input_tokens, output_tokens, outcome,
            ROW_NUMBER() OVER (
                PARTITION BY json_extract_string(payload,'$.session_id')
                ORDER BY event_timestamp
            ) AS rn
        FROM events_fact WHERE event_type='system.session.recorded'
    ),
    closed AS (
        SELECT
            json_extract_string(payload,'$.session_id') AS session_id,
            event_timestamp AS ended_at,
            TRY_CAST(json_extract_string(payload,'$.duration_s') AS DOUBLE) AS duration_s,
            TRY_CAST(json_extract_string(payload,'$.tasks_completed') AS BIGINT) AS tasks_completed,
            json_extract_string(payload,'$.outcome') AS outcome,
            ROW_NUMBER() OVER (
                PARTITION BY json_extract_string(payload,'$.session_id')
                ORDER BY event_timestamp DESC
            ) AS rn
        FROM events_fact WHERE event_type='system.session.closed'
    )
    SELECT
        r.session_id, r.project_id, r.topic,
        r.started_at, c.ended_at, c.duration_s,
        r.input_tokens, r.output_tokens,
        c.tasks_completed, r.pipeline_phase,
        NULL::BIGINT AS handoff_consumed,
        COALESCE(c.outcome, r.outcome) AS outcome
    FROM recorded r
    LEFT JOIN closed c ON c.session_id = r.session_id AND c.rn = 1
    WHERE r.rn = 1;
"""

_EVENTS_FACT_DDL = """
    CREATE TABLE IF NOT EXISTS events_fact (
        event_id VARCHAR, source VARCHAR, event_type VARCHAR, event_timestamp VARCHAR,
        correlation_id VARCHAR, project_id VARCHAR, milestone_id VARCHAR, work_order_id VARCHAR,
        task_id VARCHAR, session_id VARCHAR, skill_id VARCHAR, workflow_id VARCHAR, agent_id VARCHAR,
        hook_id VARCHAR, tool_id VARCHAR, model_id VARCHAR, adapter_id VARCHAR, severity VARCHAR,
        input_tokens BIGINT, output_tokens BIGINT, duration_ms BIGINT, exit_code BIGINT,
        status VARCHAR, outcome VARCHAR, payload JSON
    );
"""

_FACT_DIMS = [
    "correlation_id",
    "project_id",
    "milestone_id",
    "work_order_id",
    "task_id",
    "session_id",
    "skill_id",
    "workflow_id",
    "agent_id",
    "hook_id",
    "tool_id",
    "model_id",
    "adapter_id",
    "severity",
]


def derive_events_fact(conn, studio_db_path, *, full_rebuild: bool = False) -> int:
    """Derive the wide events_fact in DuckDB from the SQLite dual canonical events.

    The dashboard read surface — one wide fact serving token/hook/skill/workflow/
    agent/session/execution analytics via filter+group. Runner is the sole writer;
    fed read-only from SQLite (NEVER-AUTHORITY). Incremental by event_timestamp
    unless full_rebuild. Returns rows written.
    """
    import sqlite3

    conn.execute("INSTALL sqlite")
    conn.execute("LOAD sqlite")
    conn.execute(f"ATTACH '{studio_db_path}' AS s (TYPE SQLITE, READ_ONLY)")
    try:
        if full_rebuild:
            conn.execute("DELETE FROM events_fact")
        last = conn.execute(
            "SELECT COALESCE(MAX(event_timestamp), '') FROM events_fact"
        ).fetchone()[0]
        before = conn.execute("SELECT COUNT(*) FROM events_fact").fetchone()[0]
        for table, src in (
            ("ai_canonical_events", "ai"),
            ("business_canonical_events", "business"),
        ):
            cols = {
                r[1] for r in sqlite3.connect(studio_db_path).execute(f"PRAGMA table_info({table})")
            }

            def d(n, cols=cols):
                return f"e.{n}" if n in cols else "NULL"

            conn.execute(
                f"""
                INSERT INTO events_fact SELECT e.event_id, '{src}', e.event_type, e.event_timestamp,
                  {', '.join(d(c) for c in _FACT_DIMS[:13])}, {d('severity')},
                  TRY_CAST(json_extract_string(e.payload,'$.input_tokens') AS BIGINT),
                  TRY_CAST(json_extract_string(e.payload,'$.output_tokens') AS BIGINT),
                  TRY_CAST(json_extract_string(e.payload,'$.duration_ms') AS BIGINT),
                  TRY_CAST(json_extract_string(e.payload,'$.exit_code') AS BIGINT),
                  json_extract_string(e.payload,'$.status'),
                  json_extract_string(e.payload,'$.outcome_status'), e.payload
                FROM s.{table} e WHERE e.event_timestamp > ?
            """,
                [last],
            )
        return conn.execute("SELECT COUNT(*) FROM events_fact").fetchone()[0] - before
    finally:
        conn.execute("DETACH s")


def analytics_db_path() -> Path:
    """Return path to the DuckDB analytics store."""
    return state_dir() / "aggregate_metrics.db"


def connect_analytics(
    db_path: Path | None = None,
    *,
    read_only: bool = True,
) -> duckdb.DuckDBPyConnection:
    """Open a DuckDB connection to the analytics store.

    API routes and CLI reads must use read_only=True (the default).
    Only the aggregation pipeline and projection runners use read_only=False.
    """
    path = db_path or analytics_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _ensure_native_duckdb(path)
    if read_only and not path.exists():
        # read-only cannot create the file; make an empty native store first
        duckdb.connect(str(path)).close()
    return duckdb.connect(str(path), read_only=read_only)


def _refresh_pricing_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Materialize the Claude pricing reference into DuckDB.

    core/pricing/claude_models.py is the single pricing source; this table is a
    projection of it so the token_usage_records view can derive estimated_cost
    the same way execution_spine.record_token_usage does at SQLite insert time
    (WO-TOKEN-VIEW-WIDEN). Refreshed on every schema ensure so price updates
    propagate without a store rebuild.
    """
    from core.pricing.claude_models import CLAUDE_MODEL_PRICING

    conn.execute(
        "CREATE OR REPLACE TABLE token_model_pricing ("
        " model VARCHAR, input_per_m DOUBLE, output_per_m DOUBLE,"
        " cache_write_per_m DOUBLE, cache_read_per_m DOUBLE)"
    )
    for model, p in CLAUDE_MODEL_PRICING.items():
        conn.execute(
            "INSERT INTO token_model_pricing VALUES (?, ?, ?, ?, ?)",
            [model, p["input"], p["output"], p["cache_write"], p["cache_read"]],
        )


def ensure_analytics_schema(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    """Create all analytics tables + read-model views (idempotent)."""
    conn.execute(_ROLLUP_TABLES_DDL)
    conn.execute(_ANALYTICS_TABLES_DDL)
    conn.execute(_EVENTS_FACT_DDL)
    _refresh_pricing_table(conn)  # before the views: token_usage_records joins it
    conn.execute(_PROJECTION_VIEWS_DDL)  # views over events_fact (after it exists)
