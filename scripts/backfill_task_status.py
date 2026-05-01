"""Backfill task completion statuses from handoff data.

Handoffs record tasks_completed counts. This script marks the corresponding
tasks in raw_tasks as 'completed' based on that data.

Usage:
    py scripts/backfill_task_status.py                # apply fixes
    py scripts/backfill_task_status.py --dry-run      # preview only
    py scripts/backfill_task_status.py --verbose       # detailed output
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from lib import paths


def backfill_task_status(
    db_path: Path | None = None,
    *,
    dry_run: bool = False,
    verbose: bool = False,
) -> dict:
    if db_path is None:
        db_path = paths.state_dir() / "studio.db"

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    handoffs = conn.execute(
        """SELECT h.project_id, h.topic, h.tasks_completed, h.tasks_total,
                  h.session_id, h.created_at
           FROM raw_handoffs h
           WHERE h.tasks_completed > 0
           ORDER BY h.created_at"""
    ).fetchall()

    if not handoffs:
        conn.close()
        return {"handoffs_with_tasks": 0, "tasks_marked": 0}

    specs = conn.execute("SELECT * FROM raw_specs").fetchall()
    spec_map = {s["spec_id"]: dict(s) for s in specs}

    total_marked = 0
    specs_updated = 0

    for h in handoffs:
        topic = h["topic"]
        completed = h["tasks_completed"]

        matching_spec = None
        for sid, spec in spec_map.items():
            if topic and (topic in sid or (spec.get("title") and topic in spec["title"])):
                matching_spec = sid
                break

        if not matching_spec:
            if verbose:
                print(f"  SKIP handoff '{topic}' — no matching spec found")
            continue

        tasks = conn.execute(
            "SELECT task_id, status FROM raw_tasks WHERE spec_id=? ORDER BY task_id",
            (matching_spec,),
        ).fetchall()

        if not tasks:
            if verbose:
                print(f"  SKIP spec '{matching_spec}' — no tasks in raw_tasks")
            continue

        planned = [t for t in tasks if t["status"] == "planned"]
        to_mark = min(completed, len(planned))

        if to_mark == 0:
            if verbose:
                already = sum(1 for t in tasks if t["status"] == "completed")
                print(f"  SKIP spec '{matching_spec}' — {already} already completed, {len(planned)} planned")
            continue

        if verbose:
            print(f"  MARK {to_mark}/{len(tasks)} tasks as completed for spec '{matching_spec}' (handoff: {topic})")

        if not dry_run:
            for t in planned[:to_mark]:
                conn.execute(
                    "UPDATE raw_tasks SET status='completed' WHERE task_id=? AND spec_id=?",
                    (t["task_id"], matching_spec),
                )
                total_marked += 1

            conn.execute(
                "UPDATE raw_specs SET tasks_done=? WHERE spec_id=?",
                (sum(1 for t in tasks if t["status"] == "completed") + to_mark, matching_spec),
            )
        else:
            total_marked += to_mark

        specs_updated += 1

    if not dry_run:
        conn.commit()

    final_stats = {}
    for row in conn.execute("SELECT status, COUNT(*) as cnt FROM raw_tasks GROUP BY status"):
        final_stats[row["status"]] = row["cnt"]

    conn.close()

    return {
        "handoffs_with_tasks": len(handoffs),
        "specs_matched": specs_updated,
        "tasks_marked_completed": total_marked,
        "final_status_counts": final_stats,
        **({"dry_run": True} if dry_run else {}),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill task statuses from handoff data")
    ap.add_argument("--db", type=Path, default=None, help="override studio.db path")
    ap.add_argument("--dry-run", action="store_true", help="preview without modifying DB")
    ap.add_argument("--verbose", action="store_true", help="show per-handoff details")
    args = ap.parse_args()

    print("=== Backfill task statuses from handoff data ===")
    result = backfill_task_status(args.db, dry_run=args.dry_run, verbose=args.verbose)
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
