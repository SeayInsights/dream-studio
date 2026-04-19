"""Context handoff helpers — session writing extracted from on-context-threshold handler.

Public surface: HANDOFF_PCT, HANDOFF_KB, write_handoff, write_recap, draft_handoff_lesson.
Threshold constants are exported here so the handler imports them as single source of truth.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import paths  # noqa: E402
from lib.time_utils import utcnow  # noqa: E402

WARN_PCT = 30
COMPACT_PCT = 70
HANDOFF_PCT = 75
URGENT_PCT = 78

WARN_KB = 800
COMPACT_KB = 2000
HANDOFF_KB = 2500
URGENT_KB = 3000


def git(args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except Exception:
        return ""


def git_context(cwd: Path) -> str:
    branch = git(["branch", "--show-current"], cwd)
    last = git(["log", "--oneline", "-1"], cwd)
    top = git(["rev-parse", "--show-toplevel"], cwd)
    return f"branch: {branch or 'unknown'} | last commit: {last or 'unknown'} | repo: {top or str(cwd)}"


def active_files(cwd: Path) -> list[tuple[str, str]]:
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        raw = proc.stdout
    except Exception:
        return []
    labels = {"M": "modified", "A": "added", "D": "deleted", "??": "untracked", "R": "renamed"}
    result = []
    for line in raw.splitlines():
        if len(line) < 4:
            continue
        code = line[:2].strip()
        path = line[3:]
        if code and path:
            result.append((labels.get(code, code), path))
    return result


def checkpoint_career_ops(session_id: str | None) -> str | None:
    """If career-ops has an in-progress checkpoint, preserve it in the handoff."""
    try:
        cp = paths.user_data_dir() / "career-ops" / "checkpoint.json"
        if not cp.exists():
            return None
        data = json.loads(cp.read_text(encoding="utf-8"))
        if data.get("status") in ("in_progress", "partial"):
            data["handoff_session"] = session_id
            data["handoff_reason"] = "context_threshold"
            cp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            return (
                f"\n## Career-Ops State\n"
                f"- **Action:** {data.get('last_action', 'unknown')}\n"
                f"- **Mode:** {data.get('mode', 'unknown')}\n"
                f"- **Status:** {data.get('status')}\n"
                f"- **Checkpoint:** `~/.dream-studio/career-ops/checkpoint.json`\n"
                f"- Resume with: read checkpoint → continue from pending items\n"
            )
        return None
    except Exception:
        return None


def write_handoff(cwd: Path, kb: float, session_id: str | None, is_pct: bool = False) -> Path | None:
    now = utcnow()
    date_str = now.strftime("%Y-%m-%d")
    sessions_dir = cwd / ".sessions" / date_str
    try:
        sessions_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"[on-context-threshold] cannot create sessions dir: {e}", file=sys.stderr, flush=True)
        return None

    sid = (session_id or "unknown")[:8]
    base = sessions_dir / f"handoff-{sid}.md"
    handoff_path = base
    counter = 1
    while handoff_path.exists():
        handoff_path = sessions_dir / f"handoff-{sid}-{counter}.md"
        counter += 1

    branch = git(["branch", "--show-current"], cwd) or "unknown"
    last_commit = git(["log", "--oneline", "-1"], cwd) or "unknown"
    files = active_files(cwd)
    files_lines = (
        "\n".join(f"- `{p}`: {l}" for l, p in files) if files else "- (working tree clean)"
    )

    career_section = checkpoint_career_ops(session_id) or ""

    handoff = (
        f"# Handoff: {branch}\n"
        f"Date: {date_str}\n\n"
        f"## Current state\n"
        f"- **Branch:** {branch}\n"
        f"- **Last commit:** {last_commit}\n"
        f"- **Context:** ~{kb:.0f}{'%' if is_pct else ' KB'} (threshold: {HANDOFF_PCT if is_pct else HANDOFF_KB}{'%' if is_pct else ' KB'})\n\n"
        f"## Active files\n"
        f"{files_lines}\n"
        f"{career_section}\n"
        f"## Next action\n"
        f"Continue work on branch `{branch}`. Check git log for recent task context.\n"
    )
    try:
        handoff_path.write_text(handoff, encoding="utf-8")
    except Exception as e:
        print(f"[on-context-threshold] handoff write failed: {e}", file=sys.stderr, flush=True)
        return None

    print(
        f"\n  -> HANDOFF written: {handoff_path}\n"
        f"  -> Open a new session and resume from this file.\n",
        flush=True,
    )
    return handoff_path


def write_recap(cwd: Path, kb: float, session_id: str | None, handoff_path: Path | None) -> None:
    now = utcnow()
    date_str = now.strftime("%Y-%m-%d")
    sessions_dir = cwd / ".sessions" / date_str
    sessions_dir.mkdir(parents=True, exist_ok=True)

    sid = (session_id or "unknown")[:8]
    recap_path = sessions_dir / f"recap-{sid}.md"
    branch = git(["branch", "--show-current"], cwd) or "unknown"
    commits_raw = git(["log", "--oneline", "-10"], cwd)
    commits = commits_raw.splitlines() if commits_raw else []
    files = active_files(cwd)

    commits_lines = "\n".join(f"  - {c}" for c in commits) if commits else "  - (no recent commits)"
    changed_lines = "\n".join(f"- `{p}`: {l}" for l, p in files) if files else "- (working tree clean)"
    next_step = (
        f"Read `{handoff_path}` to resume." if handoff_path
        else f"Continue work on branch `{branch}`."
    )

    recap = (
        f"# Recap: {branch}\n"
        f"Date: {date_str}\n"
        f"Session: {session_id or 'unknown'}\n\n"
        f"## What was built\n"
        f"{changed_lines}\n"
        f"- Commits:\n{commits_lines}\n\n"
        f"## Risk flags\n"
        f"- Context budget exceeded at ~{kb:.0f} KB (threshold: {HANDOFF_KB} KB)\n\n"
        f"## Next step\n"
        f"{next_step}\n"
    )
    try:
        recap_path.write_text(recap, encoding="utf-8")
        print(f"  -> RECAP written: {recap_path}\n", flush=True)
    except Exception as e:
        print(f"[on-context-threshold] recap write failed: {e}", file=sys.stderr, flush=True)


def draft_handoff_lesson(kb: float, ctx: str, session_id: str | None, is_pct: bool = False) -> None:
    try:
        timestamp = utcnow().isoformat()
        date_str = utcnow().strftime("%Y-%m-%d")
        drafts_dir = paths.meta_dir() / "draft-lessons"
        drafts_dir.mkdir(parents=True, exist_ok=True)

        sid = session_id or "unknown"
        draft_path = drafts_dir / f"handoff-{date_str}-{sid[:8]}.md"
        if draft_path.exists():
            return

        draft = (
            f"---\n"
            f"type: draft-lesson\n"
            f"source: on-context-threshold\n"
            f"status: draft\n"
            f"created: {timestamp}\n"
            f"---\n\n"
            f"## Context Budget Exceeded\n\n"
            f"Session hit auto-handoff at ~{kb:.0f}{'%' if is_pct else ' KB'} (threshold: {HANDOFF_PCT if is_pct else HANDOFF_KB}{'%' if is_pct else ' KB'}).\n\n"
            f"**Git state:** {ctx}\n"
            f"**Session:** {sid}\n\n"
            f"## Retrospective Prompts\n\n"
            f"1. What task was being worked on when context blew up?\n"
            f"2. Was there unnecessary exploration or thrashing?\n"
            f"3. Could the task have been split into smaller milestones?\n"
            f"4. Were large files read that didn't need to be?\n"
            f"5. Should a /compact have been run earlier?\n\n"
            f"## Director Action\n\n"
            f"- [ ] Add lesson to patterns (what to avoid next time)\n"
            f"- [ ] No action needed (one-off)\n"
            f"- [ ] Reject (delete this file)\n"
        )
        draft_path.write_text(draft, encoding="utf-8")
        print(f"  -> SENSOR: Handoff retrospective drafted: {draft_path}\n", flush=True)
    except Exception:
        pass
