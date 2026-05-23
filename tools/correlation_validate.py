"""Phase 18.1.3 — Correlation ID validation utility.

Walks recent canonical and raw events and validates that each correlation_id
follows the composition rules defined in core.correlation.composer.

Exit codes:
  0 — all events valid (or no events to check)
  1 — one or more events have malformed correlation_ids
  2 — database not found or query error

Usage::

    py tools/correlation_validate.py [--limit N] [--since DATE] [--db-path PATH] [--json]

Examples::

    py tools/correlation_validate.py --limit 500
    py tools/correlation_validate.py --since 2026-05-22 --json
    py tools/correlation_validate.py --limit 100 --db-path ~/.dream-studio/state/studio.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.correlation.composer import validate as _validate  # noqa: E402

_TABLES = [
    "raw_claude_code_events",
    "business_canonical_events",
    "ai_canonical_events",
]


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
    )


def _validate_table(
    conn: sqlite3.Connection,
    table: str,
    limit: int | None,
    since: str | None,
) -> dict:
    if not _table_exists(conn, table):
        return {"table": table, "skipped": True, "reason": "table not found"}

    # Determine timestamp column name
    ts_col = "received_at" if "received_at" in _column_names(conn, table) else "timestamp"

    where_clauses: list[str] = []
    params: list = []
    if since:
        where_clauses.append(f"{ts_col} >= ?")
        params.append(since)

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
    limit_sql = f"LIMIT {limit}" if limit else ""

    rows = conn.execute(
        f"SELECT event_id, correlation_id FROM {table} {where_sql} ORDER BY {ts_col} DESC {limit_sql}",  # noqa: S608
        params,
    ).fetchall()

    total = len(rows)
    valid_count = 0
    missing_count = 0
    invalid_rows: list[dict] = []

    for event_id, cid in rows:
        if cid is None:
            missing_count += 1
        else:
            ok, err = _validate(cid)
            if ok:
                valid_count += 1
            else:
                invalid_rows.append({"event_id": event_id, "correlation_id": cid, "error": err})

    return {
        "table": table,
        "total_checked": total,
        "valid": valid_count,
        "missing": missing_count,
        "invalid": len(invalid_rows),
        "invalid_rows": invalid_rows,
    }


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}  # noqa: S608


def run_validation(
    db_path: Path,
    limit: int | None,
    since: str | None,
) -> dict:
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA journal_mode = WAL")

    results = []
    for table in _TABLES:
        results.append(_validate_table(conn, table, limit, since))

    conn.close()

    total_checked = sum(r.get("total_checked", 0) for r in results)
    total_valid = sum(r.get("valid", 0) for r in results)
    total_missing = sum(r.get("missing", 0) for r in results)
    total_invalid = sum(r.get("invalid", 0) for r in results)

    return {
        "db_path": str(db_path),
        "tables": results,
        "summary": {
            "total_checked": total_checked,
            "valid": total_valid,
            "missing": total_missing,
            "invalid": total_invalid,
        },
    }


def _print_report(report: dict, json_output: bool) -> None:
    if json_output:
        print(json.dumps(report, indent=2))
        return

    print("\nCorrelation ID Validation Report")
    print(f"Database: {report['db_path']}")
    print("=" * 60)

    for table_result in report["tables"]:
        table = table_result["table"]
        if table_result.get("skipped"):
            print(f"\n  {table}: SKIPPED — {table_result.get('reason')}")
            continue

        checked = table_result["total_checked"]
        valid = table_result["valid"]
        missing = table_result["missing"]
        invalid = table_result["invalid"]
        print(
            f"\n  {table}:\n"
            f"    checked={checked}  valid={valid}  missing={missing}  invalid={invalid}"
        )

        if invalid > 0:
            print("    Malformed correlation_ids:")
            for row in table_result.get("invalid_rows", [])[:10]:
                print(
                    f"      event_id={row['event_id'][:16]}…  "
                    f"cid={str(row['correlation_id'])[:50]}  "
                    f"error={row['error']}"
                )
            if invalid > 10:
                print(f"      … and {invalid - 10} more (use --json for full list)")

        if missing > 0:
            print(f"    WARNING: {missing} events have no correlation_id.")

    s = report["summary"]
    print("\n  TOTALS:")
    print(
        f"    total_checked={s['total_checked']}  valid={s['valid']}  "
        f"missing={s['missing']}  invalid={s['invalid']}"
    )

    if s["invalid"] == 0 and s["missing"] == 0:
        print("\n  RESULT: All correlation_ids are valid.")
    elif s["invalid"] > 0:
        print(f"\n  RESULT: FAIL — {s['invalid']} malformed correlation_id(s) found.")
    else:
        print(f"\n  RESULT: WARN — {s['missing']} event(s) missing correlation_id.")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate correlation IDs across Dream Studio event tables."
    )
    parser.add_argument(
        "--limit", type=int, default=1000, help="Max rows per table (default 1000; 0 = all)"
    )
    parser.add_argument(
        "--since", type=str, help="Only check events received after this ISO date (e.g. 2026-05-22)"
    )
    parser.add_argument("--db-path", type=Path, help="Path to studio.db")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    args = parser.parse_args(argv)

    if args.db_path:
        db_path = args.db_path
    else:
        from core.config.database import _default_db_path

        db_path = _default_db_path()

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        return 2

    limit = args.limit if args.limit > 0 else None

    try:
        report = run_validation(db_path, limit, args.since)
    except sqlite3.Error as exc:
        print(f"ERROR: Database query failed: {exc}", file=sys.stderr)
        return 2

    _print_report(report, args.json_output)

    s = report["summary"]
    if s["invalid"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
