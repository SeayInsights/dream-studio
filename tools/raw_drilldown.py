#!/usr/bin/env python3
"""Phase 18.1.1 drill-down verification utility for raw_claude_code_events.

Proves raw is queryable for correlation-ID-based drill-down per v2 data
architecture Commitments 6 (drill-down first-class) and 8 (mandatory indexing).

Usage examples:
  py tools/raw_drilldown.py --stats
  py tools/raw_drilldown.py --hook-id on-tool-activity --limit 10
  py tools/raw_drilldown.py --event-type skill.invoked
  py tools/raw_drilldown.py --project-id dream-studio-clean
  py tools/raw_drilldown.py --correlation-id "hook-on-tool-activity"
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

TABLE_NAME = "raw_claude_code_events"

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _resolve_db_path(override: str | None) -> Path:
    if override:
        return Path(override)
    env = os.environ.get("DREAM_STUDIO_DB_PATH")
    if env:
        return Path(env)
    return Path.home() / ".dream-studio" / "state" / "studio.db"


def _open_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def _table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE_NAME,),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Stats mode
# ---------------------------------------------------------------------------


def _run_stats(conn: sqlite3.Connection) -> int:
    total = conn.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]

    type_rows = conn.execute(
        f"SELECT event_type, COUNT(*) AS cnt FROM {TABLE_NAME} GROUP BY event_type ORDER BY cnt DESC"
    ).fetchall()
    distinct_types = len(type_rows)

    date_row = conn.execute(
        f"SELECT MIN(received_at), MAX(received_at) FROM {TABLE_NAME}"
    ).fetchone()

    corr_row = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE correlation_id IS NOT NULL AND correlation_id != ''"
    ).fetchone()

    session_row = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE session_id IS NOT NULL AND session_id != ''"
    ).fetchone()

    project_row = conn.execute(
        f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE project_id IS NOT NULL AND project_id != ''"
    ).fetchone()

    corr_pct = (corr_row[0] / total * 100) if total else 0.0
    session_pct = (session_row[0] / total * 100) if total else 0.0
    project_pct = (project_row[0] / total * 100) if total else 0.0

    print(f"=== {TABLE_NAME} statistics ===")
    print(f"  Total rows          : {total:,}")
    print(f"  Distinct event types: {distinct_types}")
    if type_rows:
        for r in type_rows:
            print(f"    {r['event_type'] or '(null)':50s}  {r['cnt']:>6,}")
    print(f"  Date range          : {date_row[0]} to {date_row[1]}")
    print(f"  correlation_id set  : {corr_row[0]:,} ({corr_pct:.1f}% of total)")
    print(f"  session_id set      : {session_row[0]:,} ({session_pct:.1f}% of total)")
    print(f"  project_id set      : {project_row[0]:,} ({project_pct:.1f}% of total)")
    return 0


# ---------------------------------------------------------------------------
# Filter query
# ---------------------------------------------------------------------------


def _build_query(args: argparse.Namespace) -> tuple[str, list]:
    """Return (sql, params) for the filter query."""
    conditions: list[str] = []
    params: list = []

    if args.correlation_id:
        conditions.append("correlation_id LIKE ?")
        params.append(f"%{args.correlation_id}%")
    if args.session_id:
        conditions.append("session_id = ?")
        params.append(args.session_id)
    if args.workflow_id:
        conditions.append("workflow_id = ?")
        params.append(args.workflow_id)
    if args.skill_id:
        conditions.append("skill_id = ?")
        params.append(args.skill_id)
    if args.hook_id:
        conditions.append("hook_id = ?")
        params.append(args.hook_id)
    if args.tool_id:
        conditions.append("tool_id = ?")
        params.append(args.tool_id)
    if args.project_id:
        conditions.append("project_id = ?")
        params.append(args.project_id)
    if args.event_type:
        conditions.append("event_type = ?")
        params.append(args.event_type)

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    limit = args.limit if args.limit and args.limit > 0 else 50

    sql = (
        f"SELECT event_id, event_type, event_timestamp, received_at, "
        f"correlation_id, session_id, project_id, workflow_id, skill_id, "
        f"hook_id, tool_id, model_id, adapter_id, schema_version, source_payload "
        f"FROM {TABLE_NAME} "
        f"{where} "
        f"ORDER BY received_at ASC "
        f"LIMIT ?"
    )
    params.append(limit)
    return sql, params


def _run_filter(conn: sqlite3.Connection, args: argparse.Namespace) -> int:
    sql, params = _build_query(args)
    rows = conn.execute(sql, params).fetchall()

    if args.json:
        out = []
        for r in rows:
            d = dict(r)
            # Parse source_payload if it's JSON text
            if d.get("source_payload"):
                try:
                    d["source_payload"] = json.loads(d["source_payload"])
                except (json.JSONDecodeError, TypeError):
                    pass
            out.append(d)
        print(json.dumps(out, indent=2, default=str))
        return 0

    # Table output
    if not rows:
        print("No rows matched the given filters.")
        return 0

    # Column widths
    id_w = 10  # first 8 chars + 2 padding
    type_w = 30
    ts_w = 24
    corr_w = 42  # first 40 chars + 2 padding

    header = (
        f"{'event_id':<{id_w}}  "
        f"{'event_type':<{type_w}}  "
        f"{'event_timestamp':<{ts_w}}  "
        f"{'correlation_id':<{corr_w}}"
    )
    sep = "-" * len(header)
    print(header)
    print(sep)

    for r in rows:
        eid = (r["event_id"] or "")[:8]
        etype = (r["event_type"] or "")[:type_w]
        ets = (r["event_timestamp"] or r["received_at"] or "")[:ts_w]
        corr = (r["correlation_id"] or "")[:40]
        print(f"{eid:<{id_w}}  " f"{etype:<{type_w}}  " f"{ets:<{ts_w}}  " f"{corr:<{corr_w}}")

    print(sep)
    print(f"  {len(rows)} row(s) returned")
    return 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="raw_drilldown.py",
        description="Drill-down verification utility for raw_claude_code_events.",
    )
    p.add_argument(
        "--correlation-id",
        metavar="TEXT",
        help="Match events where correlation_id LIKE '%%{value}%%'",
    )
    p.add_argument("--session-id", metavar="TEXT", help="Match events by session_id")
    p.add_argument("--workflow-id", metavar="TEXT", help="Match events by workflow_id")
    p.add_argument("--skill-id", metavar="TEXT", help="Match events by skill_id")
    p.add_argument("--hook-id", metavar="TEXT", help="Match events by hook_id")
    p.add_argument("--tool-id", metavar="TEXT", help="Match events by tool_id")
    p.add_argument("--project-id", metavar="TEXT", help="Match events by project_id")
    p.add_argument("--event-type", metavar="TEXT", help="Match events by event_type")
    p.add_argument(
        "--limit", metavar="INT", type=int, default=50, help="Max rows to return (default: 50)"
    )
    p.add_argument("--db-path", metavar="PATH", help="Override DB path")
    p.add_argument("--json", action="store_true", help="Output as JSON instead of table")
    p.add_argument("--stats", action="store_true", help="Show table statistics (no filter needed)")
    return p


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    db_path = _resolve_db_path(args.db_path)
    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}", file=sys.stderr)
        return 1

    try:
        conn = _open_db(db_path)
    except sqlite3.Error as exc:
        print(f"ERROR: Could not open DB: {exc}", file=sys.stderr)
        return 1

    try:
        if not _table_exists(conn):
            print(f"{TABLE_NAME} table does not exist yet — run migration 066 first")
            return 1

        if args.stats:
            return _run_stats(conn)

        # Require at least one filter when not in stats mode
        filter_given = any(
            [
                args.correlation_id,
                args.session_id,
                args.workflow_id,
                args.skill_id,
                args.hook_id,
                args.tool_id,
                args.project_id,
                args.event_type,
            ]
        )
        if not filter_given:
            parser.print_help()
            print(
                "\nProvide at least one filter (or --stats to inspect the table).",
                file=sys.stderr,
            )
            return 1

        return _run_filter(conn, args)

    except sqlite3.Error as exc:
        print(f"ERROR: Query failed: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
