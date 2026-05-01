"""lesson_queue.py — CLI for draft lesson triage.

Commands:
  list [--pending|--promoted|--rejected]  List draft lessons filtered by status.
  promote <file> --target <skill/gotchas.yml>  Mark a lesson PROMOTED.
  reject <file>                           Mark a lesson REJECTED.
  stats                                   Show summary counts.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

LESSONS_DIR = Path.home() / ".dream-studio" / "meta" / "draft-lessons"

# ── Parsing helpers ────────────────────────────────────────────────────────────

def _parse_lesson(path: Path) -> dict:
    """Parse a draft-lesson .md file into a metadata dict."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"file": path.name, "error": str(exc)}

    title = ""
    title_match = re.search(r"^#\s+Draft Lesson:\s*(.+)", text, re.MULTILINE)
    if title_match:
        title = title_match.group(1).strip()

    date = ""
    date_match = re.search(r"^Date:\s*(\S+)", text, re.MULTILINE)
    if date_match:
        date = date_match.group(1).strip()

    status = "DRAFT"
    status_match = re.search(r"^Status:\s*(\S+)", text, re.MULTILINE)
    if status_match:
        status = status_match.group(1).strip().upper()

    applies_to = ""
    applies_match = re.search(r"##\s*Applies to\s*\n([^\n#]+)", text, re.IGNORECASE)
    if applies_match:
        applies_to = applies_match.group(1).strip()

    promoted_target = ""
    target_match = re.search(r"^Promoted-to:\s*(.+)", text, re.MULTILINE)
    if target_match:
        promoted_target = target_match.group(1).strip()

    return {
        "file": path.name,
        "path": path,
        "title": title,
        "date": date,
        "status": status,
        "applies_to": applies_to,
        "promoted_target": promoted_target,
        "error": None,
    }


def _load_lessons() -> list[dict]:
    """Load all .md lessons from LESSONS_DIR."""
    if not LESSONS_DIR.is_dir():
        return []
    return [_parse_lesson(p) for p in sorted(LESSONS_DIR.glob("*.md"))]


# ── Table formatting ───────────────────────────────────────────────────────────

