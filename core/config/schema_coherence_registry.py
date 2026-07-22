"""Schema-coherence registries — Python-owned table inventories and swallow catalog.

Data leaf for the schema_coherence audit (WO-GF-CORE-HEALTH-SKILLS split): the
registries here are consumed by schema_coherence_scan.py and
schema_coherence_audit.py. No behavior, only data.
"""

from __future__ import annotations

from typing import Any

# ── Python-owned table registry ───────────────────────────────────────────────
# Tables created by Python code outside of migrations.
#
# Staleness guard: the audit greps Python source for CREATE TABLE call sites
# and flags any table not in this registry AND not in the migration-only DB.
# Add new Python-side CREATE TABLE call sites here; never let the list drift.
_PYTHON_OWNED_TABLES: dict[str, str] = {
    # canonical_events: REMEDIATED in 18.4.6-followup-1 (migration 083).
    # canonical_events is now migration-owned (migration 083 creates it).
    # EventStore._init_tables and spool/ingestor.py _write_to_sqlite are
    # idempotent fallbacks that defer to the migration. Removed from this
    # registry; the staleness guard will find it in migration_tables and skip it.
    # validation_failures + hook_executions: SQLite tables dropped in migration 129
    # (WO-READMODELS-DUCKDB). They are NOT in this registry: their writers now only emit
    # canonical events, the DuckDB VIEWs serve reads, and the dead duckdb_store.py
    # _PROJECTION_TABLES_DDL_UNUSED constant (which held the only DuckDB-side CREATE TABLE
    # statements) was removed in this WO — so the staleness guard finds no CREATE TABLE site.
    # They are served as DuckDB CREATE OR REPLACE VIEW (not matched by the CREATE TABLE guard).
    "workflow_executions": "core/projections/workflow_metrics.py:30",
    "workflow_phases": "core/projections/workflow_metrics.py:49",
    "workflow_kpis": "core/projections/workflow_metrics.py:63",
    "phase_kpis": "core/projections/workflow_metrics.py:79",
    "consumer_state": "core/projections/workflow_consumer.py:158",
    "projection_checkpoints": "core/projections/framework.py:1186",
    # proj_workflow_runs, proj_skill_stats, proj_sessions, proj_decision_patterns,
    # proj_security_summary: REMOVED from registry — dropped in migration 129 (WO-READMODELS-DUCKDB).
    # consumers.py consumers retired; no live readers existed; DuckDB events_fact is source of truth.
    # memory_fts: dual-owned — migration 079 + retrieval.py both use CREATE VIRTUAL TABLE
    # IF NOT EXISTS (idempotent). Listed here so the staleness guard does not
    # flag retrieval.py as an unregistered call site on FTS5-absent systems.
    "memory_fts": "core/memory/retrieval.py:78 (dual-owned; migration 079 also creates it)",
    # aggregate_metrics.db tables — separate database at state_dir()/aggregate_metrics.db.
    # Not in studio.db; no migration file. Created by ensure_aggregate_schema() in PR #143.
    "finding_rollups": "core/analytics/aggregate_metrics.py:47",
    "rule_fire_rates": "core/analytics/aggregate_metrics.py:60",
    "baseline_trends": "core/analytics/aggregate_metrics.py:73",
    "guard_calibration": "core/analytics/aggregate_metrics.py:86",
    "pattern_catalog": "core/analytics/aggregate_metrics.py:97",
    "recommendation_outcomes": "core/analytics/aggregate_metrics.py:107",
    # duckdb_execution_events — DuckDB execution log created by DuckDBStore in a
    # separate analytics SQLite file (not studio.db). No migration file.
    "duckdb_execution_events": "core/analytics/duckdb_store.py:108",
    # events_fact — DuckDB wide read-model fact table derived from canonical events
    # by the projection runner. Separate analytics store (aggregate_metrics.db),
    # not studio.db; no migration file.
    "events_fact": "core/analytics/duckdb_store.py:270",
    # ds_files — file-tracking table created by FileStore at module load.
    # Not in studio.db; no migration file.
    "ds_files": "core/files/store.py:25",
}

# Dual-owned tables — both Python and a migration create them with IF NOT EXISTS.
# These are NOT aspirational because the migration-side creation is authoritative
# and the Python-side is a harmless idempotent fallback. Reported as informational.
_DUAL_OWNED_TABLES: frozenset[str] = frozenset({"memory_fts"})

# Tables that live in files.db (the three-store document/artifact store), NOT in
# studio.db.  They are created by Python code (ensure_documents_schema in
# document_store.py) and have no studio.db migration file.  The staleness guard
# must recognise these as legitimate so it does not flag them as unregistered
# studio.db tables.
_FILES_DB_TABLES: frozenset[str] = frozenset(
    {
        "ds_documents",
        "ds_documents_fts",
    }
)

# Tables that live in the packet store's own SQLite DB (packets.db), created on
# demand by core/work_orders/packet_store.py (WO-FILESDB-C3, PR #517). Like the
# files.db tables above, they are a separate database from studio.db, so the
# staleness guard must not flag them as unregistered studio.db tables.
_PACKETS_DB_TABLES: frozenset[str] = frozenset(
    {
        "packet_artifacts",
    }
)

