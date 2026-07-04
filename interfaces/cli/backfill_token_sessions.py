"""Backfill raw_sessions with attribution and duration data from token-log.md.

raw_token_usage (the table this script originally backfilled) was dropped in
migration 138 (WO 468ce225) — superseded by canonical token.consumed events
and the DuckDB aggregate_metrics.db token_usage_records view. Backfilling
raw_sessions from token-log.md (the SSOT for historical per-call token
records) is now this script's sole purpose.

Usage:
    py scripts/backfill_token_sessions.py                  # backfill raw_sessions
    py scripts/backfill_token_sessions.py --dry-run        # preview only
    py scripts/backfill_token_sessions.py --verbose        # detailed output
"""

from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from core.config import paths
from core.event_store import studio_db


def parse_token_log(log_path: Path | None = None) -> list[dict]:
    if log_path is None:
        log_path = paths.meta_dir() / "token-log.md"
    if not log_path.is_file():
        return []

    records = []
    line_re = re.compile(
        r"\|\s*(\d{4}-\d{2}-\d{2}T[^\s|]+)\s*\|"
        r"\s*([0-9a-f-]{36})\s*\|"
        r"\s*([^\s|]+)\s*\|"
        r"\s*([0-9,]+)\s*\|"
        r"\s*([0-9,]+)\s*\|"
        r"\s*([0-9,]+)\s*\|"
    )

    for line in log_path.read_text(encoding="utf-8").splitlines():
        m = line_re.match(line)
        if not m:
            continue
        records.append(
            {
                "timestamp": m.group(1),
                "session_id": m.group(2),
                "model": m.group(3),
                "input_tokens": int(m.group(4).replace(",", "")),
                "output_tokens": int(m.group(5).replace(",", "")),
                "total_tokens": int(m.group(6).replace(",", "")),
            }
        )
    return records


def backfill_sessions(
    db_path: Path | None = None,
    *,
    dry_run: bool = False,
    verbose: bool = False,
    project_id: str = "dream-studio",
) -> dict:
    if db_path is None:
        db_path = paths.state_dir() / "studio.db"

    records = parse_token_log()
    if not records:
        return {"error": "No token-log.md data found", "updated": 0, "inserted": 0}

    by_session: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        by_session[r["session_id"]].append(r)

    updated = 0
    inserted = 0

    # Prepare all session data first
    session_updates = []
    for sid, recs in by_session.items():
        recs.sort(key=lambda x: x["timestamp"])
        first = recs[0]
        last = recs[-1]
        start_ts = first["timestamp"]
        end_ts = last["timestamp"]

        try:
            start_dt = datetime.fromisoformat(start_ts)
            end_dt = datetime.fromisoformat(end_ts)
            duration_s = (end_dt - start_dt).total_seconds()
        except ValueError:
            duration_s = None

        total_input = last["input_tokens"]
        total_output = last["output_tokens"]
        primary_model = max(
            set(r["model"] for r in recs),
            key=lambda m: sum(1 for r in recs if r["model"] == m),
        )

        if dry_run:
            if verbose:
                dur_str = f"{duration_s / 60:.1f}min" if duration_s else "?"
                print(
                    f"  {sid[:8]}... | {start_ts[:10]} | {dur_str} | {total_input + total_output:,} tokens | {primary_model}"
                )
            continue

        session_updates.append(
            {
                "session_id": sid,
                "start_ts": start_ts,
                "end_ts": end_ts,
                "duration_s": duration_s,
                "total_input": total_input,
                "total_output": total_output,
                "primary_model": primary_model,
            }
        )

    # Write operations in transaction
    if not dry_run:
        # reg_projects deleted in migration 084; ensure project exists in business_projects
        studio_db.upsert_project(
            project_id,
            str(paths.project_root()),
            project_name=project_id,
            db_path=db_path,
        )
        with studio_db._db_transaction(db_path) as conn:
            conn.row_factory = sqlite3.Row
            for sess in session_updates:
                sid = sess["session_id"]
                existing = conn.execute(
                    "SELECT session_id FROM raw_sessions WHERE session_id=?", (sid,)
                ).fetchone()

                if existing:
                    conn.execute(
                        """UPDATE raw_sessions SET
                            started_at=COALESCE(?, started_at),
                            ended_at=COALESCE(?, ended_at),
                            duration_s=COALESCE(?, duration_s),
                            input_tokens=COALESCE(?, input_tokens),
                            output_tokens=COALESCE(?, output_tokens)
                           WHERE session_id=?""",
                        (
                            sess["start_ts"],
                            sess["end_ts"],
                            sess["duration_s"],
                            sess["total_input"],
                            sess["total_output"],
                            sid,
                        ),
                    )
                    updated += 1
                else:
                    conn.execute(
                        """INSERT INTO raw_sessions
                           (session_id, project_id, started_at, ended_at,
                            duration_s, input_tokens, output_tokens)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (
                            sid,
                            project_id,
                            sess["start_ts"],
                            sess["end_ts"],
                            sess["duration_s"],
                            sess["total_input"],
                            sess["total_output"],
                        ),
                    )
                    inserted += 1

                if verbose:
                    dur_str = f"{sess['duration_s'] / 60:.1f}min" if sess["duration_s"] else "?"
                    action = "UPD" if existing else "NEW"
                    print(
                        f"  [{action}] {sid[:8]}... | {sess['start_ts'][:10]} | {dur_str} | {sess['total_input'] + sess['total_output']:,} tokens"
                    )

    # Read-only queries to verify results
    conn = studio_db._connect(db_path)
    total_sessions = conn.execute("SELECT COUNT(*) FROM raw_sessions").fetchone()[0]
    with_duration = conn.execute(
        "SELECT COUNT(*) FROM raw_sessions WHERE duration_s IS NOT NULL"
    ).fetchone()[0]
    conn.close()

    return {
        "updated": updated,
        "inserted": inserted,
        "total_sessions": total_sessions,
        "with_duration": with_duration,
        "unique_in_log": len(by_session),
        **({"dry_run": True} if dry_run else {}),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill raw_sessions from token-log.md")
    ap.add_argument("--db", type=Path, default=None, help="override studio.db path")
    ap.add_argument("--dry-run", action="store_true", help="preview without modifying DB")
    ap.add_argument("--verbose", action="store_true", help="show per-record details")
    ap.add_argument("--project-id", default="dream-studio", help="project_id for backfilled rows")
    args = ap.parse_args()

    print("=== Backfill raw_sessions from token-log.md ===")
    result = backfill_sessions(
        args.db,
        dry_run=args.dry_run,
        verbose=args.verbose,
        project_id=args.project_id,
    )
    for k, v in result.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
