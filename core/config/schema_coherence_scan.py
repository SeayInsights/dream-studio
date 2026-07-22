"""Schema-coherence scan helpers — migration-text greps and classification logic.

Split out of schema_coherence.py (WO-GF-CORE-HEALTH-SKILLS): these functions
scan migration SQL files and Python source for structural DDL evidence, and
classify swallowed-error severity for schema_coherence_audit.py.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .schema_coherence_registry import (
    _DDL_KEYWORD_FALSE_POSITIVES,
    _FILES_DB_TABLES,
    _PACKETS_DB_TABLES,
    _PYTHON_OWNED_TABLES,
    _SELF_SCAN_EXCLUDE,
)


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
    known = set(_PYTHON_OWNED_TABLES.keys()) | _FILES_DB_TABLES | _PACKETS_DB_TABLES
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
                if table in _DDL_KEYWORD_FALSE_POSITIVES:
                    # Regex backtracking artifact on an f-string-interpolated name
                    # (e.g. "CREATE TABLE IF NOT EXISTS {_TABLE}") — not a real table.
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
