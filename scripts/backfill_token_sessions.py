"""Backfill raw_token_usage with correct timestamps and attribution from token-log.md.

The bulk import (migrate_to_db.py) set recorded_at to the import timestamp instead of
the original token-log timestamps, and left project_id NULL. This script re-imports
from token-log.md (the SSOT) with full attribution.

Usage:
    py scripts/backfill_token_sessions.py                  # full re-import
    py scripts/backfill_token_sessions.py --dry-run        # preview only
    py scripts/backfill_token_sessions.py --verbose        # detailed output
    py scripts/backfill_token_sessions.py --sessions       # also backfill raw_sessions
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))
from lib import paths


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
        records.append({
            "timestamp": m.group(1),
            "session_id": m.group(2),
            "model": m.group(3),
            "input_tokens": int(m.group(4).replace(",", "")),
            "output_tokens": int(m.group(5).replace(",", "")),
            "total_tokens": int(m.group(6).replace(",", "")),
        })
    return records


def backfill_token_usage(
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
        return {"error": "No token-log.md data found", "inserted": 0, "deleted": 0}

    conn = sqlite3.connect(str(db_path))
    existing = conn.execute("SELECT COUNT(*) FROM raw_token_usage").fetchone()[0]

    if dry_run:
        print(f"DRY RUN: would delete {existing} rows, insert {len(records)} from token-log.md")
        conn.close()
        return {"deleted": existing, "inserted": len(records), "dry_run": True}

    conn.execute("DELETE FROM raw_token_usage")

    for r in records:
        conn.execute(
            """INSERT INTO raw_token_usage
               (session_id, project_id, skill_name, input_tokens,
                output_tokens, model, recorded_at)
               VALUES (?, ?, 'session', ?, ?, ?, ?)""",
            (r["session_id"], project_id, r["input_tokens"],
             r["output_tokens"], r["model"], r["timestamp"]),
        )
        if verbose:
            print(f"  + {r['timestamp'][:19]} | {r['session_id'][:8]}... | {r['model']} | {r['input_tokens']:,}+{r['output_tokens']:,}")

    conn.commit()
    new_count = conn.execute("SELECT COUNT(*) FROM raw_token_usage").fetchone()[0]
    with_session = conn.execute(
        "SELECT COUNT(*) FROM raw_token_usage WHERE session_id IS NOT NULL"
    ).fetchone()[0]
    conn.close()

    return {
        "deleted": existing,
        "inserted": len(records),
        "total": new_count,
        "with_session_id": with_session,
    }


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

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    updated = 0
    inserted = 0

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
                print(f"  {sid[:8]}... | {start_ts[:10]} | {dur_str} | {total_input + total_output:,} tokens | {primary_model}")
            continue

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
                (start_ts, end_ts, duration_s, total_input, total_output, sid),
            )
            updated += 1
        else:
            conn.execute(
                """INSERT INTO raw_sessions
                   (session_id, project_id, started_at, ended_at,
                    duration_s, input_tokens, output_tokens)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (sid, project_id, start_ts, end_ts, duration_s,
                 total_input, total_output),
            )
            inserted += 1

        if verbose:
            dur_str = f"{duration_s / 60:.1f}min" if duration_s else "?"
            action = "UPD" if existing else "NEW"
            print(f"  [{action}] {sid[:8]}... | {start_ts[:10]} | {dur_str} | {total_input + total_output:,} tokens")

    if not dry_run:
        conn.commit()

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
    ap = argparse.ArgumentParser(description="Backfill token sessions from token-log.md")
    ap.add_argument("--db", type=Path, default=None, help="override studio.db path")
    ap.add_argument("--dry-run", action="store_true", help="preview without modifying DB")
    ap.add_argument("--verbose", action="store_true", help="show per-record details")
    ap.add_argument("--sessions", action="store_true", help="also backfill raw_sessions")
    ap.add_argument("--project-id", default="dream-studio", help="project_id for backfilled rows")
    args = ap.parse_args()

    print("=== Backfill token_usage from token-log.md ===")
    result = backfill_token_usage(
        args.db, dry_run=args.dry_run, verbose=args.verbose, project_id=args.project_id,
    )
    for k, v in result.items():
        print(f"  {k}: {v}")

    if args.sessions:
        print("\n=== Backfill raw_sessions from token-log.md ===")
        sess_result = backfill_sessions(
            args.db, dry_run=args.dry_run, verbose=args.verbose, project_id=args.project_id,
        )
        for k, v in sess_result.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
