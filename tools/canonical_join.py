#!/usr/bin/env python3
"""Correlation join verification utility for the v2 dual canonical architecture.

Given a correlation_id, retrieves matching rows from both business_canonical_events
and ai_canonical_events, formatted for readability.

Usage:
  py tools/canonical_join.py [--db-path PATH] [--list] [--correlation-id ID]
                              [--limit N] [--json]

Options:
  --list              List distinct correlation_ids present in either canonical table
  --correlation-id ID Join both tables on this correlation_id and display results
  --limit N           Limit rows returned per table (default: 20)
  --json              Emit raw JSON instead of formatted text
  --db-path PATH      Override DB path (uses DREAM_STUDIO_DB_PATH or ~/.dream-studio/state/studio.db)
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

DB_PATH_ENV = "DREAM_STUDIO_DB_PATH"
_DEFAULT_DB_PATH = Path.home() / ".dream-studio" / "state" / "studio.db"


def _resolve_db_path(cli_override: str | None) -> Path:
    if cli_override:
        return Path(cli_override)
    env = os.environ.get(DB_PATH_ENV)
    if env:
        return Path(env)
    return _DEFAULT_DB_PATH


def _connect(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        print(f"ERROR: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA query_only = ON")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
    )


def _list_correlation_ids(conn: sqlite3.Connection, limit: int) -> None:
    has_bce = _table_exists(conn, "business_canonical_events")
    has_ace = _table_exists(conn, "ai_canonical_events")

    if not has_bce and not has_ace:
        print("Neither business_canonical_events nor ai_canonical_events exist yet.")
        return

    parts = []
    if has_bce:
        parts.append(
            "SELECT correlation_id, 'business' AS source FROM business_canonical_events "
            "WHERE correlation_id IS NOT NULL"
        )
    if has_ace:
        parts.append(
            "SELECT correlation_id, 'ai' AS source FROM ai_canonical_events "
            "WHERE correlation_id IS NOT NULL"
        )

    union_sql = " UNION ALL ".join(parts)
    rows = conn.execute(
        f"""
        SELECT correlation_id,
               COUNT(CASE WHEN source='business' THEN 1 END) AS business_count,
               COUNT(CASE WHEN source='ai' THEN 1 END) AS ai_count,
               COUNT(*) AS total_count
        FROM ({union_sql})
        GROUP BY correlation_id
        ORDER BY total_count DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    if not rows:
        print("No correlation_ids found in either canonical table.")
        return

    print(f"{'CORRELATION_ID':<60}  {'BUS':>5}  {'AI':>5}  {'TOTAL':>6}")
    print("-" * 80)
    for row in rows:
        paired = " *" if row["business_count"] > 0 and row["ai_count"] > 0 else ""
        print(
            f"{row['correlation_id']:<60}  {row['business_count']:>5}  "
            f"{row['ai_count']:>5}  {row['total_count']:>6}{paired}"
        )
    print(f"\n  * = paired (present in both canonicals)  |  Showing top {len(rows)} rows")


def _join_correlation_id(
    conn: sqlite3.Connection, correlation_id: str, limit: int, as_json: bool
) -> None:
    has_bce = _table_exists(conn, "business_canonical_events")
    has_ace = _table_exists(conn, "ai_canonical_events")

    result: dict = {"correlation_id": correlation_id, "business": [], "ai": []}

    if has_bce:
        rows = conn.execute(
            """
            SELECT event_id, event_type, event_timestamp, received_at,
                   project_id, milestone_id, work_order_id, task_id,
                   severity, source, schema_version, trace, payload
            FROM business_canonical_events
            WHERE correlation_id = ?
            ORDER BY event_timestamp
            LIMIT ?
            """,
            (correlation_id, limit),
        ).fetchall()
        result["business"] = [dict(r) for r in rows]

    if has_ace:
        rows = conn.execute(
            """
            SELECT event_id, event_type, event_timestamp, received_at,
                   session_id, skill_id, workflow_id, agent_id, hook_id, model_id,
                   severity, source, schema_version, trace, payload
            FROM ai_canonical_events
            WHERE correlation_id = ?
            ORDER BY event_timestamp
            LIMIT ?
            """,
            (correlation_id, limit),
        ).fetchall()
        result["ai"] = [dict(r) for r in rows]

    if as_json:
        print(json.dumps(result, indent=2))
        return

    total = len(result["business"]) + len(result["ai"])
    if total == 0:
        print(f"No rows found for correlation_id={correlation_id!r}")
        return

    print(f"Correlation join: {correlation_id!r}")
    print(f"  business rows : {len(result['business'])}")
    print(f"  ai rows       : {len(result['ai'])}")
    print()

    if result["business"]:
        print("── business_canonical_events ──────────────────────────────────────────")
        for r in result["business"]:
            print(
                f"  [{r['event_timestamp'][:19]}] {r['event_type']:<45} "
                f"proj={r['project_id'] or '-':>36}  "
                f"sev={r['severity']}"
            )

    if result["ai"]:
        print()
        print("── ai_canonical_events ────────────────────────────────────────────────")
        for r in result["ai"]:
            print(
                f"  [{r['event_timestamp'][:19]}] {r['event_type']:<45} "
                f"sess={r['session_id'] or '-':>36}  "
                f"sev={r['severity']}"
            )


def _stats(conn: sqlite3.Connection) -> None:
    has_bce = _table_exists(conn, "business_canonical_events")
    has_ace = _table_exists(conn, "ai_canonical_events")

    print("=== Dual Canonical Table Stats ===")
    for name, exists in [("business_canonical_events", has_bce), ("ai_canonical_events", has_ace)]:
        if not exists:
            print(f"  {name}: <not yet created>")
            continue
        total = conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        paired = conn.execute(
            f"SELECT COUNT(DISTINCT correlation_id) FROM {name} WHERE correlation_id IS NOT NULL"
        ).fetchone()[0]
        sources = conn.execute(
            f"SELECT source, COUNT(*) AS cnt FROM {name} GROUP BY source ORDER BY cnt DESC"
        ).fetchall()
        print(f"  {name}:")
        print(f"    total rows           : {total:,}")
        print(f"    distinct corr_ids    : {paired:,}")
        src_str = ", ".join(f"{r['source']}={r['cnt']}" for r in sources)
        print(f"    by source            : {src_str or '(none)'}")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Correlation join utility for business_canonical_events and ai_canonical_events."
    )
    p.add_argument("--db-path", metavar="PATH", help="Path to studio.db")
    p.add_argument(
        "--list",
        action="store_true",
        help="List distinct correlation_ids (top N by event count)",
    )
    p.add_argument("--correlation-id", metavar="ID", help="Join both tables on this correlation_id")
    p.add_argument(
        "--stats", action="store_true", help="Show row counts and source breakdown for both tables"
    )
    p.add_argument("--limit", type=int, default=20, help="Max rows per table (default: 20)")
    p.add_argument("--json", action="store_true", help="Emit raw JSON output")
    return p


def main() -> int:
    args = _build_parser().parse_args()
    db_path = _resolve_db_path(args.db_path)
    conn = _connect(db_path)

    try:
        if args.stats:
            _stats(conn)
        elif args.list:
            _list_correlation_ids(conn, args.limit)
        elif args.correlation_id:
            _join_correlation_id(conn, args.correlation_id, args.limit, args.json)
        else:
            _stats(conn)
            print()
            _list_correlation_ids(conn, args.limit)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
