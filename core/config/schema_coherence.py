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
    "canonical_events": "core/event_store/event_store.py:97 (EventStore._init_tables)",
    "validation_failures": "core/event_store/event_store.py:112 (EventStore._init_tables)",
    "action_feedback": "core/repo_actions/feedback.py:244",
    "real_action_feedback": "core/execution/real_feedback.py:200",
    "workflow_executions": "core/projections/workflow_metrics.py:30",
    "workflow_phases": "core/projections/workflow_metrics.py:49",
    "workflow_kpis": "core/projections/workflow_metrics.py:63",
    "phase_kpis": "core/projections/workflow_metrics.py:79",
    "consumer_state": "core/projections/workflow_consumer.py:158",
    "projection_checkpoints": "core/projections/framework.py:1186",
    "proj_workflow_runs": "core/projections/consumers.py:27",
    "proj_skill_stats": "core/projections/consumers.py:146",
    "proj_sessions": "core/projections/consumers.py:241",
    "proj_decision_patterns": "core/projections/consumers.py:335",
    "proj_security_summary": "core/projections/consumers.py:409",
    # memory_fts: dual-owned — migration 079 + retrieval.py both use CREATE VIRTUAL TABLE
    # IF NOT EXISTS (idempotent). Listed here so the staleness guard does not
    # flag retrieval.py as an unregistered call site on FTS5-absent systems.
    "memory_fts": "core/memory/retrieval.py:78 (dual-owned; migration 079 also creates it)",
}

# Dual-owned tables — both Python and a migration create them with IF NOT EXISTS.
# These are NOT aspirational because the migration-side creation is authoritative
# and the Python-side is a harmless idempotent fallback. Reported as informational.
_DUAL_OWNED_TABLES: frozenset[str] = frozenset({"memory_fts"})

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
        "explanation": "Legacy ds_documents absent in migration-only or partial DBs.",
    },
    {
        "pattern": "no such table: canonical_events",
        "classification": "stale",
        "explanation": (
            "Originally added to handle vw_activity_timeline creation failures in migration 062. "
            "vw_activity_timeline was permanently dropped in migration 081 and is not recreated. "
            "The swallow is now overloaded: it silently discards ALTER TABLE (migration 052) and "
            "INSERT (migrations 060, 061, 062, 064) failures that occur because canonical_events "
            "is absent from migration-only DBs. The handler believes it is catching view-creation "
            "errors; no such view exists. This is a second-order aspirational-schema instance: "
            "code believing something untrue about the schema it guards."
        ),
        "remediation": (
            "Do not remove this swallow until its root cause is fixed. "
            "Fix options: (A) move canonical_events DDL into a new migration, "
            "(B) drop migration references to canonical_events (052/060/061/062/064). "
            "After the root cause is fixed, remove the 'canonical_events' entry from the handler."
        ),
        "cross_references": ["docs/architecture/aspirational-schema-debt.md"],
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


def _build_migration_only_tables(source_root: Path) -> set[str]:
    """Run all migrations into a fresh in-memory DB. Return the resulting table names."""
    from core.config.sqlite_bootstrap import run_migrations

    conn = sqlite3.connect(":memory:")
    try:
        run_migrations(conn)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
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
    known = set(_PYTHON_OWNED_TABLES.keys())
    findings: list[dict[str, Any]] = []

    if _override_python_files is not None:
        file_iter = iter(_override_python_files)
    else:

        def file_iter():  # type: ignore[misc]
            for py_file in sorted((source_root / "core").rglob("*.py")):
                rel = str(py_file.relative_to(source_root))
                try:
                    yield rel, py_file.read_text(encoding="utf-8", errors="replace")
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

    # ── Structural: staleness guard ───────────────────────────────────────────
    findings.extend(
        _staleness_guard(
            source_root,
            migration_tables,
            _override_python_files=_override_python_files,
        )
    )

    # ── Structural: stale swallow entries ────────────────────────────────────
    for entry in _SWALLOW_INVENTORY:
        if entry["classification"] == "stale":
            findings.append(
                {
                    "check": "schema_coherence",
                    "severity": "medium",
                    "scope": "structural",
                    "finding_type": "stale_swallow",
                    "pattern": entry["pattern"],
                    "classification": entry["classification"],
                    "explanation": entry["explanation"],
                    "remediation": entry.get("remediation", ""),
                    "cross_references": entry.get("cross_references", []),
                }
            )

    # ── Live drift: probe the live DB ─────────────────────────────────────────
    if live_db_path is not None and live_db_path.is_file():
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
                                "remediation": "Add missing columns via a new migration (ALTER TABLE ADD COLUMN).",
                                "cross_references": [],
                            }
                        )
            finally:
                conn.close()
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
        "summary": summary,
    }
