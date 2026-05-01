"""
resume_from_handoff.py — reads a handoff JSON and produces a structured session briefing.

Usage:
    py scripts/resume_from_handoff.py [handoff.json] [--checkout] [--brief]

    --brief     Output just the one-line resume command
    --checkout  Also switch to the handoff's branch via git checkout
    (no flags)  Full structured briefing

If no file argument is given, scans .sessions/ for the most recent handoff-*.json.
"""

import argparse
import glob
import io
import json
import os
import subprocess
import sys
from pathlib import Path

# Force UTF-8 output on Windows so the box-drawing border renders correctly.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf_8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BORDER = "═" * 43


def find_latest_handoff(sessions_dir: str = ".sessions") -> str | None:
    """Scan .sessions/ for the most recent handoff-*.json."""
    pattern = os.path.join(sessions_dir, "handoff-*.json")
    matches = glob.glob(pattern)
    if not matches:
        return None
    # Sort by modification time, newest first
    matches.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    return matches[0]


def load_handoff(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run_git(args: list[str]) -> str:
    """Run a git command and return its stdout. Returns empty string on failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


def current_branch() -> str:
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"])


def git_checkout(branch: str) -> bool:
    """Checkout branch. Returns True on success."""
    try:
        result = subprocess.run(
            ["git", "checkout", branch],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def get_recent_commits(last_commit: str, max_lines: int = 10) -> list[str]:
    """Return up to max_lines commit lines since last_commit."""
    if not last_commit:
        return []
    output = run_git(["log", "--oneline", f"{last_commit}..HEAD"])
    if not output:
        return []
    lines = output.splitlines()
    return lines[:max_lines]


def build_resume_command(data: dict) -> str:
    plan_path = data.get("plan_path", "<plan_path unknown>")
    task_id = data.get("current_task_id", "?")
    task_name = data.get("current_task_name", "<task unknown>")
    return f"Read {plan_path} — resume at Task {task_id}: {task_name}"


def print_full_briefing(data: dict) -> None:
    topic = data.get("topic", "(no topic)")
    phase = data.get("pipeline_phase", "(unknown)")
    branch = data.get("branch", "(unknown)")

    # Progress
    tasks = data.get("tasks", [])
    if tasks:
        done = sum(1 for t in tasks if t.get("status") in ("done", "complete", "completed"))
        total = len(tasks)
        progress = f"{done} of {total} tasks complete"
    else:
        progress = data.get("progress", "(unknown)")

    # Commits since handoff
    last_commit = data.get("last_commit", "")
    commit_lines = get_recent_commits(last_commit)

    resume_cmd = build_resume_command(data)

    lines = [
        BORDER,
        " SESSION RESUME BRIEFING",
        BORDER,
        "",
        f" Topic:     {topic}",
        f" Phase:     {phase}",
        f" Branch:    {branch}",
        f" Progress:  {progress}",
    ]

    # WHAT'S WORKING
    working = data.get("working", [])
    if working:
        lines.append("")
        lines.append(" WHAT'S WORKING")
        for item in working:
            lines.append(f" • {item}")

    # WHAT'S BROKEN
    broken = data.get("broken", [])
    if broken:
        lines.append("")
        lines.append(" WHAT'S BROKEN")
        for item in broken:
            if isinstance(item, dict):
                name = item.get("name", item.get("item", str(item)))
                detail = item.get("detail", item.get("description", ""))
                lines.append(f" • {name}: {detail}" if detail else f" • {name}")
            else:
                lines.append(f" • {item}")

    # PENDING DECISIONS
    decisions = data.get("pending_decisions", [])
    if decisions:
        lines.append("")
        lines.append(" PENDING DECISIONS")
        for item in decisions:
            if isinstance(item, dict):
                decision = item.get("decision", item.get("name", str(item)))
                context = item.get("context", item.get("detail", ""))
                lines.append(f" • {decision}: {context}" if context else f" • {decision}")
            else:
                lines.append(f" • {item}")

    # LESSONS FROM LAST SESSION
    lessons = data.get("lessons_this_session", [])
    if lessons:
        lines.append("")
        lines.append(" LESSONS FROM LAST SESSION")
        for item in lessons:
            lines.append(f" • {item}")

    # RECENT COMMITS
    lines.append("")
    lines.append(" RECENT COMMITS (since handoff)")
    if commit_lines:
        for c in commit_lines:
            lines.append(f"   {c}")
    elif last_commit:
        lines.append("   (no new commits since handoff)")
    else:
        lines.append("   (no last_commit recorded in handoff)")

    # NEXT ACTION
    next_action = data.get("next_action", "(none specified)")
    lines.append("")
    lines.append(" NEXT ACTION")
    lines.append(f" → {next_action}")

    # RESUME COMMAND
    lines.append("")
    lines.append(" RESUME COMMAND")
    lines.append(f" {resume_cmd}")
    lines.append("")
    lines.append(BORDER)

    print("\n".join(lines))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resume a dream-studio session from a handoff JSON.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "handoff_file",
        nargs="?",
        help="Path to handoff JSON. Auto-discovers .sessions/handoff-*.json if omitted.",
    )
    parser.add_argument(
        "--checkout",
        action="store_true",
        help="Switch to the branch recorded in the handoff.",
    )
    parser.add_argument(
        "--brief",
        action="store_true",
        help="Output only the one-line resume command.",
    )
    args = parser.parse_args()

    # Resolve handoff file
    handoff_path = args.handoff_file
    if not handoff_path:
        handoff_path = find_latest_handoff(".sessions")
        if not handoff_path:
            print("Error: no handoff file specified and no handoff-*.json found in .sessions/", file=sys.stderr)
            sys.exit(1)
        print(f"Auto-discovered: {handoff_path}", file=sys.stderr)

    if not os.path.isfile(handoff_path):
        print(f"Error: file not found: {handoff_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = load_handoff(handoff_path)
    except json.JSONDecodeError as exc:
        print(f"Error: invalid JSON in {handoff_path}: {exc}", file=sys.stderr)
        sys.exit(1)

    # Handle --checkout
    if args.checkout:
        branch = data.get("branch", "")
        if branch:
            active = current_branch()
            if active != branch:
                print(f"Checking out branch: {branch}", file=sys.stderr)
                if not git_checkout(branch):
                    print(f"Warning: git checkout {branch!r} failed — continuing anyway.", file=sys.stderr)
            else:
                print(f"Already on branch: {branch}", file=sys.stderr)
        else:
            print("Warning: no branch in handoff JSON; skipping checkout.", file=sys.stderr)

    # Output
    if args.brief:
        print(build_resume_command(data))
    else:
        print_full_briefing(data)


if __name__ == "__main__":
    main()
