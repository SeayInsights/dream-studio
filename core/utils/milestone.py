"""Milestone management logic for on-milestone-start and on-milestone-end hooks."""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from .time import utcnow

MARKER_FILENAME = "milestone-active.txt"
DIFFICULTY_THRESHOLD_MINUTES = 30

DCL_PATTERN = re.compile(
    r"^(build feature:|build page:|build api:|build component:|build schema:|"
    r"build report:|build app:|build flow:|new game:|3d new game:|3d scene:|"
    r"launch project:|deploy:|python package:|python migrate:|python publish:|"
    r"desktop: build|desktop: phase|desktop: release)",
    re.IGNORECASE,
)


def load_and_clear_marker(state_dir: Path) -> dict | None:
    """Load milestone marker and delete file. Returns None if no marker exists."""
    marker_path = state_dir / MARKER_FILENAME
    if not marker_path.exists():
        return None

    try:
        marker_data = marker_path.read_text(encoding="utf-8")
        marker_path.unlink(missing_ok=True)
        marker = json.loads(marker_data)
        marker["completed_at"] = utcnow().isoformat()
        return marker
    except Exception:
        return {"command": "unknown", "started_at": "unknown", "completed_at": utcnow().isoformat()}


def log_completion(marker: dict, meta_dir: Path) -> None:
    """Append milestone completion to milestone-log.md."""
    log_path = meta_dir / "milestone-log.md"
    command = marker.get("command", "unknown")
    started_at = marker.get("started_at", "unknown")
    completed_at = marker.get("completed_at", "unknown")

    try:
        if not log_path.exists():
            log_path.write_text(
                "# Milestone Log\n\n" "| Completed At | Command | Started At |\n" "|---|---|---|\n",
                encoding="utf-8",
            )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"| {completed_at} | {command[:80]} | {started_at} |\n")
    except Exception as e:
        print(f"[milestone] failed to write log: {e}", flush=True)


def print_checkpoint(marker: dict) -> None:
    """Print checkpoint reminder message."""
    command = marker.get("command", "unknown")
    print(
        f"\n[dream-studio] Milestone complete: {command[:60]}\n"
        f"  -> Consider: save pattern, capture lessons, commit changes\n",
        flush=True,
    )


def draft_lesson_if_long(marker: dict, meta_dir: Path) -> None:
    """Draft retrospective lesson if milestone elapsed > DIFFICULTY_THRESHOLD_MINUTES."""
    command = marker.get("command", "unknown")
    started_at = marker.get("started_at", "unknown")
    completed_at = marker.get("completed_at", "unknown")

    try:
        start_dt = datetime.fromisoformat(started_at)
        end_dt = datetime.fromisoformat(completed_at)
    except (ValueError, TypeError):
        return

    elapsed_min = (end_dt - start_dt).total_seconds() / 60
    if elapsed_min < DIFFICULTY_THRESHOLD_MINUTES:
        return

    drafts_dir = meta_dir / "draft-lessons"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    date_str = utcnow().strftime("%Y-%m-%d")
    slug = re.sub(r"[^a-z0-9]+", "-", command.lower())[:40].strip("-") or "milestone"
    draft_path = drafts_dir / f"long-milestone-{date_str}-{slug}.md"

    if draft_path.exists():
        return

    draft = (
        f"---\n"
        f"type: draft-lesson\n"
        f"source: on-milestone-end\n"
        f"status: draft\n"
        f"created: {completed_at}\n"
        f"---\n\n"
        f"## Long-Running Milestone Detected\n\n"
        f"**Command:** {command}\n"
        f"**Started:** {started_at}\n"
        f"**Completed:** {completed_at}\n"
        f"**Elapsed:** {elapsed_min:.0f} minutes (threshold: {DIFFICULTY_THRESHOLD_MINUTES} min)\n\n"
        f"## Retrospective Prompts\n\n"
        f"1. Was the scope appropriate for a single milestone?\n"
        f"2. Did the agent hit unexpected complexity or blockers?\n"
        f"3. Should this task have been split into smaller milestones?\n"
        f"4. Was there thrashing (repeated attempts at the same thing)?\n"
        f"5. Any patterns here that apply to future similar tasks?\n\n"
        f"## Director Action\n\n"
        f"- [ ] Add lesson to patterns (scope/splitting guidance)\n"
        f"- [ ] No action needed (task was legitimately complex)\n"
        f"- [ ] Reject (delete this file)\n"
    )
    draft_path.write_text(draft, encoding="utf-8")
    print(
        f"  -> SENSOR: Milestone took {elapsed_min:.0f} min — draft lesson created\n"
        f"     Review: {draft_path}\n",
        flush=True,
    )


def write_marker(state_dir: Path, command: str) -> bool:
    """Write milestone marker file. Returns False if marker already exists."""
    marker_path = state_dir / MARKER_FILENAME
    timestamp = utcnow().isoformat()

    if marker_path.exists():
        return False

    try:
        marker_path.write_text(
            json.dumps({"command": command, "started_at": timestamp}),
            encoding="utf-8",
        )
        return True
    except Exception:
        return False


# === Milestone Start Functions ===


def read_user_message() -> str:
    """Extract user message from env var or stdin payload."""
    env = os.environ.get("CLAUDE_USER_MESSAGE_TEXT", "").strip()
    if env:
        return env
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except Exception:
        return ""
    return str(payload.get("prompt") or payload.get("user_message") or "").strip()


def is_dcl_command(message: str) -> bool:
    """Check if message matches DCL pattern (build/deploy commands)."""
    return bool(DCL_PATTERN.match(message))


def marker_exists(state_dir: Path) -> bool:
    """Check if milestone marker file exists."""
    return (state_dir / MARKER_FILENAME).exists()


def create_marker(command: str, state_dir: Path) -> bool:
    """Create milestone marker file. Returns True if successful."""
    return write_marker(state_dir, command)


def print_already_active(message: str) -> None:
    """Print message when milestone marker already exists."""
    print(
        f"\n[dream-studio] Milestone already active — skipping duplicate for: {message[:60]}",
        flush=True,
    )


def print_workflow_reminder(message: str) -> None:
    """Print Research -> Plan -> Implement workflow reminder."""
    print(f"\n[dream-studio] Milestone started: {message[:60]}", flush=True)
    print(
        "[dream-studio] Research -> Plan -> Implement required for this milestone:\n"
        "  1. RESEARCH  — read relevant docs, standards, prior decisions (<=3 tool calls)\n"
        "  2. PLAN      — present numbered plan (what changes, what tools, token cost)\n"
        "  3. IMPLEMENT — execute approved plan; stop + re-present if scope changes\n"
        "  Skip only for: read-only queries, single-file edits with a clear target.\n",
        flush=True,
    )