def _truncate(value: str, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return value[: max_len - 1] + "…"


def _print_table(lessons: list[dict]) -> None:
    if not lessons:
        print("(no lessons found)")
        return

    col_widths = {
        "file": max(8, max(len(r["file"]) for r in lessons)),
        "date": 10,
        "title": 36,
        "status": 9,
        "applies_to": 20,
    }

    header = (
        f"{'Filename':<{col_widths['file']}}  "
        f"{'Date':<{col_widths['date']}}  "
        f"{'Title':<{col_widths['title']}}  "
        f"{'Status':<{col_widths['status']}}  "
        f"{'Applies to':<{col_widths['applies_to']}}"
    )
    sep = "  ".join("-" * w for w in col_widths.values())

    print(header)
    print(sep)
    for row in lessons:
        line = (
            f"{_truncate(row['file'], col_widths['file']):<{col_widths['file']}}  "
            f"{_truncate(row['date'], col_widths['date']):<{col_widths['date']}}  "
            f"{_truncate(row['title'], col_widths['title']):<{col_widths['title']}}  "
            f"{_truncate(row['status'], col_widths['status']):<{col_widths['status']}}  "
            f"{_truncate(row['applies_to'], col_widths['applies_to']):<{col_widths['applies_to']}}"
        )
        print(line)


# ── Status mutation helpers ────────────────────────────────────────────────────

def _resolve_lesson_path(filename: str) -> Path:
    """Resolve a filename to its full path in LESSONS_DIR."""
    candidate = LESSONS_DIR / filename
    if not candidate.exists():
        # Try adding .md if not present
        if not filename.endswith(".md"):
            candidate = LESSONS_DIR / (filename + ".md")
    if not candidate.exists():
        print(f"Error: lesson file not found: {filename}", file=sys.stderr)
        sys.exit(1)
    return candidate


def _update_status(path: Path, new_status: str, extra_line: str | None = None) -> None:
    """Rewrite the Status: line in the lesson file."""
    text = path.read_text(encoding="utf-8")
    if re.search(r"^Status:\s*\S+", text, re.MULTILINE):
        text = re.sub(
            r"^Status:\s*\S+",
            f"Status: {new_status}",
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        # Append after Date line if no Status line found
        text = re.sub(
            r"(^Date:\s*\S+)",
            rf"\1\nStatus: {new_status}",
            text,
            count=1,
            flags=re.MULTILINE,
        )

    if extra_line:
        # Insert or replace the extra_line key after Status line
        key = extra_line.split(":")[0]
        if re.search(rf"^{re.escape(key)}:", text, re.MULTILINE):
            text = re.sub(
                rf"^{re.escape(key)}:.*",
                extra_line,
                text,
                count=1,
                flags=re.MULTILINE,
            )
        else:
            text = re.sub(
                r"(^Status:\s*\S+)",
                rf"\1\n{extra_line}",
                text,
                count=1,
                flags=re.MULTILINE,
            )

    path.write_text(text, encoding="utf-8")


# ── Sub-commands ───────────────────────────────────────────────────────────────

def cmd_list(args: argparse.Namespace) -> None:
    lessons = _load_lessons()

    if args.promoted:
        filter_status = "PROMOTED"
    elif args.rejected:
        filter_status = "REJECTED"
    else:
        filter_status = "DRAFT"  # --pending is default

    filtered = [r for r in lessons if r["status"] == filter_status]
    label = filter_status.lower()
    print(f"Draft lessons — {label} ({len(filtered)} of {len(lessons)} total)\n")
    _print_table(filtered)


def cmd_promote(args: argparse.Namespace) -> None:
    path = _resolve_lesson_path(args.file)
    lesson = _parse_lesson(path)

    if lesson["status"] == "PROMOTED":
        print(f"Already PROMOTED: {args.file}")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    _update_status(path, "PROMOTED", f"Promoted-to: {args.target}")
    print(f"Promoted: {args.file}")
    print(f"  Target : {args.target}")
    print(f"  Date   : {today}")


def cmd_reject(args: argparse.Namespace) -> None:
    path = _resolve_lesson_path(args.file)
    lesson = _parse_lesson(path)

    if lesson["status"] == "REJECTED":
        print(f"Already REJECTED: {args.file}")
        return

    _update_status(path, "REJECTED")
    print(f"Rejected: {args.file}")


def cmd_stats(args: argparse.Namespace) -> None:
    lessons = _load_lessons()
    total = len(lessons)
    pending = sum(1 for r in lessons if r["status"] == "DRAFT")
    promoted = sum(1 for r in lessons if r["status"] == "PROMOTED")
    rejected = sum(1 for r in lessons if r["status"] == "REJECTED")
    other = total - pending - promoted - rejected

    print(f"Draft lesson stats ({LESSONS_DIR})")
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
        description="Triage dream-studio draft lessons.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")
    sub.required = True

    # list
    p_list = sub.add_parser("list", help="List draft lessons (default: --pending).")
    filter_group = p_list.add_mutually_exclusive_group()
    filter_group.add_argument(
        "--pending",
        action="store_true",
        default=False,
        help="Show only DRAFT/pending lessons (default).",
    )
    filter_group.add_argument(
        "--promoted",
        action="store_true",
        default=False,
        help="Show only PROMOTED lessons.",
    )
    filter_group.add_argument(
        "--rejected",
        action="store_true",
        default=False,
        help="Show only REJECTED lessons.",
    )
    p_list.set_defaults(func=cmd_list)

    # promote
    p_promote = sub.add_parser("promote", help="Promote a lesson to a skill/gotchas file.")
    p_promote.add_argument("file", help="Lesson filename (with or without .md).")
    p_promote.add_argument(
        "--target",
        required=True,
        metavar="SKILL/GOTCHAS.YML",
        help="The skill name or gotchas.yml path this lesson was promoted into.",
    )
    p_promote.set_defaults(func=cmd_promote)

    # reject
    p_reject = sub.add_parser("reject", help="Reject a draft lesson.")
    p_reject.add_argument("file", help="Lesson filename (with or without .md).")
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
