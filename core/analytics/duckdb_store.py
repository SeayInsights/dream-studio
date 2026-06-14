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

from pathlib import Path

try:
    import duckdb
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "duckdb is required for the analytics store. " "Run: pip install duckdb>=0.10"
    ) from exc

from core.config.paths import state_dir

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


def analytics_db_path() -> Path:
    """Return path to the DuckDB analytics store."""
    return state_dir() / "aggregate_metrics.db"


def connect_analytics(
    db_path: Path | None = None,
    *,
    read_only: bool = True,
) -> "duckdb.DuckDBPyConnection":
    """Open a DuckDB connection to the analytics store.

    API routes and CLI reads must use read_only=True (the default).
    Only the aggregation pipeline and projection runners use read_only=False.
    """
    path = db_path or analytics_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path), read_only=read_only)


def ensure_analytics_schema(
    conn: "duckdb.DuckDBPyConnection",
) -> None:
    """Create all analytics tables (idempotent)."""
    conn.execute(_ROLLUP_TABLES_DDL)
    conn.execute(_ANALYTICS_TABLES_DDL)
