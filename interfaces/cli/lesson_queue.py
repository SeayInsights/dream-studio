"""lesson_queue.py — CLI for draft lesson triage (DB-backed).

Lessons live in the raw_lessons table of studio.db (operator decision 2026-06-14).
File-based lesson .md writing has been removed — lessons are inserted via insert_lesson().

Commands:
  list [--pending|--promoted|--rejected]  List lessons filtered by status.
  promote <lesson_id> --target <skill>    Mark lesson PROMOTED with target.
  reject <lesson_id>                      Mark lesson REJECTED.
  stats                                   Show count summary.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.config import paths
from core.event_store.studio_db import (
    get_lessons,
    get_pending_lessons,
    promote_lesson,
    reject_lesson,
)


def _db_path() -> Path:
    return paths.state_dir() / "studio.db"


# ── Table formatting ───────────────────────────────────────────────────────────


def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def _print_table(rows: list[dict]) -> None:
    if not rows:
        print("(no lessons found)")
        return

    col_widths = {
        "lesson_id": max(12, max(len(r.get("lesson_id", "") or "") for r in rows)),
        "source": 22,
        "title": 36,
        "status": 9,
        "created_at": 19,
    }

    header = (
        f"{'Lesson ID':<{col_widths['lesson_id']}}  "
        f"{'Source':<{col_widths['source']}}  "
        f"{'Title':<{col_widths['title']}}  "
        f"{'Status':<{col_widths['status']}}  "
        f"{'Created':<{col_widths['created_at']}}"
    )
    sep = "  ".join("-" * w for w in col_widths.values())

    print(header)
    print(sep)
    for row in rows:
        line = (
            f"{_truncate(row.get('lesson_id', '') or '', col_widths['lesson_id']):<{col_widths['lesson_id']}}  "
            f"{_truncate(row.get('source', '') or '', col_widths['source']):<{col_widths['source']}}  "
            f"{_truncate(row.get('title', '') or '', col_widths['title']):<{col_widths['title']}}  "
            f"{_truncate(row.get('status', '') or '', col_widths['status']):<{col_widths['status']}}  "
            f"{_truncate((row.get('created_at', '') or '')[:19], col_widths['created_at']):<{col_widths['created_at']}}"
        )
        print(line)


# ── Sub-commands ───────────────────────────────────────────────────────────────


def cmd_list(args: argparse.Namespace) -> None:
    if args.promoted:
        status = "promoted"
        label = "promoted"
    elif args.rejected:
        status = "rejected"
        label = "rejected"
    else:
        status = "draft"
        label = "pending"

    all_rows = get_lessons(db_path=_db_path())
    filtered = [r for r in all_rows if r.get("status") == status]
    print(f"Draft lessons — {label} ({len(filtered)} of {len(all_rows)} total)\n")
    _print_table(filtered)


def cmd_promote(args: argparse.Namespace) -> None:
    lesson_id = args.lesson_id
    ok = promote_lesson(lesson_id, args.target, db_path=_db_path())
    if ok:
        print(f"Promoted: {lesson_id}")
        print(f"  Target : {args.target}")
    else:
        print(f"Error: could not promote {lesson_id!r} (not found or DB error)", file=sys.stderr)
        sys.exit(1)


def cmd_reject(args: argparse.Namespace) -> None:
    lesson_id = args.lesson_id
    ok = reject_lesson(lesson_id, db_path=_db_path())
    if ok:
        print(f"Rejected: {lesson_id}")
    else:
        print(f"Error: could not reject {lesson_id!r} (not found or DB error)", file=sys.stderr)
        sys.exit(1)


def cmd_stats(args: argparse.Namespace) -> None:
    all_rows = get_lessons(db_path=_db_path())
    total = len(all_rows)
    pending = sum(1 for r in all_rows if r.get("status") == "draft")
    promoted = sum(1 for r in all_rows if r.get("status") == "promoted")
    rejected = sum(1 for r in all_rows if r.get("status") == "rejected")
    other = total - pending - promoted - rejected

    print("Draft lesson stats (studio.db raw_lessons)")
    print(f"  Total    : {total}")
    print(f"  Pending  : {pending}")
    print(f"  Promoted : {promoted}")
    print(f"  Rejected : {rejected}")
    if other:
        print(f"  Other    : {other}")


# ── Entry point ────────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lesson_queue",
        description="Triage dream-studio draft lessons (DB-backed).",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # list
    p_list = sub.add_parser("list", help="List lessons (default: --pending).")
    filter_group = p_list.add_mutually_exclusive_group()
    filter_group.add_argument("--pending", action="store_true", default=False)
    filter_group.add_argument("--promoted", action="store_true", default=False)
    filter_group.add_argument("--rejected", action="store_true", default=False)
    p_list.set_defaults(func=cmd_list)

    # promote
    p_promote = sub.add_parser("promote", help="Promote a lesson.")
    p_promote.add_argument("lesson_id", help="Lesson ID from the DB.")
    p_promote.add_argument("--target", required=True, metavar="SKILL", help="Promotion target.")
    p_promote.set_defaults(func=cmd_promote)

    # reject
    p_reject = sub.add_parser("reject", help="Reject a draft lesson.")
    p_reject.add_argument("lesson_id", help="Lesson ID from the DB.")
    p_reject.set_defaults(func=cmd_reject)

    # stats
    p_stats = sub.add_parser("stats", help="Show lesson count summary.")
    p_stats.set_defaults(func=cmd_stats)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