# SQL keywords that the CREATE-TABLE regex can spuriously capture as a "table
# name" when the real name is an f-string interpolation (e.g.
# ``CREATE TABLE IF NOT EXISTS {_TABLE}``): the optional IF-NOT-EXISTS group fails
# to complete before the ``{`` and the pattern backtracks onto ``IF``. These are
# never real table names, so the staleness guard skips them.
_DDL_KEYWORD_FALSE_POSITIVES: frozenset[str] = frozenset(
    {
        "if",
        "not",
        "exists",
        "table",
        "virtual",
        "temp",
        "temporary",
    }
)

# Files excluded from the staleness-guard scan.
# The guard's own source and its test file contain DDL-pattern text for
# illustrative/test purposes; scanning them would produce false positives.
_SELF_SCAN_EXCLUDE: frozenset[str] = frozenset(
    {
        "core/config/schema_coherence.py",
        "core/config/schema_coherence_registry.py",
        "core/config/schema_coherence_probe.py",
        "core/config/schema_coherence_scan.py",
        "core/config/schema_coherence_audit.py",
        "tests/unit/test_schema_coherence_audit.py",
        # Build-mode auditor contains SQL pattern descriptions in string literals
        # (e.g., "CREATE TABLE without PRIMARY KEY → BLOCK") — these are detection
        # rule text, not actual DDL; would produce false-positive table names.
        "core/skills/build/database.py",
        # Gate docstring contains prose like "CREATE TABLE for a table" and
        # "CREATE TABLE or a RENAME TO target" — pattern text, not DDL.
        "core/gates/test_fixture_resurrection_guard.py",
        # Nothing-left-hanging detectors contain SQL-pattern prose/regex
        # ("a migration CREATE TABLE for a table ...", INSERT/UPDATE matchers) —
        # detection rule text, not DDL call sites.
        "core/gates/hanging_detectors.py",
        # Independent review prompt template contains "CREATE TABLE IF NOT EXISTS"
        # as an example pattern to detect — not an actual DDL call site.
        "core/work_orders/verify.py",
        # Shared gate comment-stripper: its docstring quotes DDL-pattern prose
        # ("# CREATE TABLE if needed", "DROP TABLE") to explain what it strips —
        # detection rule text, not DDL call sites (WO-GATE-SQL-PARSERS).
        "core/gates/sql_comments.py",
    }
)

# Columns declared in EventStore._init_tables for canonical_events.
# Used in the supplementary column-level pass (Technique 1 extension).
_CANONICAL_EVENTS_PYTHON_COLS: frozenset[str] = frozenset(
    {
        "event_id",
        "event_type",
        "timestamp",
        "trace",
        "severity",
        "payload",
        "actor",
        "confidence_score",
        "source_type",
        "created_at",
    }
)

# Swallow entries in sqlite_bootstrap.py, classified for the audit report.
_SWALLOW_INVENTORY: list[dict[str, Any]] = [
    {
        "pattern": "no such module",
        "classification": "legitimate",
        "explanation": "FTS5 module absent — graceful degradation for envs without FTS5 support.",
    },
    {
        "pattern": "no such table: fts_gotchas",
        "classification": "legitimate",
        "explanation": "Legacy table; graceful fallback when absent.",
    },
    {
        "pattern": "no such table: memory_entries",
        "classification": "legitimate",
        "explanation": (
            "memory_entries absent in partial test fixtures. "
            "memory_entries IS declared in migrations 011/078."
        ),
    },
    {
        "pattern": "no such table: ds_documents",
        "classification": "legitimate",
        "explanation": (
            "ds_documents is absent in studio.db — it was created in migration 007 and "
            "dropped in migration 127 (three-store architecture fix: ds_documents now "
            "lives in files.db). Partial/migration-only DBs and fresh installs after "
            "migration 127 will not have this table."
        ),
    },
    {
        "pattern": "no such table: canonical_events",
        "classification": "legitimate",
        "explanation": (
            "Migrations 052-064 reference canonical_events but run BEFORE migration 083 "
            "(which creates canonical_events) in the migration sequence. On fresh installs, "
            "those older migrations fail with 'no such table: canonical_events' and are "
            "swallowed here. This is intentional graceful degradation. "
            "Migration 083 (18.4.6-followup-1) made canonical_events migration-owned; "
            "the swallow remains necessary for the pre-083 references and is no longer stale."
        ),
    },
    {
        "pattern": "no such table: token_usage_records / ai_usage_operational_records",
        "classification": "legitimate",
        "explanation": (
            "Migration 081 table-reconstruction pattern. Partial test fixtures without "
            "source tables skip the INSERT...SELECT step gracefully."
        ),
    },
    {
        "pattern": "no such column in token_usage_records / ai_usage_operational_records",
        "classification": "legitimate",
        "explanation": "Migration 081 INSERT from partial fixture with columns absent before 042/043.",
    },
    {
        "pattern": "no such table: ds_projects/ds_milestones/ds_work_orders/ds_tasks/ds_design_briefs/ds_work_order_types",
        "classification": "legitimate",
        "explanation": (
            "Migration 070 ds_* → business_* copy. Pre-048 fixtures have no ds_* source tables; "
            "business_* tables are created empty, which is correct."
        ),
    },
    {
        "pattern": "no such column on CREATE INDEX",
        "classification": "legitimate",
        "explanation": "Index on pre-existing table with minimal schema in test fixtures. Queries still work.",
    },
    {
        "pattern": "no such column in ds_* / business_* tables (migration 070 context)",
        "classification": "legitimate",
        "explanation": "Migration 070 partial-fixture tolerance. ds_* tables are always empty in fixtures.",
    },
]
