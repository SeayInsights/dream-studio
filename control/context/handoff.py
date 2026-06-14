"""Context handoff helpers — session writing extracted from on-context-threshold handler.

Public surface: HANDOFF_PCT, HANDOFF_KB, write_handoff, write_recap, draft_handoff_lesson,
parse_stop_payload, has_session_activity, write_session_handoff, record_session_to_db.
Threshold constants are exported here so the handler imports them as single source of truth.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import paths  # noqa: E402
from core.utils.time import utcnow  # noqa: E402

WARN_PCT = 55
COMPACT_PCT = 70
HANDOFF_PCT = 75
URGENT_PCT = 82

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


def write_handoff(
    cwd: Path, kb: float, session_id: str | None, is_pct: bool = False
) -> Path | None:
    now = utcnow()
    date_str = now.strftime("%Y-%m-%d")
    session_root = paths.sessions_dir() / date_str
    try:
        session_root.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(
            f"[on-context-threshold] cannot create sessions dir: {e}", file=sys.stderr, flush=True
        )
        return None

    sid = (session_id or "unknown")[:8]
    base = session_root / f"handoff-{sid}.md"
    handoff_path = base
    counter = 1
    while handoff_path.exists():
        handoff_path = session_root / f"handoff-{sid}-{counter}.md"
        counter += 1

    branch = git(["branch", "--show-current"], cwd) or "unknown"
    last_commit = git(["log", "--oneline", "-1"], cwd) or "unknown"
    files = active_files(cwd)
    files_lines = (
        "\n".join(f"- `{p}`: {ln}" for ln, p in files) if files else "- (working tree clean)"
    )

    handoff = (
        f"# Handoff: {branch}\n"
        f"Date: {date_str}\n\n"
        f"## Current state\n"
        f"- **Branch:** {branch}\n"
        f"- **Last commit:** {last_commit}\n"
        f"- **Context:** ~{kb:.0f}{'%' if is_pct else ' KB'} (threshold: {HANDOFF_PCT if is_pct else HANDOFF_KB}{'%' if is_pct else ' KB'})\n\n"
        f"## Active files\n"
        f"{files_lines}\n\n"
        f"## Next action\n"
        f"Continue work on branch `{branch}`. Check git log for recent task context.\n"
    )
    try:
        handoff_path.write_text(handoff, encoding="utf-8")
    except Exception as e:
        print(f"[on-context-threshold] handoff write failed: {e}", file=sys.stderr, flush=True)
        return None

    # Only surface the "open a new session" message for context-overflow handoffs,
    # not routine session-end saves (kb=0 sentinel from write_session_handoff).
    if kb > 0:
        print(
            f"\n  -> HANDOFF written: {handoff_path}\n"
            f"  -> Open a new session and resume from this file.\n",
            flush=True,
        )
    return handoff_path


def write_recap(cwd: Path, kb: float, session_id: str | None, handoff_path: Path | None) -> None:
    now = utcnow()
    date_str = now.strftime("%Y-%m-%d")
    session_root = paths.sessions_dir() / date_str
    session_root.mkdir(parents=True, exist_ok=True)

    sid = (session_id or "unknown")[:8]
    recap_path = session_root / f"recap-{sid}.md"
    branch = git(["branch", "--show-current"], cwd) or "unknown"
    commits_raw = git(["log", "--oneline", "-10"], cwd)
    commits = commits_raw.splitlines() if commits_raw else []
    files = active_files(cwd)

    commits_lines = "\n".join(f"  - {c}" for c in commits) if commits else "  - (no recent commits)"
    changed_lines = (
        "\n".join(f"- `{p}`: {ln}" for ln, p in files) if files else "- (working tree clean)"
    )
    next_step = (
        f"Read `{handoff_path}` to resume."
        if handoff_path
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

    # Store recap blob in files.db (category='handoff') so it persists beyond loose .md files.
    try:
        from core.files.store import write_file
        from core.sdlc.cwd_resolver import resolve_project_from_cwd

        ctx_obj = resolve_project_from_cwd()
        project_id = ctx_obj.project_id if ctx_obj is not None else None
        write_file(
            name=f"recap-{sid}",
            content=recap.encode("utf-8"),
            content_type="text/markdown",
            category="handoff",
            project_id=project_id,
            correlation_id=session_id,
        )
    except Exception:
        pass


def draft_handoff_lesson(kb: float, ctx: str, session_id: str | None, is_pct: bool = False) -> None:
    try:
        from core.event_store.studio_db import insert_lesson

        date_str = utcnow().strftime("%Y-%m-%d")
        sid = session_id or "unknown"
        lesson_id = f"handoff-{date_str}-{sid[:8]}"
        threshold = f"{HANDOFF_PCT}%" if is_pct else f"{HANDOFF_KB} KB"
        what_happened = (
            f"Session hit auto-handoff at ~{kb:.0f}{'%' if is_pct else ' KB'}"
            f" (threshold: {threshold}). Git state: {ctx}. Session: {sid}"
        )
        inserted = insert_lesson(
            lesson_id,
            "on-context-threshold",
            "Context Budget Exceeded",
            what_happened=what_happened,
            confidence="medium",
            db_path=paths.state_dir() / "studio.db",
        )
        if inserted:
            print(
                f"  -> SENSOR: Handoff retrospective drafted (DB lesson_id: {lesson_id})\n",
                flush=True,
            )
    except Exception:
        pass


# Helpers for on-stop-handoff hook

SESSION_END_KB = 0.0  # sentinel: Stop hook has no context % — use 0 KB


def parse_stop_payload(raw_input: str, default_cwd: Path) -> tuple[str | None, Path]:
    """Parse Stop event payload and extract session_id and cwd."""
    try:
        payload = json.loads(raw_input) if raw_input.strip() else {}
        try:
            from core.events.models import StopPayload

            validated = StopPayload(**payload)
            session_id = validated.session_id or None
        except Exception:
            session_id = payload.get("session_id") or None
        payload_cwd = payload.get("cwd") or None
        cwd = Path(payload_cwd) if payload_cwd else default_cwd
        return session_id, cwd
    except Exception:
        return None, default_cwd


def last_commit_age_seconds(cwd: Path) -> float | None:
    """Return seconds since the last commit, or None if git is unavailable."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ct"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=4,
        )
        ts = result.stdout.strip()
        if not ts:
            return None
        return time.time() - float(ts)
    except Exception:
        return None


