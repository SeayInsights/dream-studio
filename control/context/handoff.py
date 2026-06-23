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

# KB-band thresholds — the FALLBACK used when no context percentage is available
# (the bridge file is missing/stale). Tuned for a 200k-token window; on a larger
# window the transcript grows proportionally more before hitting the same percentage,
# so these are scaled by the active context window (WO-CONTEXT-THRESHOLD-SCALE) —
# otherwise they trip at ~50% on the 1M-token model. The percentage path (pct_to_band)
# is window-relative already and needs no scaling.
WARN_KB = 800
COMPACT_KB = 2000
HANDOFF_KB = 2500
URGENT_KB = 3000

# Baseline window the fixed *_KB thresholds were tuned for.
BASELINE_WINDOW_TOKENS = 200_000
CONTEXT_WINDOW_ENV = "DREAM_STUDIO_CONTEXT_WINDOW_TOKENS"
CONTEXT_WINDOW_CONFIG_KEY = "context.window_tokens"


def context_window_tokens(db_path: Path | None = None) -> int:
    """Resolve the active model's context window in tokens.

    Resolution order: ``DREAM_STUDIO_CONTEXT_WINDOW_TOKENS`` env var > ds_config
    ``context.window_tokens`` row > the 200k baseline. Set this for the 1M-token model
    (``1000000``) so the KB-fallback thresholds scale up instead of tripping at ~50%.
    Never raises — any resolution failure degrades to the baseline.
    """
    import os

    env = os.environ.get(CONTEXT_WINDOW_ENV)
    if env:
        try:
            return int(env)
        except ValueError:
            pass
    try:
        from core.config import paths as _paths
        from core.config.authority import get_config_value

        _db = db_path or (_paths.state_dir() / "studio.db")
        raw = get_config_value(CONTEXT_WINDOW_CONFIG_KEY, _db)
        if raw is not None:
            return int(raw)
    except Exception:
        pass
    return BASELINE_WINDOW_TOKENS


def kb_threshold_scale(db_path: Path | None = None) -> float:
    """Scale factor for the KB-band thresholds = active window / 200k baseline.

    1.0 on a 200k window, 5.0 on the 1M model, 0.5 on a 100k window.
    """
    return context_window_tokens(db_path) / BASELINE_WINDOW_TOKENS


def scaled_kb_thresholds(db_path: Path | None = None) -> dict[str, float]:
    """The four KB-band thresholds scaled to the active context window."""
    s = kb_threshold_scale(db_path)
    return {
        "warn": WARN_KB * s,
        "compact": COMPACT_KB * s,
        "handoff": HANDOFF_KB * s,
        "urgent": URGENT_KB * s,
    }


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
        f"- **Context:** ~{kb:.0f}{'%' if is_pct else ' KB'} (threshold: {HANDOFF_PCT if is_pct else scaled_kb_thresholds()['handoff']:.0f}{'%' if is_pct else ' KB'})\n\n"
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
        f"- Context budget exceeded at ~{kb:.0f} KB (threshold: {scaled_kb_thresholds()['handoff']:.0f} KB)\n\n"
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
    """Emit a console retrospective marker on auto-handoff.

    WO-HANDOFF-LESSON-NOISE: this used to insert a body-less draft into raw_lessons
    on every context-threshold trip ("Context Budget Exceeded"), which polluted the
    lessons pipeline (every handoff became a stuck pending draft with no learning
    content). A handoff is an operational event, not a learning — the handoff packet
    (write_handoff) already persists it — so this no longer writes to raw_lessons.
    """
    try:
        sid = session_id or "unknown"
        threshold = f"{HANDOFF_PCT}%" if is_pct else f"{scaled_kb_thresholds()['handoff']:.0f} KB"
        print(
            f"  -> SENSOR: Handoff at ~{kb:.0f}{'%' if is_pct else ' KB'}"
            f" (threshold: {threshold}, session: {sid})\n",
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
