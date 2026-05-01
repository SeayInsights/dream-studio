#!/usr/bin/env python3
"""One-time migration: ingest existing metadata files into SQLite.

Parses handoff JSON/MD, lessons, sentinels, token logs, skill usage,
and specs/tasks from file-based storage into the operational tables.
Idempotent — safe to re-run; duplicates are skipped.

Usage:
    py scripts/migrate_to_db.py [--verbose] [--dry-run]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "hooks"))

from lib import paths  # noqa: E402
from lib.studio_db import (  # noqa: E402
    _connect,
    upsert_project,
    insert_session,
    insert_handoff,
    insert_lesson,
    set_sentinel,
    has_sentinel,
    insert_token_usage,
    upsert_spec,
    upsert_task,
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
        c = _connect()
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
        upsert_project(project_id, project_root, project_name=project_id)
        _count("reg_projects")

    insert_session(session_id, project_id, topic=topic,
                   pipeline_phase=data.get("pipeline_phase"))
    _count("raw_sessions")

    insert_handoff(
        session_id, project_id, topic,
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
    body = text[end + 3:].strip()
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

    insert_lesson(lesson_id, source, title,
                  what_happened=what_happened or None,
                  lesson=lesson_text or None,
                  confidence=confidence)
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
            set_sentinel(f.stem, sentinel_type)
            _count("raw_sentinels")
            _log(f"sentinel: {f.name}")


# ── Token log ─────────────────────────────────────────────────────────────

def _ingest_token_log(f: Path) -> None:
    if has_sentinel("migration-token-log"):
        _log("skip token log (already migrated)")
        return
    try:
        lines = f.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        _err(f"token log read failed: {e}")
        return

    for line in lines:
        if not line.startswith("|") or line.startswith("| Timestamp") or line.startswith("|---"):
            continue
        parts = [p.strip() for p in line.split("|")]
        parts = [p for p in parts if p]
        if len(parts) < 5:
            continue
        try:
            _ts = parts[0]  # noqa: F841 — parsed but not stored (recorded_at set by insert)
            session_id = parts[1] if len(parts) > 1 else None
            model = parts[2] if len(parts) > 2 else None
            input_tokens = int(parts[3]) if len(parts) > 3 else 0
            output_tokens = int(parts[4]) if len(parts) > 4 else 0
            insert_token_usage(
                session_id=session_id,
                skill_name="session",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model,
            )
            _count("raw_token_usage")
        except (ValueError, IndexError):
            _err(f"token log parse failed: {line[:80]}")

    set_sentinel("migration-token-log", "migration")


# ── Spec/task files ───────────────────────────────────────────────────────

def _ingest_specs(specs_dir: Path) -> None:
    if not specs_dir.is_dir():
        return
    for spec_dir in specs_dir.iterdir():
        if not spec_dir.is_dir():
            continue
        spec_id = spec_dir.name
        spec_file = spec_dir / "spec.md"
        tasks_file = spec_dir / "tasks.md"

        spec_content = None
        title = spec_id.replace("-", " ").title()
        if spec_file.is_file():
            spec_content = spec_file.read_text(encoding="utf-8")
            title_match = re.search(r"^#\s+(?:Spec:\s*)?(.+)", spec_content, re.MULTILINE)
            if title_match:
                title = title_match.group(1).strip()

        plan_content = None
        task_count = 0
        if tasks_file.is_file():
            plan_content = tasks_file.read_text(encoding="utf-8")
            task_count = len(re.findall(r"^- \[ \] (T\d+)", plan_content, re.MULTILINE))

        upsert_spec(spec_id, "dream-studio", title,
                    task_count=task_count or None,
                    spec_content=spec_content,
                    plan_content=plan_content)
        _count("raw_specs")
        _log(f"spec: {spec_id} ({task_count} tasks)")

        if tasks_file.is_file() and plan_content:
            for m in re.finditer(
                r"^- \[ \] (T\d+)\s+\[est:([\d.]+)h\]\s+(.+?)$",
                plan_content, re.MULTILINE,
            ):
                task_id, est, task_title = m.group(1), float(m.group(2)), m.group(3)
                upsert_task(task_id, spec_id, "dream-studio", task_title,
                            estimated_hours=est)
                _count("raw_tasks")


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

    # Token log
    token_log = paths.meta_dir() / "token-log.md"
    if token_log.is_file():
        _ingest_token_log(token_log)

    # Spec/task files
    specs_dir = Path.cwd() / ".planning" / "specs"
    _ingest_specs(specs_dir)

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
