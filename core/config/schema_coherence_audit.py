"""Schema-coherence audit entry point — check_schema_coherence().

Split out of schema_coherence.py (WO-GF-CORE-HEALTH-SKILLS): the single public
entry point that composes the registry, probe, and scan siblings into the
full structural + live-drift audit result.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .schema_coherence_probe import (
    _build_migration_object_inventory,
    _build_migration_only_tables,
)
from .schema_coherence_registry import (
    _CANONICAL_EVENTS_PYTHON_COLS,
    _DUAL_OWNED_TABLES,
    _PYTHON_OWNED_TABLES,
    _SWALLOW_INVENTORY,
)
from .schema_coherence_scan import (
    _effective_swallow_classification,
    _migration_insert_columns,
    _migration_references,
    _staleness_guard,
    _swallowed_casualty_severity,
)


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
