"""Phase 18.1.3 — Backfill correlation IDs for historical events.

Walks raw_claude_code_events, business_canonical_events, and
ai_canonical_events. For each row:

  - If correlation_id is present and already valid → kept as-is
  - If correlation_id is present but malformed → normalized (best-effort)
  - If correlation_id is missing → reconstructed from available ID columns
  - If reconstruction produces nothing → marked unfixable

Reports per-table statistics. Safe to re-run (UPDATE only changes rows where
normalization produces a different value; skips rows where result equals the
current value).

Usage::

    py -m scripts.backfill_correlation_ids [--db-path PATH] [--dry-run] [--verbose]

Or directly::

    py scripts/backfill_correlation_ids.py [--db-path PATH] [--dry-run] [--verbose]
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

from core.correlation.composer import compose, normalize_legacy, validate  # noqa: E402

# ---------------------------------------------------------------------------
# Per-table column definitions
# ---------------------------------------------------------------------------

_TABLE_CONFIGS: dict[str, dict] = {
    "raw_claude_code_events": {
        "pk": "event_id",
        "id_cols": {
            "session": "session_id",
            "workflow": "workflow_id",
            "skill": "skill_id",
            "agent": "agent_id",
            "hook": "hook_id",
            "tool": "tool_id",
        },
    },
    "business_canonical_events": {
        "pk": "event_id",
        # business canonical doesn't have individual ID columns for all types;
        # try to reconstruct from the correlation_id-adjacent JSON fields.
        "id_cols": {
            "session": None,  # no dedicated column
            "workflow": None,
            "skill": None,
            "agent": None,
            "hook": None,
            "tool": None,
        },
        "trace_col": "trace",
    },
    "ai_canonical_events": {
        "pk": "event_id",
        "id_cols": {
            "session": "session_id",
            "workflow": "workflow_id",
            "skill": "skill_id",
            "agent": "agent_id",
            "hook": "hook_id",
            "tool": None,  # no tool column in ai canonical (tool detail lives in raw)
        },
    },
}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _extract_ids_from_trace(trace_json: str | None) -> dict[str, str | None]:
    """Try to extract entity IDs from a JSON trace blob."""
    if not trace_json:
        return {}
    try:
        trace = json.loads(trace_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(trace, dict):
        return {}
    return {
        "session": trace.get("session_id"),
        "workflow": trace.get("workflow_id") or trace.get("stream_id"),
        "skill": trace.get("skill_id") or trace.get("skill_specifier"),
        "agent": trace.get("agent_id"),
        "hook": trace.get("hook_id"),
        "tool": trace.get("tool_id"),
    }


def _backfill_table(
    conn: sqlite3.Connection,
    table: str,
    config: dict,
    dry_run: bool,
    verbose: bool,
) -> dict[str, int]:
    stats = {
        "total": 0,
        "kept": 0,
        "normalized": 0,
        "reconstructed": 0,
        "unfixable": 0,
        "skipped_no_table": 0,
    }

    if not _table_exists(conn, table):
        print(f"  [SKIP] Table {table!r} does not exist in this database.")
        stats["skipped_no_table"] = 1
        return stats

    rows = conn.execute(
        f"SELECT {config['pk']}, correlation_id FROM {table}"  # noqa: S608
    ).fetchall()
    stats["total"] = len(rows)

    id_cols = config.get("id_cols", {})
    trace_col = config.get("trace_col")

    for pk_value, current_cid in rows:
        # Determine new correlation_id
        if current_cid is not None:
            is_valid, _ = validate(current_cid)
            if is_valid:
                stats["kept"] += 1
                if verbose:
                    print(f"    kept   {pk_value[:16]}… {current_cid[:60]}")
                continue

            normalized, action = normalize_legacy(current_cid)
            if action == "normalized" and normalized != current_cid:
                new_cid = normalized
                action_label = "normalized"
            else:
                # Still unfixable via normalization alone; try reconstruction
                new_cid = None
                action_label = None
        else:
            new_cid = None
            action_label = None

        if new_cid is None:
            # Attempt reconstruction from dedicated ID columns or trace JSON
            parts: dict[str, str | None] = {}

            # Build parts from dedicated columns
            for entity_type, col_name in id_cols.items():
                if col_name:
                    val = conn.execute(
                        f"SELECT {col_name} FROM {table} WHERE {config['pk']}=?",  # noqa: S608
                        (pk_value,),
                    ).fetchone()
                    parts[entity_type] = val[0] if val else None

            # Supplement from trace JSON if available
            if trace_col:
                trace_row = conn.execute(
                    f"SELECT {trace_col} FROM {table} WHERE {config['pk']}=?",  # noqa: S608
                    (pk_value,),
                ).fetchone()
                trace_parts = _extract_ids_from_trace(trace_row[0] if trace_row else None)
                for k, v in trace_parts.items():
                    if v and not parts.get(k):
                        parts[k] = v

            reconstructed = compose(parts)
            if reconstructed:
                new_cid = reconstructed
                action_label = "reconstructed"
            else:
                action_label = "unfixable"

        if action_label == "kept":
            stats["kept"] += 1
        elif action_label == "normalized":
            stats["normalized"] += 1
            if not dry_run:
                conn.execute(
                    f"UPDATE {table} SET correlation_id=? WHERE {config['pk']}=?",  # noqa: S608
                    (new_cid, pk_value),
                )
            if verbose:
                print(f"    normalized  {pk_value[:16]}… → {new_cid[:60]}")
        elif action_label == "reconstructed":
            stats["reconstructed"] += 1
            if not dry_run:
                conn.execute(
                    f"UPDATE {table} SET correlation_id=? WHERE {config['pk']}=?",  # noqa: S608
                    (new_cid, pk_value),
                )
            if verbose:
                print(f"    reconstructed {pk_value[:16]}… → {new_cid[:60]}")
        else:
            stats["unfixable"] += 1
            if verbose:
                print(f"    unfixable {pk_value[:16]}… (was: {str(current_cid)[:40]})")

    if not dry_run:
        conn.commit()

    return stats


def run_backfill(db_path: Path, dry_run: bool, verbose: bool) -> dict[str, dict]:
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.execute("PRAGMA journal_mode = WAL")

    all_stats: dict[str, dict] = {}

    for table, config in _TABLE_CONFIGS.items():
        print(f"\nProcessing {table}…")
        stats = _backfill_table(conn, table, config, dry_run, verbose)
        all_stats[table] = stats

    conn.close()
    return all_stats


def _print_summary(all_stats: dict[str, dict], dry_run: bool) -> None:
    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{'='*60}")
    print(f"{mode}Backfill correlation IDs — Summary")
    print(f"{'='*60}")
    totals = {"total": 0, "kept": 0, "normalized": 0, "reconstructed": 0, "unfixable": 0}
    for table, stats in all_stats.items():
        if stats.get("skipped_no_table"):
            print(f"  {table}: SKIPPED (table not found)")
            continue
        print(
            f"  {table}:\n"
            f"    total={stats['total']}  kept={stats['kept']}  "
            f"normalized={stats['normalized']}  reconstructed={stats['reconstructed']}  "
            f"unfixable={stats['unfixable']}"
        )
        for k in totals:
            totals[k] += stats.get(k, 0)

    print("\n  TOTALS:")
    print(
        f"    total={totals['total']}  kept={totals['kept']}  "
        f"normalized={totals['normalized']}  reconstructed={totals['reconstructed']}  "
        f"unfixable={totals['unfixable']}"
    )
    if dry_run:
        print("\n  NOTE: Dry-run mode — no changes written to database.")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backfill correlation IDs for historical Dream Studio events."
    )
    parser.add_argument("--db-path", type=Path, help="Path to studio.db")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing to DB.",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-row actions.")
    args = parser.parse_args(argv)

    if args.db_path:
        db_path = args.db_path
    else:
        from core.config.database import _default_db_path

        db_path = _default_db_path()

    if not db_path.exists():
        print(f"ERROR: Database not found at {db_path}", file=sys.stderr)
        return 1

    print(f"Database: {db_path}")
    if args.dry_run:
        print("Mode: DRY RUN (no writes)")
    else:
        print("Mode: LIVE (will update malformed/missing correlation_ids)")

    all_stats = run_backfill(db_path, args.dry_run, args.verbose)
    _print_summary(all_stats, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
