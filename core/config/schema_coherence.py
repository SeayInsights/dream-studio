"""Aspirational schema audit — detects schema references that fail at runtime.

Two scopes of finding:
  structural  — detected via migration replay + schema diff + migration grep.
                Same result on every machine; independent of live DB state.
  live_drift  — detected by probing the live DB. Machine-specific.

Usage:
    from core.config.schema_coherence import check_schema_coherence
    result = check_schema_coherence(source_root=source_root)
    result = check_schema_coherence(source_root=source_root, live_db_path=db_path)
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
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
    "action_feedback": "core/repo_actions/feedback.py:244",
    "real_action_feedback": "core/execution/real_feedback.py:200",
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

# Files excluded from the staleness-guard scan.
# The guard's own source and its test file contain DDL-pattern text for
# illustrative/test purposes; scanning them would produce false positives.
_SELF_SCAN_EXCLUDE: frozenset[str] = frozenset(
    {
        "core/config/schema_coherence.py",
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


def _build_migration_object_inventory(source_root: Path) -> dict[str, dict[str, str]]:
    """Build the set of indexes and triggers a full migration sequence should produce.

    Returns:
        {
          "indexes": {name: sql_ddl},   # sql_ddl used to determine UNIQUE vs non-unique
          "triggers": {name: sql_ddl},
        }

    Views are excluded: the M1-scar class (live-only objects like vw_activity_timeline,
    present-in-live/absent-in-fresh) is the opposite direction from a swallowed casualty
    and would false-positive without direction-aware diffing. Revisit when a fresh-only
    view casualty is confirmed.
    """
    from core.config.sqlite_bootstrap import run_migrations

    conn = sqlite3.connect(":memory:")
    try:
        run_migrations(conn)
        indexes = {
            row[0]: (row[1] or "")
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        triggers = {
            row[0]: (row[1] or "")
            for row in conn.execute(
                "SELECT name, sql FROM sqlite_master WHERE type='trigger'"
            ).fetchall()
        }
        return {"indexes": indexes, "triggers": triggers}
    finally:
        conn.close()


def _swallowed_casualty_severity(obj_type: str, ddl: str) -> str:
    """Derive severity from object type and DDL text.

    - Trigger: high (correctness loss — the automated op doesn't run)
    - UNIQUE index: high (uniqueness constraint unenforced = silent data-integrity loss)
    - Non-unique index: medium (performance loss only)

    Severity is derived from the DDL so future migrations get correct severity
    automatically — no hardcoded per-index list to maintain.
    """
    if obj_type == "trigger":
        return "high"
    if "UNIQUE" in ddl.upper():
        return "high"
    return "medium"


def _effective_swallow_classification(entry: dict[str, Any], migration_tables: set[str]) -> str:
    """Derive the real classification of a swallow entry from migration schema state.

    For "no such table: X" patterns, probes migration_tables rather than trusting the
    hardcoded classification string. This prevents the audit from being silenced by
    editing a comment — the finding reflects the actual schema state, not a label.

    Classification logic:
      - "no such table: X" AND X in migration_tables:
          Intentional sequencing — the table exists migration-side but an older migration
          runs before the table-creation migration. "legitimate".
      - "no such table: X" AND X NOT in migration_tables AND X in _PYTHON_OWNED_TABLES:
          Python-owned table referenced by migrations, still absent from migrations.
          This is real aspirational-schema debt. "stale".
      - All other patterns (module errors, column errors, legacy-gone tables):
          Fall back to the hardcoded classification string.
    """
    pattern = entry.get("pattern", "")
    hardcoded = entry.get("classification", "legitimate")

    if "no such table:" not in pattern:
        return hardcoded

    # Extract the first table name after "no such table:" — handles compound entries like
    # "no such table: token_usage_records / ai_usage_operational_records"
    after = pattern.split("no such table:", 1)[-1].strip()
    table_name = after.split()[0].rstrip("/,;")

    if table_name in migration_tables:
        # Table exists in migration-only DB: the swallow is intentional sequencing.
        # Even if the hardcoded classification says "stale", reality wins.
        return "legitimate"

    if table_name in _PYTHON_OWNED_TABLES:
        # Table is Python-owned and still absent from migrations: real schema debt.
        # Even if the hardcoded classification says "legitimate", reality wins.
        return "stale"

    # Unknown/legacy table (e.g., fts_gotchas, ds_documents — gone and not in the
    # Python-owned registry): fall back to the hardcoded classification.
    return hardcoded


def _build_migration_only_tables(source_root: Path) -> set[str]:
    """Run all migrations into a fresh in-memory DB. Return the resulting table and view names.

    VIEWs are included because a migration may convert a table to a view (e.g. migration 102
    retired the canonical_events TABLE and replaced it with a VIEW of the same name). Both
    are migration-owned schema objects and must be excluded from the staleness guard.
    """
    from core.config.sqlite_bootstrap import run_migrations

    conn = sqlite3.connect(":memory:")
    try:
        run_migrations(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master"
            " WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%'"
        )
        return {row[0] for row in cursor.fetchall()}
    finally:
        conn.close()


def _migration_references(migration_dir: Path, table_name: str) -> list[dict[str, Any]]:
    """Find migration files that structurally reference table_name in SQL.

    Only matches lines where table_name appears in a structural SQL context
    (FROM, JOIN, INTO, ON, UPDATE, TABLE, ALTER TABLE) to avoid false positives
    from comment-only references or string-literal occurrences.
    """
    escaped = re.escape(table_name)
    structural_re = re.compile(
        r"(?:FROM|JOIN|INTO|ON|UPDATE|TABLE)\s+" + escaped + r"|ALTER\s+TABLE\s+" + escaped,
        re.IGNORECASE,
    )
    trailing_comment_re = re.compile(r"\s*--.*$")
    hits: list[dict[str, Any]] = []
    for sql_file in sorted(migration_dir.glob("[0-9]*.sql")):
        text = sql_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("--"):
                continue
            # Strip trailing inline comment before matching
            without_comment = trailing_comment_re.sub("", stripped)
            if structural_re.search(without_comment):
                hits.append(
                    {
                        "migration": sql_file.name,
                        "line": line_no,
                        "context": stripped[:120],
                    }
                )
    return hits


def _migration_insert_columns(migration_dir: Path, table_name: str) -> list[dict[str, Any]]:
    """Find INSERT INTO <table_name> column lists in migration files."""
    # Match INSERT [OR IGNORE] INTO table (col, ...) — across potential newlines
    pattern = re.compile(
        r"INSERT\s+(?:OR\s+\w+\s+)?INTO\s+" + re.escape(table_name) + r"\s*\(([^)]+)\)",
        re.IGNORECASE | re.DOTALL,
    )
    results: list[dict[str, Any]] = []
    for sql_file in sorted(migration_dir.glob("[0-9]*.sql")):
        text = sql_file.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            raw_cols = match.group(1)
            cols = [c.strip() for c in raw_cols.replace("\n", " ").split(",") if c.strip()]
            line_no = text[: match.start()].count("\n") + 1
            results.append(
                {
                    "migration": sql_file.name,
                    "line": line_no,
                    "columns": cols,
                }
            )
    return results


def _staleness_guard(
    source_root: Path,
    migration_tables: set[str],
    *,
    _override_python_files: list[tuple[str, str]] | None = None,
) -> list[dict[str, Any]]:
    """Inventory Python-side table declarations not in the registered set.

    Scans Python source under core/ for DDL patterns and flags any table
    that is neither in _PYTHON_OWNED_TABLES nor in the migration-only DB.

    Args:
        source_root: repo root, used to scan core/*.py
        migration_tables: tables present in a migration-only DB replay
        _override_python_files: (filename, content) pairs injected by tests
                                 instead of scanning the real filesystem
    """
    create_table_re = re.compile(
        r"CREATE\s+(?:VIRTUAL\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?['\"]?(\w+)['\"]?",
        re.IGNORECASE,
    )
    # Include files.db tables so the staleness guard does not flag them as
    # unregistered studio.db tables (they live in a separate database).
    known = set(_PYTHON_OWNED_TABLES.keys()) | _FILES_DB_TABLES
    findings: list[dict[str, Any]] = []

    if _override_python_files is not None:
        file_iter = iter(_override_python_files)
    else:

        def file_iter():  # type: ignore[misc]
            for py_file in sorted((source_root / "core").rglob("*.py")):
                # Normalise to forward-slash posix for cross-platform exclusion matching.
                rel_posix = py_file.relative_to(source_root).as_posix()
                if rel_posix in _SELF_SCAN_EXCLUDE:
                    continue
                try:
                    yield rel_posix, py_file.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    pass

        file_iter = file_iter()

    for filename, content in file_iter:
        for line_no, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            for match in create_table_re.finditer(stripped):
                table = match.group(1).lower()
                if table.startswith("_"):
                    continue
                if table in known:
                    continue
                if table in migration_tables:
                    continue
                findings.append(
                    {
                        "check": "schema_coherence",
                        "severity": "medium",
                        "scope": "structural",
                        "finding_type": "unregistered_python_owned_table",
                        "table": table,
                        "file": filename,
                        "line": line_no,
                        "explanation": (
                            f"Python source at {filename}:{line_no} creates table '{table}' "
                            "outside of migrations, but it is not registered in the "
                            "schema_coherence audit inventory (_PYTHON_OWNED_TABLES in "
                            "core/config/schema_coherence.py)."
                        ),
                        "remediation": (
                            f"Add '{table}' to _PYTHON_OWNED_TABLES with its source location, "
                            "or move the table definition into a migration."
                        ),
                        "cross_references": [],
                    }
                )
    return findings


def check_schema_coherence(
    source_root: Path,
    *,
    live_db_path: Path | None = None,
    _override_python_files: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """Run the aspirational-schema audit.

    Args:
        source_root: repo root (contains core/event_store/migrations/)
        live_db_path: optional path to the live studio.db for live-drift probes
        _override_python_files: injected by tests to avoid scanning real filesystem

    Returns dict with keys:
        status: "pass" | "findings"
        findings: list of finding dicts (each has severity, scope, finding_type, ...)
        scope_structural: count of structural findings
        scope_live_drift: count of live_drift findings
        summary: {"high": N, "medium": N, "low": N, "informational": N}
    """
    migration_dir = source_root / "core" / "event_store" / "migrations"
    findings: list[dict[str, Any]] = []

    # ── Structural: migration replay ──────────────────────────────────────────
    migration_tables = _build_migration_only_tables(source_root)

    for table, location in _PYTHON_OWNED_TABLES.items():
        is_dual_owned = table in _DUAL_OWNED_TABLES
        in_migration_only_db = table in migration_tables

        if is_dual_owned:
            if not in_migration_only_db:
                # e.g. memory_fts on FTS5-absent system
                findings.append(
                    {
                        "check": "schema_coherence",
                        "severity": "informational",
                        "scope": "structural",
                        "finding_type": "dual_owned_table_fts_absent",
                        "table": table,
                        "location": location,
                        "explanation": (
                            f"Table '{table}' is dual-owned (Python + migration both create it "
                            "with IF NOT EXISTS). On this system the migration-side creation "
                            "failed (likely FTS5 absent), leaving Python as sole creator."
                        ),
                        "remediation": "Ensure FTS5 is available, or treat as informational.",
                        "cross_references": [],
                    }
                )
            continue

        if in_migration_only_db:
            # Table IS created by migrations → not Python-owned in the aspirational sense.
            # Should not appear in _PYTHON_OWNED_TABLES unless it's dual-owned.
            continue

        # Table is Python-owned (absent from migration-only DB). Check for references.
        refs = _migration_references(migration_dir, table)
        if not refs:
            findings.append(
                {
                    "check": "schema_coherence",
                    "severity": "low",
                    "scope": "structural",
                    "finding_type": "python_owned_table_no_migration_ref",
                    "table": table,
                    "location": location,
                    "explanation": (
                        f"Table '{table}' is created by Python code ({location}) and has no "
                        "references in any migration. Schema fragmentation: this table is "
                        "invisible to the migration runner."
                    ),
                    "remediation": (
                        f"Consider moving '{table}' DDL into a migration for full schema visibility."
                    ),
                    "cross_references": [],
                }
            )
            continue

        # Python-owned AND referenced by migrations → aspirational (structural).
        # Deduplicate: report one finding per migration file, not per line.
        seen_migrations: set[str] = set()
        for ref in refs:
            if ref["migration"] in seen_migrations:
                continue
            seen_migrations.add(ref["migration"])
            findings.append(
                {
                    "check": "schema_coherence",
                    "severity": "medium",
                    "scope": "structural",
                    "finding_type": "python_owned_table_in_migration",
                    "table": table,
                    "location": location,
                    "migration": ref["migration"],
                    "line": ref["line"],
                    "context": ref["context"],
                    "explanation": (
                        f"Migration '{ref['migration']}' references table '{table}', "
                        f"but '{table}' is created by Python code ({location}), not by any migration. "
                        "On a migration-only DB (fresh install, CI fixture, alternative bootstrapper), "
                        "this reference silently fails. The system works only because Python "
                        "initializes after migrations and the exception handler swallows the error."
                    ),
                    "remediation": (
                        f"Option A: Move '{table}' DDL into a migration (superset of Python + migration columns). "
                        f"Option B: Remove migration references to '{table}'. "
                        "See docs/architecture/aspirational-schema-debt.md."
                    ),
                    "cross_references": ["docs/architecture/aspirational-schema-debt.md"],
                }
            )

        # Supplementary column-level pass: only meaningful for canonical_events today.
        # Deduplicate: one finding per (migration, missing_cols set) — a migration with
        # multiple INSERT statements with the same mismatch produces a single finding.
        if table == "canonical_events":
            seen_col_findings: set[tuple[str, frozenset[str]]] = set()
            for insert in _migration_insert_columns(migration_dir, table):
                extra_cols = [
                    c for c in insert["columns"] if c not in _CANONICAL_EVENTS_PYTHON_COLS
                ]
                if not extra_cols:
                    continue
                dedup_key = (insert["migration"], frozenset(extra_cols))
                if dedup_key in seen_col_findings:
                    continue
                seen_col_findings.add(dedup_key)
                findings.append(
                    {
                        "check": "schema_coherence",
                        "severity": "high",
                        "scope": "structural",
                        "finding_type": "column_absent_from_python_ddl",
                        "table": table,
                        "migration": insert["migration"],
                        "line": insert["line"],
                        "missing_columns": extra_cols,
                        "python_ddl_location": location,
                        "explanation": (
                            f"Migration '{insert['migration']}' inserts into columns "
                            f"{extra_cols} of '{table}', but those columns are not declared "
                            f"in the Python DDL at {location}. "
                            "On upgrade paths where the table was previously created by Python init "
                            "(canonical_events exists with only the Python-declared 10 columns), "
                            "this INSERT fails with an unhandled 'no such column' error "
                            "that the swallow handler does NOT catch."
                        ),
                        "remediation": (
                            "Option A: Move canonical_events into a migration with the full column set "
                            "(EventStore._init_tables 10 cols + raw_prompt_retained + "
                            "raw_tool_output_retained + schema_version + invocation_mode). "
                            "Option B: Remove the INSERT statements from migrations 061/062/064. "
                            "See docs/architecture/aspirational-schema-debt.md."
                        ),
                        "cross_references": ["docs/architecture/aspirational-schema-debt.md"],
                    }
                )

    # ── Structural: cross-reference enrichment ───────────────────────────────
    # For migrations that have BOTH a python_owned_table_in_migration medium AND a
    # column_absent_from_python_ddl high, enrich the medium's explanation so a reader
    # can distinguish the ghost-view reference (historical, low risk) from the live
    # INSERT column mismatch (actionable, unguarded crash path).
    _high_mig = {
        f["migration"] for f in findings if f.get("finding_type") == "column_absent_from_python_ddl"
    }
    for f in findings:
        if f.get("finding_type") != "python_owned_table_in_migration":
            continue
        mig = f.get("migration", "")
        ctx = f.get("context", "").upper()
        # Detect view-query ghost: matched line is a FROM clause (SELECT/VIEW context).
        is_view_ghost = ctx.startswith("FROM ") or " FROM " in ctx
        if mig in _high_mig:
            suffix = (
                " — This reference is the dropped vw_activity_timeline view text "
                "(migration 062 DDL; view permanently dropped by migration 081). "
                "The view is gone but its immutable SQL remains in this migration file. "
                "See the separate column_absent_from_python_ddl HIGH finding on this "
                "same migration for the live, unguarded crash path."
                if is_view_ghost
                else " — This migration also has a column_absent_from_python_ddl HIGH "
                "finding (live unguarded crash path). See that finding for the "
                "actionable issue; this medium documents the structural reference."
            )
            f["explanation"] = f["explanation"] + suffix

    # ── Structural: staleness guard ───────────────────────────────────────────
    findings.extend(
        _staleness_guard(
            source_root,
            migration_tables,
            _override_python_files=_override_python_files,
        )
    )

    # ── Structural: stale swallow entries ────────────────────────────────────
    # Uses _effective_swallow_classification() to probe migration_tables rather than
    # trusting the hardcoded classification string. This prevents the audit from being
    # silenced by relabeling a swallow entry without fixing the underlying schema.
    for entry in _SWALLOW_INVENTORY:
        effective = _effective_swallow_classification(entry, migration_tables)
        if effective == "stale":
            findings.append(
                {
                    "check": "schema_coherence",
                    "severity": "medium",
                    "scope": "structural",
                    "finding_type": "stale_swallow",
                    "pattern": entry["pattern"],
                    "classification": effective,
                    "explanation": entry["explanation"],
                    "remediation": entry.get("remediation", ""),
                    "cross_references": entry.get("cross_references", []),
                }
            )

    # ── Live drift: probe the live DB ─────────────────────────────────────────
    # Probe status is always explicit: "ran: N findings", "ran: 0 findings",
    # or "skipped: no DB at <path>" — never a silent zero.
    live_drift_probe_status: str
    live_drift_findings_before = len([f for f in findings if f.get("scope") == "live_drift"])

    if live_db_path is None:
        live_drift_probe_status = "skipped: live_db_path not provided"
    elif not live_db_path.is_file():
        live_drift_probe_status = f"skipped: no DB at {live_db_path}"
    else:
        try:
            conn = sqlite3.connect(str(live_db_path), timeout=5.0)
            conn.row_factory = sqlite3.Row
            try:
                row = conn.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' AND name='canonical_events'"
                ).fetchone()
                if row:
                    live_cols = {
                        r["name"]
                        for r in conn.execute("PRAGMA table_info(canonical_events)").fetchall()
                    }
                    missing_in_live = _CANONICAL_EVENTS_PYTHON_COLS - live_cols
                    if missing_in_live:
                        findings.append(
                            {
                                "check": "schema_coherence",
                                "severity": "high",
                                "scope": "live_drift",
                                "finding_type": "live_db_column_missing",
                                "table": "canonical_events",
                                "missing_columns": sorted(missing_in_live),
                                "explanation": (
                                    f"Live DB canonical_events is missing columns "
                                    f"{sorted(missing_in_live)} that EventStore._init_tables declares. "
                                    "The table may have been created by an older EventStore version."
                                ),
                                "remediation": (
                                    "Add missing columns via a new migration (ALTER TABLE ADD COLUMN)."
                                ),
                                "cross_references": [],
                            }
                        )

                # ── Swallowed-statement casualties: index and trigger diff ──────────
                # Compare live DB's index/trigger inventory against the migration-only set.
                # Objects present in migration-only (fresh) but ABSENT in live are M2
                # casualties: a migration intended to create them but the swallow handler
                # silently discarded the creation statement.
                # Direction-aware: only flag fresh-only absences (M2 class). Live-only
                # objects (vw_activity_timeline etc.) are M1 scars — the opposite
                # direction — and are intentionally not flagged here.
                # Views excluded: M1-scar class (live-only views like vw_activity_timeline)
                # would false-positive; revisit when a fresh-only view casualty is confirmed.
                migration_inventory = _build_migration_object_inventory(source_root)
                live_indexes = {
                    r["name"]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='index' AND name NOT LIKE 'sqlite_%'"
                    ).fetchall()
                }
                live_triggers = {
                    r["name"]
                    for r in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='trigger'"
                    ).fetchall()
                }
                for missing_idx, ddl in sorted(migration_inventory["indexes"].items()):
                    if missing_idx not in live_indexes:
                        sev = _swallowed_casualty_severity("index", ddl)
                        findings.append(
                            {
                                "check": "schema_coherence",
                                "severity": sev,
                                "scope": "live_drift",
                                "finding_type": "swallowed_statement_casualty",
                                "object_type": "index",
                                "object_name": missing_idx,
                                "explanation": (
                                    f"Index '{missing_idx}' is declared by a migration but absent "
                                    "from the live DB. A swallow handler silently discarded its "
                                    "creation — the migration runner reported success but the object "
                                    "was never created (M2 mechanism). "
                                    + (
                                        "UNIQUE index: the uniqueness constraint is unenforced, "
                                        "which may cause silent data-integrity failures."
                                        if "UNIQUE" in ddl.upper()
                                        else "Non-unique index: performance impact only, "
                                        "no correctness loss."
                                    )
                                ),
                                "remediation": (
                                    "Add the index via a repair migration. "
                                    "See docs/architecture/aspirational-schema-debt.md for the "
                                    "M2 mechanism and docs/architecture/event-store-corruption-tolerance.md "
                                    "for the repair-migration pattern."
                                ),
                                "cross_references": [
                                    "docs/architecture/aspirational-schema-debt.md"
                                ],
                            }
                        )
                for missing_trig, ddl in sorted(migration_inventory["triggers"].items()):
                    if missing_trig not in live_triggers:
                        findings.append(
                            {
                                "check": "schema_coherence",
                                "severity": "high",
                                "scope": "live_drift",
                                "finding_type": "swallowed_statement_casualty",
                                "object_type": "trigger",
                                "object_name": missing_trig,
                                "explanation": (
                                    f"Trigger '{missing_trig}' is declared by a migration but absent "
                                    "from the live DB. A swallow handler silently discarded its "
                                    "creation. Trigger absence is a correctness loss: the automated "
                                    "operation the trigger performs (FTS sync, access tracking, etc.) "
                                    "will not run."
                                ),
                                "remediation": (
                                    "Add the trigger via a repair migration "
                                    "(pattern: migration 082 for FTS triggers)."
                                ),
                                "cross_references": [
                                    "docs/architecture/aspirational-schema-debt.md"
                                ],
                            }
                        )
            finally:
                conn.close()
            n_new = (
                len([f for f in findings if f.get("scope") == "live_drift"])
                - live_drift_findings_before
            )
            live_drift_probe_status = f"ran: {n_new} finding{'s' if n_new != 1 else ''}"
        except Exception as exc:
            findings.append(
                {
                    "check": "schema_coherence",
                    "severity": "low",
                    "scope": "live_drift",
                    "finding_type": "live_db_probe_failed",
                    "table": None,
                    "explanation": f"Could not probe live DB at {live_db_path}: {exc}",
                    "remediation": "",
                    "cross_references": [],
                }
            )
            live_drift_probe_status = f"error: {exc}"

    # ── Summarise ─────────────────────────────────────────────────────────────
    structural = [f for f in findings if f.get("scope") == "structural"]
    live_drift = [f for f in findings if f.get("scope") == "live_drift"]
    summary = {
        "high": sum(1 for f in findings if f.get("severity") == "high"),
        "medium": sum(1 for f in findings if f.get("severity") == "medium"),
        "low": sum(1 for f in findings if f.get("severity") == "low"),
        "informational": sum(1 for f in findings if f.get("severity") == "informational"),
    }
    has_findings = summary["high"] > 0 or summary["medium"] > 0
    return {
        "status": "findings" if has_findings else ("low_findings" if findings else "pass"),
        "findings": findings,
        "scope_structural": len(structural),
        "scope_live_drift": len(live_drift),
        "live_drift_probe_status": live_drift_probe_status,
        "summary": summary,
    }
