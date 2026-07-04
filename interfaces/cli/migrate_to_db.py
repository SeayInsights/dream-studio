#!/usr/bin/env python3
"""One-time migration: ingest existing metadata files into SQLite.

Parses handoff JSON/MD, lessons, sentinels, and skill usage from
file-based storage into the operational tables. Idempotent — safe to
re-run; duplicates are skipped.

Token-log ingest (raw_token_usage) removed — the table was dropped in
migration 138 (WO 468ce225); use backfill_token_sessions.py for
raw_sessions backfill from token-log.md instead.

Usage:
    py scripts/migrate_to_db.py [--verbose] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.config import paths  # noqa: E402
from core.event_store import studio_db  # noqa: E402
from core.event_store.studio_db import (  # noqa: E402
    _connect,
    upsert_project,
    insert_session,
    insert_handoff,
    insert_lesson,
    set_sentinel,
)

_COUNTS: dict[str, int] = {}
_ERRORS: list[str] = []
_VERBOSE = False
_DRY_RUN = False


def _log(msg: str) -> None:
    if _VERBOSE:
        print(f"  {msg}")


def _count(table: str, n: int = 1) -> None:
    _COUNTS[table] = _COUNTS.get(table, 0) + n


def _err(msg: str) -> None:
    _ERRORS.append(msg)
    if _VERBOSE:
        print(f"  ERROR: {msg}")


# ── Handoff JSON files ────────────────────────────────────────────────────


def _session_exists(session_id: str) -> bool:
    try:
        c = _connect(studio_db._db_path())
        r = c.execute("SELECT 1 FROM raw_sessions WHERE session_id=?", (session_id,)).fetchone()
        c.close()
        return r is not None
    except Exception:
        return False


def _ingest_handoff_json(f: Path) -> None:
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        _err(f"handoff JSON parse failed: {f.name} -- {e}")
        return

    project_root = data.get("project_root", "")
    topic = data.get("topic", f.stem.replace("handoff-", ""))
    date_str = data.get("date", "")
    session_id = f"{date_str}-{topic}" if date_str else f"migrated-{f.stem}"
    project_id = Path(project_root).name if project_root else "unknown"

    if _session_exists(session_id):
        _log(f"skip (exists): {f.name}")
        return

    if project_root:
        upsert_project(
            project_id, project_root, project_name=project_id, db_path=studio_db._db_path()
        )
        _count("reg_projects")

    insert_session(
        session_id,
        project_id,
        topic=topic,
        pipeline_phase=data.get("pipeline_phase"),
        db_path=studio_db._db_path(),
    )
    _count("raw_sessions")

    insert_handoff(
        session_id,
        project_id,
        topic,
        plan_path=data.get("plan_path"),
        pipeline_phase=data.get("pipeline_phase"),
        current_task_id=data.get("current_task_id"),
        current_task_name=data.get("current_task_name"),
        tasks_completed=data.get("tasks_completed"),
        tasks_total=data.get("tasks_total"),
        branch=data.get("branch"),
        last_commit=data.get("last_commit"),
        working=data.get("working"),
        broken=data.get("broken"),
        pending_decisions=data.get("pending_decisions"),
        active_files=data.get("active_files"),
        next_action=data.get("next_action"),
        lessons_json=data.get("lessons_this_session"),
        gotchas_hit=data.get("gotchas_hit"),
        approaches_json=data.get("approaches_taken"),
        db_path=studio_db._db_path(),
    )
    _count("raw_handoffs")
    _log(f"handoff: {f.name} -> session={session_id}")


# ── Lesson files ──────────────────────────────────────────────────────────


def _parse_yaml_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fm_text = text[3:end].strip()
    body = text[end + 3 :].strip()
    fm: dict = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip()
    return fm, body


def _ingest_lesson(f: Path) -> None:
    try:
        text = f.read_text(encoding="utf-8")
    except OSError as e:
        _err(f"lesson read failed: {f.name} — {e}")
        return

    fm, body = _parse_yaml_frontmatter(text)
    lesson_id = f.stem
    source = fm.get("source", "file-migration")
    confidence = fm.get("confidence", "medium")
    title_match = re.search(r"^##\s+(.+)", body, re.MULTILINE)
    title = title_match.group(1) if title_match else f.stem

    what_happened = ""
    lesson_text = ""
    for section in re.split(r"^## ", body, flags=re.MULTILINE):
        lower = section.lower()
        if lower.startswith("what happened"):
            what_happened = section.split("\n", 1)[1].strip() if "\n" in section else ""
        elif lower.startswith("lesson"):
            lesson_text = section.split("\n", 1)[1].strip() if "\n" in section else ""

    insert_lesson(
        lesson_id,
        source,
        title,
        what_happened=what_happened or None,
        lesson=lesson_text or None,
        confidence=confidence,
        db_path=studio_db._db_path(),
    )
    _count("raw_lessons")
    _log(f"lesson: {f.name}")


# ── Sentinel files ────────────────────────────────────────────────────────


def _ingest_sentinels(state_dir: Path) -> None:
    patterns = [
        ("handoff-done-*.json", "handoff-done"),
        ("harden-nudge-*.json", "harden-nudge"),
        ("security-suggest-*.json", "security-suggest"),
    ]
    for glob_pat, sentinel_type in patterns:
        for f in state_dir.glob(glob_pat):
            set_sentinel(f.stem, sentinel_type, db_path=studio_db._db_path())
            _count("raw_sentinels")
            _log(f"sentinel: {f.name}")


# ── Main ──────────────────────────────────────────────────────────────────


def main() -> None:
    global _VERBOSE, _DRY_RUN

    ap = argparse.ArgumentParser(description="Migrate existing files to SQLite")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    _VERBOSE = args.verbose
    _DRY_RUN = args.dry_run

    if _DRY_RUN:
        print("[DRY RUN] No database writes will be made.")
        return

    print("Migrating existing metadata files to SQLite...")

    # Handoff JSON files
    sessions_dir = Path.cwd() / ".sessions"
    if sessions_dir.is_dir():
        for day_dir in sorted(sessions_dir.iterdir()):
            if not day_dir.is_dir():
                continue
            for f in sorted(day_dir.glob("handoff-*.json")):
                _ingest_handoff_json(f)

    # Lesson files
    for lesson_dir in [
        paths.meta_dir() / "lessons",
        paths.meta_dir() / "draft-lessons",
    ]:
        if lesson_dir.is_dir():
            for f in sorted(lesson_dir.glob("*.md")):
                _ingest_lesson(f)

    # Sentinel files
    state_dir = paths.state_dir()
    if state_dir.is_dir():
        _ingest_sentinels(state_dir)

    # Token log ingest (_ingest_token_log / raw_token_usage) removed:
    # raw_token_usage dropped in migration 138 (WO 468ce225).

    # raw_specs / raw_tasks were dropped in migration 128; _ingest_specs removed.

    # Report
    print(f"\n{'Table':<25} {'Rows':>8}")
    print("-" * 35)
    for table, count in sorted(_COUNTS.items()):
        print(f"{table:<25} {count:>8}")
    print(f"\nTotal rows: {sum(_COUNTS.values())}")

    if _ERRORS:
        print(f"\n{len(_ERRORS)} errors:")
        for e in _ERRORS:
            print(f"  - {e}")
    else:
        print("\nNo errors.")


if __name__ == "__main__":
    main()
