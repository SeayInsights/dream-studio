#!/usr/bin/env python3
"""Hook: on-milestone-end — emit checkpoint and clear the marker at turn end.

Trigger: Stop.
Purpose: If a milestone marker exists, record completion to the milestone log,
print a checkpoint reminder, and clear the marker. If the milestone ran longer
than DIFFICULTY_THRESHOLD_MINUTES, draft a retrospective lesson for review.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))

from lib import paths  # noqa: E402
from lib.time_utils import utcnow  # noqa: E402

MARKER_FILENAME = "milestone-active.txt"
DIFFICULTY_THRESHOLD_MINUTES = 30


def main() -> None:
    marker_path = paths.state_dir() / MARKER_FILENAME
    if not marker_path.exists():
        return  # No milestone was active — silent exit

    try:
        marker_data = marker_path.read_text(encoding="utf-8")
        marker_path.unlink(missing_ok=True)
        marker = json.loads(marker_data)
    except Exception:
        marker = {"command": "unknown", "started_at": "unknown"}

    command = marker.get("command", "unknown")
    started_at = marker.get("started_at", "unknown")
    completed_at = utcnow().isoformat()

    print(
        f"\n[dream-studio] Milestone complete: {command[:60]}\n"
        f"  -> Consider: save pattern, capture lessons, commit changes\n",
        flush=True,
    )

    log_path = paths.meta_dir() / "milestone-log.md"
    try:
        if not log_path.exists():
            log_path.write_text(
                "# Milestone Log\n\n"
                "| Completed At | Command | Started At |\n"
                "|---|---|---|\n",
                encoding="utf-8",
            )
        with log_path.open("a", encoding="utf-8") as f:
            f.write(f"| {completed_at} | {command[:80]} | {started_at} |\n")
    except Exception as e:
        print(f"[on-milestone-end] failed to write milestone log: {e}", flush=True)

    try:
        draft_difficulty_lesson(command, started_at, completed_at)
    except Exception:
        pass


def draft_difficulty_lesson(command: str, started_at: str, completed_at: str) -> None:
    """If milestone elapsed > DIFFICULTY_THRESHOLD_MINUTES, draft a lesson."""
    try:
        start_dt = datetime.fromisoformat(started_at)
        end_dt = datetime.fromisoformat(completed_at)
    except (ValueError, TypeError):
        return

    elapsed_min = (end_dt - start_dt).total_seconds() / 60
    if elapsed_min < DIFFICULTY_THRESHOLD_MINUTES:
        return

    drafts_dir = paths.meta_dir() / "draft-lessons"
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


if __name__ == "__main__":
    main()