def has_session_activity(cwd: Path) -> bool:
    """Return True if the working tree has changes OR a recent commit exists."""
    files = active_files(cwd)
    if files:
        return True
    age = last_commit_age_seconds(cwd)
    if age is not None and age <= 86400:  # 24 hours
        return True
    return False


def write_session_handoff(cwd: Path, session_id: str | None) -> Path | None:
    """Write handoff and recap for session end."""
    handoff_path = write_handoff(cwd, SESSION_END_KB, session_id, is_pct=False)
    write_recap(cwd, SESSION_END_KB, session_id, handoff_path)
    return handoff_path


def record_session_to_db(cwd: Path, session_id: str | None, handoff_path: Path | None) -> None:
    """Record session and handoff to database."""
    try:
        from core.event_store.studio_db import insert_session, insert_handoff
        from core.sdlc.cwd_resolver import resolve_project_from_cwd

        # Resolve UUID project_id via marker. Falls back to None for unregistered dirs.
        ctx = resolve_project_from_cwd()
        project_id = ctx.project_id if ctx is not None else None
        sid = session_id or "unknown"
        branch = (
            subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            or "unknown"
        )
        last_commit = (
            subprocess.run(
                ["git", "log", "--oneline", "-1"],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.strip()
            or "unknown"
        )

        insert_session(sid, project_id)
        insert_handoff(
            sid,
            project_id,
            branch,
            branch=branch,
            last_commit=last_commit,
            active_files=[str(handoff_path)] if handoff_path else None,
            next_action=f"Read {handoff_path} to resume." if handoff_path else "Continue work.",
        )
    except Exception:
        pass
